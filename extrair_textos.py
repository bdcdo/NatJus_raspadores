"""Extrai texto de todos os PDFs de pareceres NatJus e gera CSV unificado.

Uso:
    uv run python extrair_textos.py            # processa tudo
    uv run python extrair_textos.py --limit 10  # testa com 10 PDFs por tribunal
"""

import argparse
import csv
import logging
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pymupdf4llm

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

# O texto integral de um parecer passa do limite default de 131.072 caracteres por
# campo do modulo csv. Sem elevar o teto, load_already_extracted() morre com
# _csv.Error ao reler o pareceres_texto.csv, ou seja, exatamente na retomada de que
# uma corrida longa depende. O laco desce o valor porque field_size_limit e limitado
# ao C long da plataforma, e sys.maxsize estoura onde ele tem 32 bits.
_limit = sys.maxsize
while True:
    try:
        csv.field_size_limit(_limit)
        break
    except OverflowError:
        _limit //= 2

PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
FINAL_CSV = OUTPUT_DIR / "pareceres.csv"
ERROR_LOG = OUTPUT_DIR / "extraction_errors.log"
# Registro estruturado das falhas desta rodada, uma linha por documento. O
# extraction_errors.log ao lado nao serve para isso: o FileHandler manda o log
# inteiro para la, e o arquivo em disco e de marco e abril. E daqui que sai a
# contagem "falha de extracao" do censo. Arquivo novo, entao nao mexe no
# fieldnames do CSV intermediario de que a retomada depende.
FAILURE_CSV = OUTPUT_DIR / "extraction_failures.csv"
WORKERS = 12

log = logging.getLogger("extrair_textos")


# ---------------------------------------------------------------------------
# Limpeza de texto (copiado de projeto 38 — base_teste/pdf_to_csv.py)
# ---------------------------------------------------------------------------


def move_footnotes_to_end(text: str) -> str:
    """Move blockquote footnotes (> N ...) to end of document as endnotes."""
    lines = text.split("\n")
    bq_indices: set[int] = set()
    raw_contents: list[str] = []

    for i, line in enumerate(lines):
        if line.startswith("> "):
            bq_indices.add(i)
            content = line[2:].strip()
            if raw_contents and not re.match(r"\d", content):
                raw_contents[-1] += " " + content
            else:
                raw_contents.append(content)

    if not raw_contents:
        return text

    footnotes: list[tuple[int, str]] = []
    for raw in raw_contents:
        parts = re.split(r"(?<=\. )(?=\d{1,2}[A-Za-z ])", raw)
        for part in parts:
            m = re.match(r"^(\d{1,2})\s*(.*)", part.strip())
            if m:
                footnotes.append((int(m.group(1)), m.group(2).strip()))

    if not footnotes:
        return text

    new_lines = [line for i, line in enumerate(lines) if i not in bq_indices]

    i = 0
    while i < len(new_lines):
        line = new_lines[i].rstrip()
        if line and not re.search(r"[.!?:]\s*$", line):
            j = i + 1
            while j < len(new_lines) and not new_lines[j].strip():
                j += 1
            if (
                j < len(new_lines)
                and new_lines[j].strip()
                and new_lines[j].strip()[0].islower()
            ):
                new_lines[i] = line + " " + new_lines[j].strip()
                del new_lines[i + 1 : j + 1]
                continue
        i += 1

    text = "\n".join(new_lines)

    notes_section = "\n\n---\n\n**Notas:**\n\n"
    for num, content in sorted(footnotes):
        notes_section += f"[{num}] {content}\n\n"

    return text.rstrip() + notes_section.rstrip()


