"""Filtra pareceres relacionados a nusinersena/Spinraza em CSV único.

Seleciona pareceres cujo metadado mencione explicitamente nusinersena,
nusinersen, Spinraza ou grafias incorretas frequentes. O filtro evita usar
menções no texto completo para não incluir pareceres de Zolgensma/Risdiplam
que citam Spinraza apenas como comparador.

Uso:
    uv run python filtrar_nusinersena.py
"""

import csv
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from extrair_textos import extract_text

OUTPUT_DIR = Path(__file__).parent / "output"
OUT_PATH = OUTPUT_DIR / "nusinersena.csv"
WORKERS = 12

TERMOS = [
    "nusinersena",
    "nusinersen",
    "spinraza",
    "nursinersena",
    "spiranza",
]

PATTERN = re.compile("|".join(re.escape(t) for t in TERMOS), re.IGNORECASE)


@dataclass(frozen=True)
class TribunalConfig:
    name: str
    dir_name: str
    metadata_fields: tuple[str, ...]
    build_external_id: Callable[[dict], str]
    build_title: Callable[[dict], str]
    get_pdf_path: Callable[[dict], Path]
    status_ok: tuple[str, ...] = ("sucesso",)
    encoding: str = "utf-8"


TRIBUNALS = [
    TribunalConfig(
        name="DF",
        dir_name="df_tjdft",
        metadata_fields=("titulo",),
        build_external_id=lambda r: f"NT-{r['id']}-DF",
        build_title=lambda r: r["titulo"],
        get_pdf_path=lambda r: OUTPUT_DIR / "df_tjdft" / "pdfs" / f"{r['id']}.pdf",
    ),
    TribunalConfig(
        name="SP",
        dir_name="sp_tjsp",
        metadata_fields=("tecnologia", "nome_arquivo"),
        build_external_id=lambda r: f"NT-{r['id']}-SP",
        build_title=lambda r: r["nome_arquivo"].removesuffix(".pdf"),
        get_pdf_path=lambda r: OUTPUT_DIR / "sp_tjsp" / "pdfs" / f"{r['id']}.pdf",
        status_ok=("sucesso", "ok"),
    ),
    TribunalConfig(
        name="RJ",
        dir_name="rj_trf2",
        metadata_fields=("descricao",),
        build_external_id=lambda r: (
            f"NATJUS-FEDERAL-{r['numero_parecer']}-{r['ano']}"
            if r["numero_parecer"]
            else Path(r["arquivo_local"]).stem
        ),
        build_title=lambda r: (
            f"Parecer {r['numero_parecer']}/{r['ano']} - {r['descricao']}"
            if r["descricao"]
            else f"Parecer {r['numero_parecer']}/{r['ano']}"
        ),
        get_pdf_path=lambda r: OUTPUT_DIR / "rj_trf2" / "pdfs" / r["arquivo_local"],
        status_ok=("sucesso", "ja_existia"),
        encoding="utf-8-sig",
    ),
    TribunalConfig(
        name="MG",
        dir_name="mg_tjmg",
        metadata_fields=("titulo", "resumo"),
        build_external_id=lambda r: f"NT-{r['uuid']}-MG",
        build_title=lambda r: r["titulo"],
        get_pdf_path=lambda r: OUTPUT_DIR / "mg_tjmg" / "pdfs" / f"{r['uuid']}.pdf",
    ),
]


def load_csv(path: Path, encoding: str = "utf-8") -> list[dict]:
    with open(path, encoding=encoding, newline="") as f:
        return list(csv.DictReader(f))


def matches_metadata(row: dict, fields: tuple[str, ...]) -> bool:
    haystack = " ".join(row.get(field, "") or "" for field in fields)
    return bool(PATTERN.search(haystack))


def load_extracted_texts(config: TribunalConfig) -> dict[str, dict]:
    texto_path = OUTPUT_DIR / config.dir_name / "pareceres_texto.csv"
    if not texto_path.exists():
        return {}

    extracted: dict[str, dict] = {}
    for row in load_csv(texto_path):
        external_id = row.get("external_id", "")
        if external_id:
            extracted[external_id] = row
    return extracted


def _extract(args: tuple[str, str, str]) -> tuple[str, str, str, str | None]:
    external_id, title, pdf_path = args
    try:
        path = Path(pdf_path)
        if not path.exists():
            return (external_id, title, "", f"PDF não encontrado: {pdf_path}")
        text = extract_text(pdf_path)
        if not text:
            return (external_id, title, "", "Texto vazio após extração")
        return (external_id, title, text, None)
    except Exception as e:
        return (external_id, title, "", f"{type(e).__name__}: {e}")


def collect_tribunal(
    config: TribunalConfig,
) -> tuple[list[dict], list[tuple[str, str, str]], int]:
    meta_path = OUTPUT_DIR / config.dir_name / "metadados.csv"
    if not meta_path.exists():
        print(f"{config.name}: metadados.csv não encontrado, pulando")
        return [], [], 0

    extracted_texts = load_extracted_texts(config)
    rows = load_csv(meta_path, encoding=config.encoding)

    results: list[dict] = []
    to_extract: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    candidates = 0

    for row in rows:
        if row.get("status_download", "") not in config.status_ok:
            continue
        if not matches_metadata(row, config.metadata_fields):
            continue

        candidates += 1
        external_id = config.build_external_id(row)
        if external_id in seen:
            continue
        seen.add(external_id)

        if external_id in extracted_texts:
            existing = extracted_texts[external_id]
            results.append(
                {
                    "external_id": external_id,
                    "title": existing.get("title", config.build_title(row)),
                    "text": existing.get("text", ""),
                }
            )
        else:
            title = config.build_title(row)
            pdf_path = config.get_pdf_path(row)
            to_extract.append((external_id, title, str(pdf_path)))

    print(
        f"{config.name}: {candidates} candidatos; "
        f"{len(results)} textos existentes; {len(to_extract)} a extrair"
    )
    return results, to_extract, candidates


def extract_missing(items: list[tuple[str, str, str]]) -> tuple[list[dict], int]:
    if not items:
        return [], 0

    results: list[dict] = []
    errors = 0
    with ProcessPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(_extract, item): item for item in items}
        for future in as_completed(futures):
            external_id, title, text, error = future.result()
            if error:
                print(f"  ERRO {external_id}: {error}")
                errors += 1
            else:
                results.append(
                    {"external_id": external_id, "title": title, "text": text}
                )
    return results, errors


def write_output(rows: list[dict]) -> None:
    rows = sorted(rows, key=lambda row: row["external_id"])
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["external_id", "title", "text"])
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in ["external_id", "title", "text"]})


def main() -> int:
    consolidated: list[dict] = []
    extraction_queue: list[tuple[str, str, str]] = []
    total_candidates = 0

    for config in TRIBUNALS:
        existing, missing, candidates = collect_tribunal(config)
        consolidated.extend(existing)
        extraction_queue.extend(missing)
        total_candidates += candidates

    extracted, errors = extract_missing(extraction_queue)
    consolidated.extend(extracted)

    seen: set[str] = set()
    deduped: list[dict] = []
    for row in consolidated:
        external_id = row["external_id"]
        if external_id in seen:
            continue
        seen.add(external_id)
        deduped.append(row)

    write_output(deduped)

    print(f"\nCandidatos por metadado: {total_candidates}")
    print(f"Consolidado: {len(deduped)} pareceres salvos em {OUT_PATH}")
    if errors:
        print(f"Extração incompleta: {errors} erro(s)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
