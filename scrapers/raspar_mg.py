"""Raspador de pareceres do NatJus MG (TJMG).

Coleta metadados e PDFs da coleção NatJus no repositório DSpace do TJMG.
API: https://bd.tjmg.jus.br/server/api

Uso: uv run python scrapers/raspar_mg.py
     uv run python scrapers/raspar_mg.py --retry-errors
"""

import argparse
import csv
import logging
import time
from pathlib import Path

import requests

# --- Configuração ---

BASE_URL = "https://bd.tjmg.jus.br/server/api"
COLLECTION_UUID = "910e3664-1f94-4f35-99d8-2d0747ec4ddc"
PAGE_SIZE = 40
DELAY = 0.5
MAX_RETRIES = 3
TIMEOUT = 30

# Os status que contam como "ja tenho este PDF". Fonte unica do lado do raspador; o
# par dela, do lado da extracao, e o status_ok do TribunalConfig de MG em
# extrair_textos.py, e os dois precisam listar os mesmos valores.
STATUS_OK = ("sucesso", "ja_existia")

OUTPUT_DIR = Path("output/mg_tjmg")
PDF_DIR = OUTPUT_DIR / "pdfs"
CSV_PATH = OUTPUT_DIR / "metadados.csv"

CSV_COLUMNS = [
    "uuid",
    "titulo",
    "data_emissao",
    "resumo",
    "link_portal",
    "link_pdf",
    "caminho_local",
    "status_download",
]

USER_AGENT = "NatJus-MG-Scraper/1.0 (pesquisa academica)"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# --- Funções auxiliares ---


def setup():
    """Cria diretórios de output."""
    PDF_DIR.mkdir(parents=True, exist_ok=True)


def load_already_downloaded(retry_errors=False):
    """Carrega UUIDs já processados do CSV para resume.

    E aqui, e nao na condicao de pulo do laco principal, que se decide o que sera
    retentado: quem pula consulta este conjunto sem olhar status nenhum. Com
    retry_errors, a linha em erro deixa de entrar, e o item volta a ser candidato.

    O CSV e append-only, entao um uuid pode ter varias linhas, e a ultima e a que
    vale. Por isso o status vai para um dict e o conjunto se monta no fim: montar
    linha a linha faria uma retentativa bem-sucedida ser mascarada pela linha de
    erro anterior.
    """
    status_por_uuid = {}
    if CSV_PATH.exists():
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                status_por_uuid[row["uuid"]] = row.get("status_download", "")
    if not retry_errors:
        return set(status_por_uuid)
    return {u for u, st in status_por_uuid.items() if st in STATUS_OK}


def resposta_definitiva(e: Exception) -> bool:
    """Diz se a exceção carrega um 4xx que não seja 429, isto é, resposta e não falha.

    O `raise_for_status` transforma 404 em exceção, e o laço de retentativa a
    trata como se fosse timeout: são MAX_RETRIES tentativas com backoff
    exponencial sobre um código que não vai mudar entre elas. Medido no acervo
    do RJ em 23/08/2026: os 714 endereços de ausência confirmada custaram cerca
    de 2.100 requisições e cerca de 14 minutos apenas de `sleep`.

    O 429 fica de fora porque ele é justamente o código que pede espera, e os
    5xx continuam merecendo backoff.
    """
    resp = getattr(e, "response", None)
    return resp is not None and 400 <= resp.status_code < 500 and resp.status_code != 429


