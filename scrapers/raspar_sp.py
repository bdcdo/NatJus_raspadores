"""Raspador de pareceres do NatJus SP (TJSP).

Usage:
    uv run python scrapers/raspar_sp.py
"""

import base64
import csv
import json
import logging
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

SEARCH_URL = "https://www.tjsp.jus.br/RHF/NatJus/Apresentacao/Pesquisar"
ANEXO_URL = "https://www.tjsp.jus.br/RHF/NatJus/Administracao/Documento/ObterAnexo/"
OUTPUT_DIR = Path("output/sp_tjsp")
PDF_DIR = OUTPUT_DIR / "pdfs"
CSV_PATH = OUTPUT_DIR / "metadados.csv"
CSV_COLUMNS = [
    "id", "cid", "doenca", "tipo_acao", "tecnologia",
    "nome_arquivo", "url_pdf", "caminho_local", "status_download",
]
PAGE_SIZE = 500
DELAY = 0.5
DELAY_PDF = 1.0


def setup():
    PDF_DIR.mkdir(parents=True, exist_ok=True)


def load_already_downloaded():
    """Carrega IDs já baixados do CSV para poder retomar."""
    downloaded = set()
    if CSV_PATH.exists():
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                downloaded.add(row["id"])
    return downloaded


def fetch_page(session, start):
    """Busca uma página de resultados da API. Retorna (itens, total)."""
    for attempt in range(3):
        try:
            resp = session.post(SEARCH_URL, data={
                "draw": 1,
                "start": start,
                "length": PAGE_SIZE,
                "Cid": "",
                "Doenca": "",
                "TipoAcao": "",
                "Tecnologia": "",
                "AnexoString": "",
            }, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            lista = data.get("ListaRetorno", "")
            if not lista or lista == "[]":
                return [], int(data.get("Total", 0))
            items = json.loads(lista)
            total = int(data.get("Total", 0))
            return items, total
        except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
            if attempt < 2:
                log.warning("Erro na página start=%d, tentativa %d: %s", start, attempt + 1, e)
                time.sleep(2 ** attempt)
            else:
                log.error("FALHA ao buscar página start=%d: %s", start, e)
                raise


def parse_item(raw):
    """Transforma item da API em dict plano para o CSV."""
    cids = raw.get("Cids") or []
    cod_list = [c.get("Cod", "") for c in cids if c.get("Cod")]
    desc_list = [c.get("Descricao", "") for c in cids if c.get("Descricao")]

    tecnologia = (raw.get("Tecnologia") or "").replace("\n", " ").strip()

    return {
        "id": str(raw["Id"]),
        "cid": "; ".join(cod_list),
        "doenca": "; ".join(desc_list),
        "tipo_acao": raw.get("TipoAcao", ""),
        "tecnologia": tecnologia,
        "nome_arquivo": "",
        "url_pdf": ANEXO_URL + str(raw["Id"]),
        "caminho_local": "",
        "status_download": "",
    }


def download_pdf(session, doc_id):
    """Baixa um PDF via API (base64 em JSON). Retorna (caminho, nome_arquivo) ou (None, None)."""
    url = ANEXO_URL + str(doc_id)

    for attempt in range(3):
        try:
            resp = session.get(url, timeout=120)
            resp.raise_for_status()
            data = resp.json()

            lista = data.get("ListaRetorno", "")
            if not lista:
                log.warning("AVISO: %s sem ListaRetorno, pulando", doc_id)
                return None, None

            inner = json.loads(lista)

            anexo = inner.get("AnexoConteudo") or {}
            conteudo_b64 = anexo.get("Conteudo")
            if not conteudo_b64:
                log.warning("AVISO: %s sem conteúdo base64, pulando", doc_id)
                return None, None

            pdf_bytes = base64.b64decode(conteudo_b64)

            if not pdf_bytes[:5].startswith(b"%PDF"):
                log.warning("AVISO: %s não parece ser PDF, pulando", doc_id)
                return None, None

            nome_arquivo = inner.get("NomeArquivo", "")
            filepath = PDF_DIR / f"{doc_id}.pdf"
            with open(filepath, "wb") as f:
                f.write(pdf_bytes)

            return str(filepath), nome_arquivo

        except (requests.RequestException, json.JSONDecodeError, Exception) as e:
            if attempt < 2:
                log.warning("Erro no PDF %s, tentativa %d: %s", doc_id, attempt + 1, e)
                time.sleep(2 ** attempt)
            else:
                log.error("FALHA ao baixar PDF %s: %s", doc_id, e)
                return None, None

    return None, None


def append_csv(item):
    """Adiciona uma linha ao CSV de metadados."""
    write_header = not CSV_PATH.exists()
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if write_header:
            writer.writeheader()
        writer.writerow(item)


def main():
    setup()
    downloaded = load_already_downloaded()
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (research bot - levantamento NatJus)",
        "Referer": "https://www.tjsp.jus.br/RHF/natjus",
    })

    log.info("=== Raspador NatJus SP (TJSP) ===")

    # Fase 1: coletar todos os metadados
    log.info("Fase 1: Coletando metadados...")
    all_items = []
    start = 0
    total = None

    while True:
        items, reported_total = fetch_page(session, start)
        if total is None:
            total = reported_total
            log.info("Total reportado pela API: %d registros", total)

        if not items:
            break

        all_items.extend(items)
        log.info("Coletados: %d/%d", len(all_items), total)

        start += PAGE_SIZE
        if start >= total:
            break
        time.sleep(DELAY)

    log.info("Fase 1 concluída: %d itens coletados.", len(all_items))

    # Fase 2: baixar PDFs
    novos = [i for i in all_items if str(i["Id"]) not in downloaded]
    total_ja_baixados = len(downloaded)
    total_novos = len(novos)

    log.info("Fase 2: Baixando PDFs...")
    if total_ja_baixados:
        log.info("%d já baixados anteriormente, pulando.", total_ja_baixados)
    log.info("%d novos para baixar.", total_novos)

    baixados = 0
    erros = 0

    for i, raw in enumerate(novos, 1):
        item = parse_item(raw)
        filepath, nome_arquivo = download_pdf(session, item["id"])

        if filepath:
            item["caminho_local"] = filepath
            item["nome_arquivo"] = nome_arquivo or ""
            item["status_download"] = "ok"
            append_csv(item)
            downloaded.add(item["id"])
            baixados += 1
            log.info("[%d/%d] %s - %s", total_ja_baixados + baixados, total, item["id"], item["tecnologia"][:60])
        else:
            item["status_download"] = "erro"
            append_csv(item)
            erros += 1

        time.sleep(DELAY_PDF)

    log.info("Concluído! %d novos PDFs baixados, %d erros, %d total.", baixados, erros, len(downloaded))


if __name__ == "__main__":
    main()
