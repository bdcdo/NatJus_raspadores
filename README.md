# NatJus Raspadores ⚖️📋

**Coleta automatizada de pareceres e notas técnicas dos NatJus de tribunais brasileiros**

---

## 📖 O que é o NatJus?

Os **NatJus** (Núcleos de Apoio Técnico do Judiciário) são órgãos que produzem **pareceres e notas técnicas** para auxiliar magistrados em decisões judiciais envolvendo saúde. Cada tribunal pode ter sua própria base de dados, com milhares de documentos sobre medicamentos, tratamentos e tecnologias em saúde.

Este projeto automatiza a coleta desses documentos a partir das bases próprias de cada tribunal, organizando metadados em CSVs e baixando os PDFs dos pareceres.

---

## 📊 Dados coletados

| Estado | Tribunal | Pareceres | PDFs baixados | Taxa de sucesso |
|--------|----------|-----------|---------------|-----------------|
| 🏛️ SP | TJSP | 17.443 | 17.443 | 100% |
| 🏛️ RJ | TRF2 | 12.589 | 11.546 | 91,7% |
| 🏛️ MG | TJMG | 3.911 | 3.887 | 99,4% |
| 🏛️ DF | TJDFT | 3.213 | 3.213 | 100% |
| | **Total** | **37.156** | **36.089** | **97,1%** |

### Bases planejadas (ainda sem raspador)

| Base | Acervo estimado | Dificuldade | Tecnologia |
|------|-----------------|-------------|------------|
| CE (TJCE) | 2.452 | Difícil | Playwright (reCAPTCHA) |
| TRF3 (SP/MS) | 1.799 | Média | Playwright (Power BI) |
| TRF4 Telessaúde | 400+ | Média | requests + BS4 |
| RN (JFRN) | 200-300 | Fácil-Média | requests (API REST) |
| TRF4 Curitiba | ~50 | Fácil | requests + BS4 |
| TRF4 Londrina | 45 | Fácil | requests + BS4 |
| SC (JFSC) | ~10-20 | Média | requests + BS4 |
| RR (TJRR) | Pequeno | Média | requests + BS4 |

---

## 🚀 Instalação

Requer **Python 3.12+** e [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

---

## 💻 Como rodar

Cada raspador é um script independente. Rode a partir da **raiz do projeto**:

```bash
uv run python scrapers/raspar_sp.py    # São Paulo (TJSP)
uv run python scrapers/raspar_mg.py    # Minas Gerais (TJMG)
uv run python scrapers/raspar_rj.py    # Rio de Janeiro (TRF2)
uv run python scrapers/raspar_df.py    # Distrito Federal (TJDFT)
```

Todos os raspadores suportam **retomada automática**: se interrompidos, basta rodar novamente que continuam de onde pararam.

---

## 📁 Estrutura do output

```
output/
├── sp_tjsp/
│   ├── metadados.csv     # Metadados de todos os pareceres
│   └── pdfs/             # PDFs baixados (~17k arquivos)
├── mg_tjmg/
│   ├── metadados.csv
│   └── pdfs/
├── rj_trf2/
│   ├── metadados.csv
│   └── pdfs/
└── df_tjdft/
    ├── metadados.csv
    └── pdfs/
```

Os **CSVs são versionados** no repositório. Os PDFs são excluídos via `.gitignore` por serem muito grandes (~20GB+).

Cada CSV contém pelo menos as colunas: `id`, `titulo`, `url_pdf`, `caminho_local`, `status_download`. Colunas extras variam por base (ex: `cid`, `doenca`, `tecnologia`).

---

## 🔧 Criando novos raspadores

Consulte o [`AGENTS.md`](AGENTS.md) para as convenções de padronização — nomes de funções, colunas CSV obrigatórias, padrões técnicos e modelo de referência.

---

## 📦 Dependências

- [requests](https://docs.python-requests.org/) — cliente HTTP
- [beautifulsoup4](https://www.crummy.com/software/BeautifulSoup/) — parsing de HTML

---

## 👥 Equipe

- [Bruno Daleffi](https://github.com/bdcdo)
- [Mariana Püschel](https://github.com/mapuschel)
