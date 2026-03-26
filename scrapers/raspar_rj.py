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


# --- Download ---


def download_pdf(
    session: requests.Session, url: str, filepath: Path
) -> str:
    """Baixa um PDF com retries. Retorna status: sucesso/erro/ja_existia."""
    if filepath.exists() and filepath.stat().st_size > 0:
        # Verificar magic bytes
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

            # Validar PDF
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
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)

    return "erro"


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
            status = download_pdf(session, entry["url_pdf"], filepath)
            entry["status_download"] = status
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
