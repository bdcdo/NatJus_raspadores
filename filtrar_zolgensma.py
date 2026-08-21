"""Filtra pareceres relacionados a Zolgensma/AME e consolida em CSV único.

Identifica pareceres relevantes no metadados do RJ, extrai texto dos PDFs
que ainda não foram processados, e junta com os dados existentes de DF/SP.

Uso:
    uv run python filtrar_zolgensma.py
"""

import csv
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from extrair_textos import extract_text

OUTPUT_DIR = Path(__file__).parent / "output"
WORKERS = 12

TERMOS = [
    "zolgensma",
    "onasemnogen",              # captura onasemnogene e onasemnogeno
    "atrofia muscular espinhal",
    "amiotrofia espinhal",
]

PATTERN = re.compile("|".join(re.escape(t) for t in TERMOS), re.IGNORECASE)
STATUS_OK = ("sucesso", "ja_existia")


def matches_text(row: dict) -> bool:
    text = (row.get("title", "") + " " + row.get("text", ""))
    return bool(PATTERN.search(text))


def matches_desc(desc: str) -> bool:
    return bool(PATTERN.search(desc))


def load_csv(path: Path, encoding: str = "utf-8") -> list[dict]:
    with open(path, encoding=encoding) as f:
        return list(csv.DictReader(f))


def _extract(args: tuple[str, str, str]) -> tuple[str, str, str, str | None]:
    """Worker: extrai texto de um PDF."""
    external_id, title, pdf_path = args
    try:
        p = Path(pdf_path)
        if not p.exists():
            return (external_id, title, "", f"PDF não encontrado: {pdf_path}")
        text = extract_text(pdf_path)
        if not text:
            return (external_id, title, "", "Texto vazio após extração")
        return (external_id, title, text, None)
    except Exception as e:
        return (external_id, title, "", f"{type(e).__name__}: {e}")


def collect_rj_pareceres() -> list[dict]:
    """Coleta pareceres de AME/Zolgensma do RJ, extraindo texto se necessário."""
    meta_path = OUTPUT_DIR / "rj_trf2" / "metadados.csv"
    texto_path = OUTPUT_DIR / "rj_trf2" / "pareceres_texto.csv"

    # Carregar textos já extraídos
    already_extracted: dict[str, dict] = {}
    if texto_path.exists():
        for row in load_csv(texto_path):
            already_extracted[row["external_id"]] = row

    # Identificar pareceres relevantes no metadados
    results = []
    to_extract: list[tuple[str, str, str]] = []

    for row in load_csv(meta_path, encoding="utf-8-sig"):
        desc = row.get("descricao", "")
        if not matches_desc(desc):
            continue
        if row.get("status_download", "") not in STATUS_OK:
            print(f"  SKIP (download falhou): {row['numero_parecer']}/{row['ano']}")
            continue

        eid = (
            f"NATJUS-FEDERAL-{row['numero_parecer']}-{row['ano']}"
            if row["numero_parecer"]
            else Path(row["arquivo_local"]).stem
        )
        title = (
            f"Parecer {row['numero_parecer']}/{row['ano']} - {desc}"
            if desc
            else f"Parecer {row['numero_parecer']}/{row['ano']}"
        )

        if eid in already_extracted:
            results.append(already_extracted[eid])
        else:
            pdf_path = OUTPUT_DIR / "rj_trf2" / "pdfs" / row["arquivo_local"]
            to_extract.append((eid, title, str(pdf_path)))

    print(f"RJ: {len(results)} já extraídos, {len(to_extract)} a extrair")

    if to_extract:
        errors = 0
        with ProcessPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(_extract, item): item for item in to_extract}
            for future in as_completed(futures):
                eid, title, text, error = future.result()
                if error:
                    print(f"  ERRO {eid}: {error}")
                    errors += 1
                else:
                    results.append({"external_id": eid, "title": title, "text": text})
        print(f"  Extração: {len(to_extract) - errors} OK, {errors} erros")

    return results


def main():
    # 1. Coletar pareceres do RJ (com extração de texto se necessário)
    rj_pareceres = collect_rj_pareceres()
    print(f"RJ total: {len(rj_pareceres)} pareceres de AME/Zolgensma")

    # 2. Carregar existente (DF + SP)
    existing_path = OUTPUT_DIR / "zolgensma_df_sp.csv"
    existing = load_csv(existing_path) if existing_path.exists() else []
    print(f"Existentes (DF/SP): {len(existing)} pareceres")

    # 3. Consolidar sem duplicatas
    seen: set[str] = set()
    consolidated: list[dict] = []
    for row in existing + rj_pareceres:
        eid = row["external_id"]
        if eid not in seen:
            seen.add(eid)
            consolidated.append(row)

    # 4. Salvar
    out_path = OUTPUT_DIR / "zolgensma.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["external_id", "title", "text"])
        writer.writeheader()
        for row in consolidated:
            writer.writerow({k: row.get(k, "") for k in ["external_id", "title", "text"]})

    print(f"\nConsolidado: {len(consolidated)} pareceres salvos em {out_path}")

    # 5. Resumo
    rj_ids = {r["external_id"] for r in rj_pareceres}
    df_sp_ids = {r["external_id"] for r in existing}
    print(f"  DF/SP: {len(df_sp_ids)} | RJ: {len(rj_ids)} | Total: {len(consolidated)}")

    print(f"\n--- Títulos do RJ ({len(rj_pareceres)} pareceres) ---")
    for r in sorted(rj_pareceres, key=lambda x: x["external_id"]):
        print(f"  {r['external_id']}: {r['title'][:100]}")


if __name__ == "__main__":
    main()
