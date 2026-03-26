# Convenções para Raspadores NatJus

Guia de padronização para criar novos raspadores neste projeto. Seguir estas convenções garante consistência, facilita manutenção e permite retomada automática em caso de interrupção.

## Estrutura de arquivos

```
scrapers/raspar_{sigla_estado}.py      # Script do raspador
output/{sigla}_{tribunal}/metadados.csv # Metadados coletados
output/{sigla}_{tribunal}/pdfs/         # PDFs baixados
```

Exemplos:
- `scrapers/raspar_sp.py` -> `output/sp_tjsp/`
- `scrapers/raspar_rj.py` -> `output/rj_trf2/`
- `scrapers/raspar_mg.py` -> `output/mg_tjmg/`

## Funções obrigatórias

Todo raspador deve implementar estas funções com estes nomes:

| Função | Responsabilidade |
|--------|-----------------|
| `setup()` | Cria diretórios de output (`PDF_DIR.mkdir(parents=True, exist_ok=True)`) |
| `load_already_downloaded()` | Carrega IDs já processados do CSV para resume. Retorna `set` |
| `download_pdf(session, url, filepath)` | Baixa PDF com retry, valida magic bytes, retorna status |
| `append_csv(entry)` | Adiciona uma linha ao CSV incrementalmente |
| `main()` | Orquestra o scraping (setup, resume, coleta, download) |

Funções adicionais específicas da base são bem-vindas (ex: `parse_year_page()`, `get_pdf_link()`).

## CSV — colunas mínimas obrigatórias

Toda base deve ter pelo menos estas colunas no CSV:

```
id, titulo, url_pdf, caminho_local, status_download
```

- `id`: Identificador único do item na base de origem
- `titulo`: Título ou descrição do parecer/nota técnica
- `url_pdf`: URL de onde o PDF foi baixado
- `caminho_local`: Caminho relativo do PDF salvo (vazio se falhou)
- `status_download`: `sucesso`, `erro`, `ja_existia`, ou `sem_pdf`

Colunas extras por base são incentivadas:

| Coluna | Quando usar |
|--------|-------------|
| `cid` | Quando a base fornece código CID |
| `doenca` | Descrição da doença/condição |
| `data_emissao` | Data de emissão do parecer |
| `resumo` | Resumo/abstract do documento |
| `tecnologia` | Medicamento ou tecnologia em saúde |
| `tipo_acao` | Tipo de ação judicial |
| `ano` | Ano do parecer |
| `numero_parecer` | Número oficial do parecer |

## Padrões técnicos

### HTTP

```python
session = requests.Session()
session.headers.update({
    "User-Agent": "NatJus-{ESTADO}-Scraper/1.0 (pesquisa academica)"
})
```

- Usar `requests.Session()` para manter cookies e connection pooling
- User-Agent descritivo identificando o raspador

### Logging

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)
```

Usar `log.info()`, `log.warning()`, `log.error()` — nunca `print()`.

### Caminhos

```python
from pathlib import Path

OUTPUT_DIR = Path("output/{sigla}_{tribunal}")
PDF_DIR = OUTPUT_DIR / "pdfs"
CSV_PATH = OUTPUT_DIR / "metadados.csv"
```

Usar `pathlib.Path` — nunca `os.path.join()`.

### Retry com backoff

```python
def fetch_with_retry(session, url, params=None):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            log.warning(f"  Tentativa {attempt}/{MAX_RETRIES}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    raise requests.RequestException(f"Falhou após {MAX_RETRIES} tentativas: {url}")
```

- 3 tentativas (`MAX_RETRIES = 3`)
- Backoff exponencial: 2s, 4s entre tentativas
- `TIMEOUT = 30` segundos por requisição

### Delay entre requisições

```python
DELAY = 0.5  # segundos entre requisições normais
```

Mínimo de 0.5s entre requisições. Ajustar para mais se a base tiver rate limiting.

### Download de PDFs com atomic write

```python
def download_pdf(session, url, filepath):
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
                if f.read(4) != b"%PDF":
                    tmp_path.unlink(missing_ok=True)
                    return "erro"
            tmp_path.rename(filepath)
            return "sucesso"
        except requests.RequestException as e:
            log.warning(f"  Tentativa {attempt}/{MAX_RETRIES}: {e}")
            tmp_path.unlink(missing_ok=True)
            if attempt < MAX_RETRIES:
                time.sleep(2 ** attempt)
    return "erro"
```

- Salvar em `.tmp` e renomear (atomic write)
- Validar magic bytes `%PDF`
- Stream download para não estourar memória
- Pular se já existe e é PDF válido

### Resume (retomada)

```python
def load_already_downloaded():
    downloaded = set()
    if CSV_PATH.exists():
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                downloaded.add(row["id"])
    return downloaded
```

- Carregar IDs já processados na inicialização
- Pular itens que já estão no CSV com status `sucesso` ou `ja_existia`
- Append incremental ao CSV (1 linha por item) para minimizar perda em interrupção

## O que NÃO padronizar

Cada base tem sua própria estrutura. Estas coisas variam e devem ser implementadas conforme necessário:

- Lógica de paginação (offset, page number, cursor, etc.)
- Parsing de HTML/JSON específico do site
- Campos de metadados extras além dos obrigatórios
- Tratamento de edge cases (base64, tokens dinâmicos, bundles, etc.)
- Uso de Playwright vs requests (depende do anti-scraping da base)

## Como rodar

```bash
uv run python scrapers/raspar_{estado}.py
```

Os scripts usam caminhos relativos ao diretório raiz do projeto. Sempre rodar a partir da raiz.

## Modelo de referência

Usar `scrapers/raspar_rj.py` como modelo — é o raspador mais maduro, com logging completo, pathlib, atomic writes e status tracking.
