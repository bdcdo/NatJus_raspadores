"""Raspador de pareceres do NatJus RJ (TRF2).

Baixa todos os pareceres técnicos de:
https://www10.trf2.jus.br/comite-estadual-de-saude-rj/nat-jus/pareceres/

Uso: uv run python scrapers/raspar_rj.py
"""

import csv
import logging
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# --- Configuração ---

BASE_URL = "https://www10.trf2.jus.br"
HUB_URL = BASE_URL + "/comite-estadual-de-saude-rj/nat-jus/pareceres/"

OUTPUT_DIR = Path("output/rj_trf2")
PDF_DIR = OUTPUT_DIR / "pdfs"
CSV_PATH = OUTPUT_DIR / "metadados.csv"

DELAY = 0.5
MAX_RETRIES = 3
TIMEOUT = 30
USER_AGENT = "NatJus-RJ-Scraper/1.0 (pesquisa academica)"

CSV_COLUMNS = [
    "numero_parecer",
    "ano",
    "descricao",
    "url_pdf",
    "arquivo_local",
    "status_download",
]

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# --- Funções auxiliares ---


def normalize_url(href: str) -> str:
    """Normaliza URLs em 3 formatos: protocol-relative, relativo e absoluto."""
    href = href.strip()
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return BASE_URL + href
    if href.startswith("http"):
        return href
    return urljoin(BASE_URL + "/", href)


def extract_description(tag) -> str:
    """Extrai a descrição do parecer a partir do <dd> que segue o <dt> pai.

    Estrutura HTML: <dt><a href="...">parecer-XXXX</a></dt><dd>descrição</dd>
    """
    # O <a> está dentro de um <dt>; a descrição está no <dd> seguinte
    dt = tag.parent
    if dt and dt.name == "dt":
        dd = dt.find_next_sibling("dd")
        if dd:
            return dd.get_text(strip=True)

    # Fallback: texto adjacente ao link
    text_parts = []
    for sibling in tag.next_siblings:
        if hasattr(sibling, "name") and sibling.name == "a":
            break
        t = sibling.string if hasattr(sibling, "string") else str(sibling)
        if t:
            text_parts.append(t.strip())

    desc = " ".join(text_parts).strip()
    desc = re.sub(r"^[\s\-\+–—:]+", "", desc).strip()
    return desc


def extract_parecer_number(filename: str) -> str:
    """Extrai o número do parecer do nome do arquivo."""
    # Padrão principal: parecer-XXXX-YYYY.pdf
    m = re.search(r"parecer-(\d+)-\d{4}", filename)
    if m:
        return m.group(1)
    # Padrão 2017 alternativo: pt_XXXX_...
    m = re.search(r"pt_(\d+)_", filename)
    if m:
        return m.group(1)
    return ""


# --- Scraping ---


def get_year_urls(session: requests.Session) -> list[tuple[int, str]]:
    """Busca a página hub e retorna lista de (ano, url) das páginas por ano."""
    log.info("Buscando página hub...")
    resp = fetch_with_retry(session, HUB_URL)

    soup = BeautifulSoup(resp.text, "html.parser")
    year_urls = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"pareceres-(\d{4})", href)
        if m:
            year = int(m.group(1))
            url = normalize_url(href)
            # Garantir trailing slash
            if not url.endswith("/"):
                url += "/"
            year_urls.append((year, url))

    # Deduplica e ordena por ano
    seen = set()
    unique = []
    for year, url in sorted(year_urls):
        if year not in seen:
            seen.add(year)
            unique.append((year, url))

    log.info(f"Encontrados {len(unique)} anos: {[y for y, _ in unique]}")
    return unique