def clean_text(text: str) -> str:
    text = re.sub(r"\*\*==> picture.*?<==\*\*\s*\n?", "", text)
    text = re.sub(
        r"\*\*----- Start of picture text -----\*\*.*?\*\*----- End of picture text -----\*\*\s*\n?",
        "",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(r"^Subsecretaria Jurídica.*$\n?", "", text, flags=re.MULTILINE)
    text = re.sub(
        r"^Núcleo de Assessoria Técnica em Ações de Saúde\s*$\n?",
        "",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(r"Powered by TCPDF \(www\.tcpdf\.org\)\s*", "", text)
    text = re.sub(r"<br>\s*", "", text)
    text = move_footnotes_to_end(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text(pdf_path: str) -> str:
    md = pymupdf4llm.to_markdown(pdf_path, header=False, footer=False)
    return clean_text(md)


# ---------------------------------------------------------------------------
# Configuração por tribunal
# ---------------------------------------------------------------------------


@dataclass
class TribunalConfig:
    name: str
    dir_name: str
    build_external_id: Callable[[dict], str]
    build_title: Callable[[dict], str]
    get_pdf_path: Callable[[dict], Path]
    status_ok: tuple[str, ...] = ("sucesso",)
    encoding: str = "utf-8"


# Ordem deliberada, e a razao dela e historica: o MG era o ultimo e ficou com 3 linhas
# extraidas de 3.887 PDFs, porque a corrida de abril morreu dentro do RJ e nunca o
# alcancou. O RJ vai por ultimo por ser o mais caro (3,24 s/PDF de relogio contra 0,78
# do SP) e o menos produtivo, ja que boa parte do acervo nem tem camada de texto.
# Como a retomada e por external_id ja presente no CSV de saida, reordenar nao reextrai
# nada do que ja foi feito.
TRIBUNALS = [
    TribunalConfig(
        name="MG",
        dir_name="mg_tjmg",
        build_external_id=lambda r: f"NT-{r['uuid']}-MG",
        build_title=lambda r: r["titulo"],
        get_pdf_path=lambda r: OUTPUT_DIR / "mg_tjmg" / "pdfs" / f"{r['uuid']}.pdf",
        # raspar_mg.py grava "sucesso" (:145) e "ja_existia" (:123, PDF ja em disco).
        # Sem declarar os dois, o default ("sucesso",) descarta o segundo em silencio:
        # o PDF fica no disco e nunca e extraido, sem erro nenhum.
        status_ok=("sucesso", "ja_existia"),
    ),
    TribunalConfig(
        name="DF",
        dir_name="df_tjdft",
        build_external_id=lambda r: f"NT-{r['id']}-DF",
        build_title=lambda r: r["titulo"],
        get_pdf_path=lambda r: OUTPUT_DIR / "df_tjdft" / "pdfs" / f"{r['id']}.pdf",
        # raspar_df.py:161 grava "ok" no sucesso e nunca "sucesso". As 3.213 linhas
        # do CSV atual sao "sucesso", de versao anterior do raspador, entao os dois
        # rotulos convivem no mesmo arquivo e ambos precisam estar aqui.
        status_ok=("sucesso", "ok"),
    ),
    TribunalConfig(
        name="SP",
        dir_name="sp_tjsp",
        build_external_id=lambda r: f"NT-{r['id']}-SP",
        build_title=lambda r: r["nome_arquivo"].removesuffix(".pdf"),
        get_pdf_path=lambda r: OUTPUT_DIR / "sp_tjsp" / "pdfs" / f"{r['id']}.pdf",
        status_ok=("sucesso", "ok"),
    ),
    TribunalConfig(
        name="RJ",
        dir_name="rj_trf2",
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
]


# ---------------------------------------------------------------------------
# Worker (roda em subprocesso)
# ---------------------------------------------------------------------------


def process_item(args: tuple[str, str, str]) -> tuple[str, str, str, str | None]:
    """Extrai texto de um PDF. Retorna (external_id, title, text, error)."""
    external_id, title, pdf_path_str = args
    try:
        pdf_path = Path(pdf_path_str)
        if not pdf_path.exists():
            return (external_id, title, "", f"Arquivo não encontrado: {pdf_path}")
        text = extract_text(pdf_path_str)
        if not text:
            return (external_id, title, "", "Texto vazio após extração")
        return (external_id, title, text, None)
    except Exception as e:
        return (external_id, title, "", f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Processamento por tribunal
# ---------------------------------------------------------------------------


def load_already_extracted(csv_path: Path) -> set[str]:
    """Carrega external_ids já extraídos de um CSV intermediário."""
    if not csv_path.exists():
        return set()
    ids = set()
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ids.add(row["external_id"])
    return ids


def process_tribunal(
    config: TribunalConfig,
    pool: ProcessPoolExecutor,
    limit: int | None = None,
) -> tuple[int, int]:
    """Processa um tribunal. Retorna (extraídos, erros)."""
    metadados_path = OUTPUT_DIR / config.dir_name / "metadados.csv"
    intermediate_csv = OUTPUT_DIR / config.dir_name / "pareceres_texto.csv"

    if not metadados_path.exists():
        log.warning(f"{config.name}: metadados.csv não encontrado, pulando")
        return 0, 0

    already_done = load_already_extracted(intermediate_csv)

    # Montar lista de trabalho
    work_items: list[tuple[str, str, str]] = []
    with open(metadados_path, encoding=config.encoding) as f:
        for row in csv.DictReader(f):
            if row.get("status_download", "") not in config.status_ok:
                continue
            ext_id = config.build_external_id(row)
            if ext_id in already_done:
                continue
            title = config.build_title(row)
            pdf_path = config.get_pdf_path(row)
            work_items.append((ext_id, title, str(pdf_path)))

    if limit:
        work_items = work_items[:limit]

    total = len(work_items)
    log.info(
        f"{config.name}: {total} a processar, {len(already_done)} já extraídos"
    )

    if not work_items:
        return 0, 0

    # Gravar CSV intermediário (append)
    write_header = not intermediate_csv.exists() or intermediate_csv.stat().st_size == 0
    done = 0
    errors = 0

    fail_header = not FAILURE_CSV.exists() or FAILURE_CSV.stat().st_size == 0

    with open(intermediate_csv, "a", newline="", encoding="utf-8") as f, open(
        FAILURE_CSV, "a", newline="", encoding="utf-8"
    ) as ff:
        writer = csv.DictWriter(f, fieldnames=["external_id", "title", "text"])
        if write_header:
            writer.writeheader()
        fail_writer = csv.DictWriter(
            ff, fieldnames=["external_id", "acervo", "pdf_path", "erro"]
        )
        if fail_header:
            fail_writer.writeheader()

        futures = {pool.submit(process_item, item): item for item in work_items}
        for future in as_completed(futures):
            ext_id, title, text, error = future.result()
            if error:
                log.warning(f"  ERRO {ext_id}: {error}")
                fail_writer.writerow(
                    {
                        "external_id": ext_id,
                        "acervo": config.dir_name,
                        "pdf_path": futures[future][2],
                        "erro": error,
                    }
                )
                ff.flush()
                errors += 1
            else:
                writer.writerow(
                    {"external_id": ext_id, "title": title, "text": text}
                )
                f.flush()
                done += 1

            processed = done + errors
            if processed % 500 == 0 or processed == total:
                log.info(f"  {config.name}: {processed}/{total} ({errors} erros)")

    log.info(f"{config.name}: concluído — {done} extraídos, {errors} erros")
    return done, errors


# ---------------------------------------------------------------------------
# Merge final
# ---------------------------------------------------------------------------


def merge_intermediates() -> int:
    """Junta CSVs intermediários em output/pareceres.csv."""
    total = 0
    with open(FINAL_CSV, "w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=["external_id", "title", "text"])
        writer.writeheader()
        for config in TRIBUNALS:
            intermediate = OUTPUT_DIR / config.dir_name / "pareceres_texto.csv"
            if not intermediate.exists():
                continue
            with open(intermediate, encoding="utf-8") as inp:
                for row in csv.DictReader(inp):
                    writer.writerow(row)
                    total += 1
    log.info(f"CSV final: {FINAL_CSV} ({total} documentos)")
    return total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Extrai texto dos PDFs NatJus")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limitar a N PDFs por tribunal (para testes)",
    )
    parser.add_argument(
        "--tribunal",
        nargs="+",
        metavar="NOME",
        choices=[c.name for c in TRIBUNALS],
        default=None,
        help=(
            "Extrair apenas estes acervos, na ordem de TRIBUNALS. Serve para nao "
            "sobrepor extracao e coleta dentro de um mesmo acervo, que faria a "
            "extracao ler um metadados.csv sendo escrito por append. Continua "
            "sendo um pool so: rodar varios processos disputaria os mesmos nucleos "
            "e sairia mais lento, nao mais rapido."
        ),
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=WORKERS,
        help=f"Número de workers paralelos (padrão: {WORKERS})",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(ERROR_LOG, encoding="utf-8"),
        ],
    )

    selecionados = TRIBUNALS
    if args.tribunal:
        escolhidos = set(args.tribunal)
        selecionados = [c for c in TRIBUNALS if c.name in escolhidos]

    log.info(
        f"=== Extração de texto: {len(selecionados)} tribunais "
        f"({', '.join(c.name for c in selecionados)}), {args.workers} workers ==="
    )
    if args.limit:
        log.info(f"    MODO TESTE: limite de {args.limit} PDFs por tribunal")

    total_done = 0
    total_errors = 0

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        for config in selecionados:
            done, errors = process_tribunal(config, pool, limit=args.limit)
            total_done += done
            total_errors += errors

    total = merge_intermediates()
    log.info(
        f"=== CONCLUÍDO: {total} documentos no CSV, {total_errors} erros no total ==="
    )


if __name__ == "__main__":
    main()
