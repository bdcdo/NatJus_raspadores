"""Raspador de pareceres do NatJus DF (TJDFT).

A listagem paginada do site so exibe ~50 itens, mas os PDFs existem
para IDs no range ~933-4700. Este script itera por todos os IDs,
baixa os PDFs e extrai o titulo de cada um via pagina /view.

Usage:
    uv run python scrapers/raspar_df.py
"""

import csv
import logging
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

BASE_URL = "https://www.tjdft.jus.br/informacoes/notas-laudos-e-pareceres/natjus-df"
OUTPUT_DIR = Path("output/df_tjdft")
PDF_DIR = OUTPUT_DIR / "pdfs"
CSV_PATH = OUTPUT_DIR / "metadados.csv"
CSV_FIELDS = ["id", "titulo", "url_pdf", "caminho_local", "status_download"]
ID_MIN = 933
ID_MAX = 4800
DELAY = 0.3


def setup():
    PDF_DIR.mkdir(parents=True, exist_ok=True)


def load_already_downloaded():
    downloaded = {}
    if CSV_PATH.exists():
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                downloaded[row["id"]] = row
    return downloaded


def get_title(session, pdf_id):
    """Extrai o titulo do parecer via pagina /view."""
    try:
        r = session.get(f"{BASE_URL}/{pdf_id}.pdf/view", timeout=15)
        if r.status_code == 200 and "text/html" in r.headers.get("content-type", ""):
            soup = BeautifulSoup(r.text, "html.parser")
            h1 = soup.find("h1")
            if h1:
                return h1.get_text(strip=True)
    except requests.RequestException:
        pass
    return ""


def download_pdf(session, pdf_id):
    """Tenta baixar o PDF. Retorna (filepath, True) se OK, (None, False) se nao existe, ou levanta excecao."""
    url = f"{BASE_URL}/{pdf_id}.pdf"
    resp = session.get(url, timeout=60, stream=True)

    if resp.status_code == 404:
        resp.close()
        return None

    resp.raise_for_status()
    ct = resp.headers.get("content-type", "")
    if "pdf" not in ct:
        resp.close()
        return None

    content = resp.content
    if not content[:5].startswith(b"%PDF"):
        return None

    filepath = PDF_DIR / f"{pdf_id}.pdf"
    tmp_path = filepath.with_suffix(".tmp")
    tmp_path.write_bytes(content)
    tmp_path.rename(filepath)
    return str(filepath)


def append_csv(row):
    write_header = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def main():
    setup()
    downloaded = load_already_downloaded()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    })

    total_new = 0
    total_skip = len(downloaded)
    total_miss = 0
    consecutive_miss = 0

    log.info("Raspagem NatJus DF -- IDs %d a %d", ID_MIN, ID_MAX)
    if total_skip:
        log.info("  %d ja baixados, retomando.", total_skip)

    for pdf_id in range(ID_MIN, ID_MAX + 1):
        str_id = str(pdf_id)

        if str_id in downloaded:
            consecutive_miss = 0
            continue

        for attempt in range(3):
            try:
                filepath = download_pdf(session, str_id)
                break
            except requests.RequestException as e:
                if attempt < 2:
                    time.sleep(2 ** (attempt + 1))
                else:
                    log.warning("  FALHA %s: %s", str_id, e)
                    filepath = None

        if filepath is None:
            total_miss += 1
            consecutive_miss += 1
            if consecutive_miss >= 100:
                log.info("  100 IDs consecutivos sem PDF apos ID %d, encerrando.", pdf_id)
                break
            continue

        consecutive_miss = 0
        titulo = get_title(session, str_id)
        url_pdf = f"{BASE_URL}/{str_id}.pdf"

        row = {
            "id": str_id,
            "titulo": titulo,
            "url_pdf": url_pdf,
            "caminho_local": filepath,
            "status_download": "ok",
        }
        append_csv(row)
        downloaded[str_id] = row
        total_new += 1

        count = total_new + total_skip
        label = f"{titulo[:55]}" if titulo else "(sem titulo)"
        log.info("  [%d] %s -- %s", count, str_id, label)

        time.sleep(DELAY)

    total = total_new + total_skip
    log.info("Concluido! %d novos, %d total, %d IDs sem PDF.", total_new, total, total_miss)


if __name__ == "__main__":
    main()