def fetch_with_retry(session: requests.Session, url: str) -> requests.Response:
    """Fetch com retry e backoff exponencial."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            log.warning(f"  Tentativa {attempt}/{MAX_RETRIES} falhou para {url}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
    raise requests.RequestException(f"Falhou após {MAX_RETRIES} tentativas: {url}")


def parse_year_page(
    session: requests.Session, year: int, url: str
) -> list[dict]:
    """Parseia uma página de ano e retorna lista de dicts com metadados."""
    log.info(f"Parseando página de {year}...")
    resp = fetch_with_retry(session, url)
    resp.encoding = resp.apparent_encoding

    soup = BeautifulSoup(resp.text, "html.parser")
    entries = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.lower().endswith(".pdf"):
            continue

        pdf_url = normalize_url(href)
        filename = pdf_url.rsplit("/", 1)[-1]
        numero = extract_parecer_number(filename)
        descricao = extract_description(a)

        entries.append(
            {
                "numero_parecer": numero,
                "ano": str(year),
                "descricao": descricao,
                "url_pdf": pdf_url,
                "arquivo_local": filename,
                "status_download": "",
            }
        )

    log.info(f"  {year}: {len(entries)} pareceres encontrados")
    return entries


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


# --- Download ---


def url_candidatas(url: str) -> list[str]:
    """URLs a tentar para um mesmo documento: a registrada e a de grafia corrigida.

    A listagem do TRF2 grafa o ano com um zero à esquerda em parte dos href de
    2025, `parecer-0232-02025.pdf`, e dois nomes trazem espaços antes da extensão.
    O `parse_year_page` copia o href sem normalizar, então o 404 que volta é do
    nosso endereço e não do documento: um quinto dos 911 erros deste acervo é
    disso, e não de link morto.

    **A original vem primeiro de propósito.** Se o TRF2 um dia servir mesmo um
    arquivo com ano de cinco dígitos, o comportamento de hoje fica preservado, e
    a correção só entra como fallback do que já falhou.

    O nome de arquivo não é corrigido junto, e isso é decisão e não descuido: o
    `metadados.csv` é append-only e a dedupe chaveia por `arquivo_local`, então
    gravar o nome corrigido daria duas chaves ao mesmo parecer e inflaria o
    `listado` do acervo. Corrige-se o endereço, preserva-se a chave.
    """
    base, _, nome = url.rpartition("/")
    corrigido = re.sub(r"\s+\.pdf$", ".pdf", nome)
    corrigido = re.sub(r"-0(\d{4})\.pdf$", r"-\1.pdf", corrigido)
    if corrigido == nome:
        return [url]
    return [url, f"{base}/{corrigido}"]


def download_pdf(
    session: requests.Session, urls: list[str], filepath: Path
) -> tuple[str, str]:
    """Baixa um PDF com retries. Retorna (status, url_que_serviu).

    Recebe lista de candidatas, não uma URL: ver `url_candidatas`. A URL que
    serviu volta para ser gravada no CSV, para que a proveniência do arquivo
    diga o endereço de onde ele veio, e não o que a listagem publicou.
    """
    if filepath.exists() and filepath.stat().st_size > 0:
        # Verificar magic bytes
        with open(filepath, "rb") as f:
            if f.read(4) == b"%PDF":
                return "ja_existia", urls[0]

    tmp_path = filepath.with_suffix(".tmp")

    for url in urls:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = session.get(url, timeout=TIMEOUT, stream=True)
                resp.raise_for_status()

                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Validar PDF
                with open(tmp_path, "rb") as f:
                    magic = f.read(4)

                if magic != b"%PDF":
                    tmp_path.unlink(missing_ok=True)
                    log.warning(f"  Arquivo inválido (não é PDF): {url}")
                    return "erro", url

                tmp_path.rename(filepath)
                return "sucesso", url

            except requests.RequestException as e:
                log.warning(f"  Tentativa {attempt}/{MAX_RETRIES} falhou: {e}")
                tmp_path.unlink(missing_ok=True)
                if resposta_definitiva(e):
                    break  # passa à candidata seguinte, se houver
                if attempt < MAX_RETRIES:
                    time.sleep(2**attempt)

    return "erro", urls[0]


# --- CSV ---


def load_existing_csv() -> dict[str, dict]:
    """Carrega CSV existente como dict por arquivo_local."""
    if not CSV_PATH.exists():
        return {}
    existing = {}
    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            existing[row["arquivo_local"]] = row
    return existing


def init_csv():
    """Cria o CSV com cabeçalho se não existir."""
    if not CSV_PATH.exists():
        with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            writer.writeheader()


def append_csv(entry: dict):
    """Adiciona uma linha ao CSV."""
    with open(CSV_PATH, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writerow(entry)


# --- Main ---


def main():
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    init_csv()

    existing = load_existing_csv()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    year_urls = get_year_urls(session)
    time.sleep(DELAY)

    totals = {"sucesso": 0, "ja_existia": 0, "erro": 0}

    for year, url in year_urls:
        entries = parse_year_page(session, year, url)
        time.sleep(DELAY)

        for i, entry in enumerate(entries, 1):
            filename = entry["arquivo_local"]

            # Pular se já processado no CSV com sucesso
            if filename in existing and existing[filename].get(
                "status_download"
            ) in ("sucesso", "ja_existia"):
                totals["ja_existia"] += 1
                log.info(
                    f"  [{i}/{len(entries)}] {filename} — já processado"
                )
                continue

            filepath = PDF_DIR / filename
            candidatas = url_candidatas(entry["url_pdf"])
            status, url_usada = download_pdf(session, candidatas, filepath)
            entry["status_download"] = status
            entry["url_pdf"] = url_usada
            totals[status] += 1

            append_csv(entry)
            log.info(f"  [{i}/{len(entries)}] {filename} — {status}")

            if status != "ja_existia":
                time.sleep(DELAY)

    log.info("=" * 60)
    log.info("CONCLUÍDO!")
    log.info(
        f"  Baixados: {totals['sucesso']} | "
        f"Já existiam: {totals['ja_existia']} | "
        f"Erros: {totals['erro']}"
    )
    log.info(
        f"  Total processado: "
        f"{sum(totals.values())}"
    )
    log.info(f"  PDFs em: {PDF_DIR.resolve()}")
    log.info(f"  CSV em: {CSV_PATH.resolve()}")


if __name__ == "__main__":
    main()