def fetch_with_retry(session, url, params=None):
    """GET com retry e backoff exponencial."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            log.warning(f"  Tentativa {attempt}/{MAX_RETRIES} falhou para {url}: {e}")
            if resposta_definitiva(e):
                break
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
    raise requests.RequestException(f"Falhou após {MAX_RETRIES} tentativas: {url}")


def get_metadata_value(metadata, key):
    """Extrai o valor de um campo de metadados se ele existir."""
    if key in metadata and len(metadata[key]) > 0:
        return metadata[key][0].get("value", "")
    return ""


def get_pdf_link(session, item_uuid):
    """Busca o link direto do PDF no bundle 'ORIGINAL'."""
    try:
        bundles_url = f"{BASE_URL}/core/items/{item_uuid}/bundles"
        resp = fetch_with_retry(session, bundles_url)
        bundles_data = resp.json()

        bundles = bundles_data.get("_embedded", {}).get("bundles", [])
        for bundle in bundles:
            if bundle.get("name") == "ORIGINAL":
                bitstreams_url = (
                    bundle.get("_links", {}).get("bitstreams", {}).get("href")
                )
                if bitstreams_url:
                    b_resp = fetch_with_retry(session, bitstreams_url)
                    bitstreams_data = b_resp.json()
                    bitstreams = (
                        bitstreams_data.get("_embedded", {}).get("bitstreams", [])
                    )
                    if bitstreams:
                        return bitstreams[0].get("_links", {}).get("content", {}).get(
                            "href"
                        )
    except requests.RequestException as e:
        log.warning(f"  Erro ao buscar PDF link para {item_uuid}: {e}")
    return ""


def download_pdf(session, url, filepath):
    """Baixa um PDF com retry. Retorna status: sucesso/erro/ja_existia."""
    if filepath.exists() and filepath.stat().st_size > 0:
        with open(filepath, "rb") as f:
            if f.read(4) == b"%PDF":
                return "ja_existia"

    tmp_path = filepath.with_suffix(".tmp")

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT, stream=True)
            resp.raise_for_status()

            with open(tmp_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            with open(tmp_path, "rb") as f:
                magic = f.read(4)

            if magic != b"%PDF":
                tmp_path.unlink(missing_ok=True)
                log.warning(f"  Arquivo inválido (não é PDF): {url}")
                return "erro"

            tmp_path.rename(filepath)
            return "sucesso"

        except requests.RequestException as e:
            log.warning(f"  Tentativa {attempt}/{MAX_RETRIES} falhou: {e}")
            tmp_path.unlink(missing_ok=True)
            if resposta_definitiva(e):
                break
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)

    return "erro"


def append_csv(entry):
    """Adiciona uma linha ao CSV de metadados."""
    write_header = not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0
    with open(CSV_PATH, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(entry)


# --- Main ---


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retry-errors",
        action="store_true",
        help="retenta os itens cuja ultima linha no CSV tem status de erro",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    setup()
    downloaded = load_already_downloaded(retry_errors=args.retry_errors)
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    log.info(f"=== Raspador NatJus MG (TJMG) ===")
    log.info(f"Coleção: {COLLECTION_UUID}")
    if downloaded:
        log.info(f"Retomando: {len(downloaded)} itens já processados")
    if args.retry_errors:
        log.info("--retry-errors ligada: itens em erro voltam para a fila")

    page = 0
    total_pages = 1
    total_elements = 0
    totals = {"sucesso": 0, "ja_existia": 0, "erro": 0, "sem_pdf": 0}
    processed = 0

    while page < total_pages:
        log.info(f"Buscando página {page}...")

        search_url = f"{BASE_URL}/discover/search/objects"
        params = {
            "scope": COLLECTION_UUID,
            "page": page,
            "size": PAGE_SIZE,
            "sort": "dc.date.accessioned,DESC",
        }

        try:
            resp = fetch_with_retry(session, search_url, params=params)
            data = resp.json()
        except requests.RequestException as e:
            log.error(f"Erro fatal na página {page}: {e}")
            break

        search_result = data.get("_embedded", {}).get("searchResult", {})

        if page == 0:
            total_pages = search_result.get("page", {}).get("totalPages", 1)
            total_elements = search_result.get("page", {}).get("totalElements", 0)
            log.info(f"Total de itens: {total_elements} ({total_pages} páginas)")

        objects = search_result.get("_embedded", {}).get("objects", [])
        if not objects:
            break

        for obj in objects:
            item = obj.get("_embedded", {}).get("indexableObject", {})
            uuid = item.get("uuid")

            if uuid in downloaded:
                totals["ja_existia"] += 1
                processed += 1
                continue

            name = item.get("name")
            metadata = item.get("metadata", {})
            date = get_metadata_value(metadata, "dc.date.issued")
            abstract = get_metadata_value(metadata, "dc.description.abstract")
            uri = get_metadata_value(metadata, "dc.identifier.uri")

            pdf_link = get_pdf_link(session, uuid)
            time.sleep(DELAY)

            entry = {
                "uuid": uuid,
                "titulo": name,
                "data_emissao": date,
                "resumo": abstract,
                "link_portal": uri,
                "link_pdf": pdf_link,
                "caminho_local": "",
                "status_download": "",
            }

            if pdf_link:
                filepath = PDF_DIR / f"{uuid}.pdf"
                status = download_pdf(session, pdf_link, filepath)
                entry["caminho_local"] = str(filepath) if status == "sucesso" else ""
                entry["status_download"] = status
                totals[status] += 1
            else:
                entry["status_download"] = "sem_pdf"
                totals["sem_pdf"] += 1

            append_csv(entry)
            downloaded.add(uuid)
            processed += 1

            log.info(
                f"  [{processed}/{total_elements}] {uuid[:8]}... "
                f"{entry['status_download']} — {(name or '')[:60]}"
            )
            time.sleep(DELAY)

        log.info(f"  Página {page} concluída.")
        page += 1

    log.info("=" * 60)
    log.info("CONCLUÍDO!")
    log.info(
        f"  Baixados: {totals['sucesso']} | "
        f"Já existiam: {totals['ja_existia']} | "
        f"Erros: {totals['erro']} | "
        f"Sem PDF: {totals['sem_pdf']}"
    )
    log.info(f"  Total processado: {processed}")
    log.info(f"  PDFs em: {PDF_DIR.resolve()}")
    log.info(f"  CSV em: {CSV_PATH.resolve()}")


if __name__ == "__main__":
    main()
