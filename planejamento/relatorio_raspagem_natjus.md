# Relatório de Viabilidade de Raspagem dos NatJus com Bases Próprias

## Contexto

A partir do mapeamento dos 27 estados, identificamos **10 NatJus (12 sub-bases)** que possuem bases de dados próprias com pareceres/notas técnicas acessíveis. Este relatório avalia a dificuldade de construir raspadores para baixar todos os PDFs e metadados de cada base.

---

## Análise Técnica por Base

### 1. RJ — TRF2 (Dificuldade: FÁCIL)

- **URL**: https://www10.trf2.jus.br/comite-estadual-de-saude-rj/nat-jus/pareceres/
- **Acervo**: ~centenas de pareceres, organizados por ano (2020-2025)
- **Estrutura**: Site WordPress, tabela HTML paginada com links diretos para PDFs
- **PDFs**: URLs estáticas previsíveis: `https://static.trf2.jus.br/nas-internet/documento/comite-estadual-saude/pareceres/{ano}/parecer-{id}-{ano}.pdf`
- **Metadados disponíveis**: Título (medicamento/doença), nº do processo (maioria), ano
- **Paginação**: HTML simples com páginas numeradas
- **Anti-scraping**: Nenhum detectado
- **Abordagem**: requests + BeautifulSoup. Listar links da tabela HTML, baixar PDFs via GET direto
- **Estimativa de esforço**: ~2h de desenvolvimento

### 2. DF — TJDFT (Dificuldade: FÁCIL)

- **URL**: https://www.tjdft.jus.br/informacoes/notas-laudos-e-pareceres/natjus-df
- **Acervo**: ~1.000 pareceres (20 páginas x 50 itens)
- **Estrutura**: Plone CMS, lista paginada de artigos com links para PDFs
- **PDFs**: URLs diretas: `https://www.tjdft.jus.br/informacoes/notas-laudos-e-pareceres/natjus-df/{id}.pdf`
- **Metadados disponíveis**: Título (medicamento + doença), nº do processo e vara (dentro do PDF)
- **Paginação**: Offset-based (`?b_start:int=50`, `?b_start:int=100`, etc.)
- **Busca**: Campo de busca com filtro "Nesta seção" disponível
- **Anti-scraping**: Nenhum detectado (cookies opcionais)
- **Abordagem**: requests + BeautifulSoup. Iterar pelas 20 páginas, extrair links de PDFs
- **Estimativa de esforço**: ~2h de desenvolvimento

### 3. SP — TJSP (Dificuldade: FÁCIL-MÉDIA)

- **URL**: https://www.tjsp.jus.br/RHF/natjus
- **Acervo**: **17.011 registros** (maior base encontrada)
- **Estrutura**: DataTables.js com API REST no backend
- **API**: `POST https://www.tjsp.jus.br/RHF/NatJus/Apresentacao/Pesquisar` (retorna JSON/HTML paginado)
- **PDFs**: Via API: `GET https://www.tjsp.jus.br/RHF/NatJus/Administracao/Documento/ObterAnexo/{id}` — retorna PDF binário
- **Metadados disponíveis**: CID, Doença, Tipo Ação, Tecnologia (medicamento)
- **Paginação**: Server-side via DataTables (parâmetros start/length no POST)
- **Filtros**: Colunas filtráveis (CID, Doença, Tipo Ação, Tecnologia) + busca por conteúdo do PDF
- **Anti-scraping**: Nenhum CAPTCHA. Application Insights (telemetria) presente mas não bloqueia
- **Abordagem**: requests direto na API. Enviar POST com parâmetros de paginação, parsear resposta, extrair IDs dos documentos, baixar PDFs via GET
- **Estimativa de esforço**: ~3h (investigar formato exato do POST + parsear resposta)

### 4. MG — TJMG (Dificuldade: MÉDIA-DIFÍCIL)

- **URL**: https://bd.tjmg.jus.br/collections/910e3664-1f94-4f35-99d8-2d0747ec4ddc
- **Acervo**: **3.911 itens** (segunda maior base)
- **Estrutura**: DSpace (repositório institucional) com REST API completa
- **API REST**: Base em `https://bd.tjmg.jus.br/server/api/core/`
  - `/collections/{uuid}` — metadados da coleção
  - `/items/{uuid}` — detalhes do item
  - `/bitstreams/{uuid}/content` — download do PDF
- **Metadados disponíveis**: ID da NT (ex: "NT 2025.0008810"), título, data, organização, resumo, UUID
- **Paginação**: 20 itens/página, ~196 páginas
- **Anti-scraping**: Rate limiting (500 req/60s), F5 CSPM bot detection, token de autenticação para API
- **Abordagem**: Usar a REST API do DSpace com headers adequados. Respeitar rate limit (max 8 req/s). Pode precisar de Playwright se o bot detection bloquear requests simples
- **Estimativa de esforço**: ~4-6h (API REST + lidar com rate limiting + bot detection)

### 5. CE — TJCE (Dificuldade: DIFÍCIL)

- **URL**: https://www.tjce.jus.br/nota-tecnica/
- **Acervo**: **2.452 notas técnicas**
- **Estrutura**: WordPress + DataTables.js (AJAX via `wp-admin/admin-ajax.php`)
- **PDFs**: URLs diretas: `https://portal.tjce.jus.br/uploads/{YYYY}/{MM}/{filename}.pdf`
- **Metadados disponíveis**: Título (tratamento + doença + medicamento), tamanho do arquivo, data (no path da URL)
- **Paginação**: 246 páginas (10 itens/página), server-side via WordPress AJAX
- **Anti-scraping**: **reCAPTCHA v2** (Google), F5 CSPM bot detection, requer JavaScript
- **Abordagem**: Playwright/Selenium obrigatório para resolver reCAPTCHA. Alternativa: investigar se o AJAX endpoint funciona sem CAPTCHA via requests direto com cookies de sessão válidos
- **Estimativa de esforço**: ~6-8h (reCAPTCHA é o maior obstáculo)

### 6. RN — JFRN (Dificuldade: FÁCIL-MÉDIA)

- **URL**: https://www.jfrn.jus.br/jud-saude/nota-tecnica
- **Acervo**: ~200-300 notas (estimativa)
- **Estrutura**: SPA (Single Page App) com API REST no backend
- **API REST**:
  - `GET https://servicos.jfrn.jus.br/siteApi/camarastecnicas/?pagina=0&qtd=10&texto=&tratamento=&doenca=&cid=` (listagem paginada com filtros)
  - `GET https://servicos.jfrn.jus.br/siteApi/tipostratamento` (tipos de tratamento)
- **PDFs**: Via detail page: `https://judsaude.jfrn.jus.br/judsaude/exibirNotaTecnica?idNotaTecnica={id}`
- **Metadados disponíveis**: CID, Doença, Tipo de tratamento, Tratamento (descrição detalhada)
- **Paginação**: Parâmetros `pagina` e `qtd` na API
- **Anti-scraping**: Requer JavaScript para renderização inicial, sem CAPTCHA
- **Abordagem**: requests direto na API REST (endpoint acessível sem auth). Parsear JSON, iterar paginação, baixar PDFs das detail pages
- **Estimativa de esforço**: ~3h

### 7. SC — JFSC (Dificuldade: MÉDIA)

- **URL**: https://portal.jfsc.jus.br/novo_portal/conteudo/servicos_judiciais/listaNotasTecnicas.php + listaPareceresTecnicos.php
- **Acervo**: ~10-20 pareceres (base muito pequena)
- **Estrutura**: HTML estático com tabela expansível
- **PDFs**: Via JavaScript popup para o CNJ: `javascript:abrirJanela('https://www.cnj.jus.br/e-natjus/base_conhecimento_publica_pesquisa.php?acao=gerar_documento_pt&id_parecer_tecnico={id}', 800, 600)`
- **Metadados disponíveis**: Data, Tecnologia/medicamento, Indicação clínica, ID do parecer
- **Paginação**: Nenhuma (tudo em uma página)
- **Anti-scraping**: Nenhum na listagem. PDFs servidos pelo CNJ (domínio externo)
- **Abordagem**: Parsear HTML para extrair IDs dos pareceres. Fazer GET na URL do CNJ para obter os PDFs. Pode precisar de Playwright se o CNJ exigir sessão
- **Estimativa de esforço**: ~2h (base pequena, mas acesso indireto via CNJ)

### 8. TRF3 — SP/MS Justiça Federal (Dificuldade: MÉDIA)

- **URL do Dashboard**: https://app.powerbi.com/view?r=eyJrIjoiMTVkM2Y2NTctYjZkOS00NzExLWJhYmUtM2EzMmRiMTRhMTgwIiwidCI6IjExMjBlOWFjLTRmMGUtNDkxOS1hZDY4LTU4ZTU5YzIwNDZjZiJ9
- **Abrangência**: TRF3 inteiro (Justiça Federal de SP e MS), não apenas MS
- **Acervo**: **1.799 solicitações** (dados atualizados em 10/03/2026)
  - Favorável: 646
  - Desfavorável: 953
  - Favorável/desfavorável: 21
  - Nota técnica Complementar: 50
  - Aguardando resposta técnica: 105
- **Distribuição temporal**: 2019: 6, 2020: 48, 2021: 83, 2022: 221, 2023: 191, 2024: 276, 2025: 820, 2026: 154
- **Estrutura**: Dashboard Power BI público (sem autenticação) com 3 tabelas scrolláveis:
  1. **Notas técnicas** — lista de URLs de PDFs (respostas técnicas e notas técnicas)
  2. **Notas complementares** — lista de URLs de PDFs complementares
  3. **Tabela de CIDs** — CID + Correspondente ao CID
  4. **Tabela de Varas** — Vara/Gabinete + contagem de solicitações
- **PDFs**: URLs estáticas acessíveis via GET direto, sem autenticação:
  - Respostas técnicas: `https://www.trf3.jus.br/documentos/natjus/respostas_tecnicas/RT_{medicamento}_{data}.pdf`
  - Notas técnicas: `https://www.trf3.jus.br/documentos/natjus/notas_tecnicas/RT_{id}_{ano}_{medicamento}_{data}.pdf`
  - Notas complementares: `https://www.trf3.jus.br/documentos/natjus/notas_tecnicas/NT_{id}_A_{ano}_{medicamento}_{data}.pdf`
- **Exemplos de URLs reais encontradas**:
  - `https://www.trf3.jus.br/documentos/natjus/respostas_tecnicas/RT_Ataluren-Distrofia_Muscular_de_Duchenne_05-10-20.pdf`
  - `https://www.trf3.jus.br/documentos/natjus/notas_tecnicas/RT_Canabidiol_2219_2023_06.06.23.pdf`
  - `https://www.trf3.jus.br/documentos/natjus/notas_tecnicas/NT_0350_2026_Vosoritida_13-02-2026.pdf`
  - `https://www.trf3.jus.br/documentos/natjus/notas_tecnicas/NT_3844-A_2024_Elevidys_14-04-2025.pdf`
- **Metadados disponíveis**:
  - Via dashboard: Medicamento (filtro dropdown), Patologia (filtro dropdown), Tipo de resposta (Favorável/Desfavorável/etc.), Vara/Gabinete
  - Via tabela CID: código CID + descrição completa da doença
  - Via URL do PDF: ID numérico, ano, nome do medicamento, data
- **Filtros interativos no Power BI**: Medicamento (dropdown "Todos"), Patologia (dropdown "Todos"), Resposta técnica (dropdown "Todos")
- **Varas com mais solicitações**: 6º Núcleo de Justiça 4.0 (466), 2ª Vara Cível (183), 25ª Vara Cível (128), 1ª Vara Federal de Barretos (58), 12ª Vara Cível (31), 1ª Vara Federal de Limeira (31)
- **Anti-scraping**: Nenhum para os PDFs (URLs estáticas no trf3.jus.br). O desafio é apenas extrair a lista completa de URLs do Power BI
- **Desafio principal**: As tabelas do Power BI exibem ~20 links por vez com scroll. Para capturar todos os ~1.799 links, é necessário:
  - **Opção A (recomendada)**: Playwright para scrollar as tabelas automaticamente, capturando os links à medida que novos itens aparecem no DOM
  - **Opção B**: Interceptar as chamadas de API do Power BI (protocolo proprietário Azure Analysis Services) para obter dados em batch
  - **Opção C**: Usar os filtros do Power BI (Medicamento/Patologia) para segmentar os resultados em lotes menores
- **Abordagem técnica recomendada**:
  1. Abrir dashboard com Playwright
  2. Aguardar carregamento completo (~10-15s)
  3. Para cada tabela (Notas técnicas + Notas complementares):
     a. Capturar links visíveis via snapshot/DOM
     b. Clicar "Rolar para baixo" (botão ref=e148/e323) repetidamente
     c. Após cada scroll, capturar novos links
     d. Parar quando não houver mais links novos
  4. Opcionalmente: iterar pelos filtros de Medicamento para obter metadados por medicamento
  5. Baixar todos os PDFs via requests (GET direto, sem headers especiais)
- **Estimativa de esforço**: ~4-6h
  - 2h: Script Playwright para extrair todos os links das tabelas scrolláveis
  - 1h: Parser de metadados a partir das URLs e tabelas
  - 1-2h: Download dos PDFs + tratamento de erros

### 9. RR — TJRR (Dificuldade: MÉDIA)

- **URL**: https://www.tjrr.jus.br/index.php/notas-tecnicas-natjus → redireciona para https://transparencia.tjrr.jus.br/index.php/natjus
- **Acervo**: Pequeno (somente notas de 2025)
- **Estrutura**: Joomla CMS, página informativa que redireciona para portal de transparência
- **PDFs**: No portal de transparência, estrutura a ser confirmada
- **Metadados disponíveis**: Inclui nº do processo nos pareceres
- **Anti-scraping**: Baixo (site Joomla padrão)
- **Abordagem**: Navegar até portal de transparência, parsear HTML para links de PDFs
- **Estimativa de esforço**: ~2-3h (depende da estrutura do portal de transparência)

### 10. TRF4 — 3 sub-bases (Dificuldade: FÁCIL)

#### 10a. Curitiba (~50 PDFs)

- **URL**: https://www.trf4.jus.br/trf4/controlador.php?acao=pagina_visualizar&id_pagina=2616
- **Estrutura**: Lista HTML simples (`<ul>` com `<a>` links), PDFs diretos em `/upload/jfpr/2019/12/{medicamento}.pdf`
- **Metadados**: Apenas nome do medicamento
- **Paginação**: Nenhuma
- **Anti-scraping**: Nenhum

#### 10b. Londrina (45 PDFs)

- **URL**: https://www.trf4.jus.br/trf4/controlador.php?acao=pagina_visualizar&id_pagina=2736
- **Estrutura**: Lista HTML simples, PDFs diretos (`NT01_NATJUSLONDRINA_{medicamento}.pdf` a NT45)
- **Metadados**: Nº da NT, medicamento
- **Paginação**: Nenhuma
- **Anti-scraping**: Nenhum

#### 10c. Telessaúde (400+ NTs)

- **URL**: https://www.trf4.jus.br/trf4/controlador.php?acao=pagina_visualizar&id_pagina=3574
- **Estrutura**: Lista HTML com metadados estruturados por item
- **PDFs indiretos**: Links para `https://www.pje.jus.br/e-natjus/notaTecnica-dados.php?idNotaTecnica={id}` (detail page no e-NatJus, com botão "PDF Nota Técnica")
- **Metadados**: ID da NT, data de conclusão, CID, diagnóstico, princípio ativo
- **Paginação**: Nenhuma (tudo em uma página)
- **Anti-scraping**: Nenhum

#### Abordagem unificada TRF4

requests + BeautifulSoup para Curitiba e Londrina (trivial). Para Telessaúde: parsear IDs, acessar detail page no e-NatJus, extrair link do PDF (token dinâmico no link).

**Estimativa de esforço total TRF4**: ~3h (1h Curitiba+Londrina, 2h Telessaúde)

---

## Tabela Resumo (ranking por facilidade)

| # | Base | Acervo | Dificuldade | PDFs | Metadados | Anti-scraping | Esforço |
|---|------|--------|-------------|------|-----------|---------------|---------|
| 1 | **TRF4 Curitiba** | ~50 | FÁCIL | Links diretos | Baixo (nome) | Nenhum | ~0.5h |
| 2 | **TRF4 Londrina** | 45 | FÁCIL | Links diretos | Baixo (NT#, nome) | Nenhum | ~0.5h |
| 3 | **RJ (TRF2)** | ~centenas | FÁCIL | Links diretos | Médio (título, processo) | Nenhum | ~2h |
| 4 | **DF (TJDFT)** | ~1.000 | FÁCIL | Links diretos | Médio (título) | Nenhum | ~2h |
| 5 | **RN (JFRN)** | ~200-300 | FÁCIL-MÉDIA | Via detail page | Alto (CID, doença, tipo, tratamento) | JS obrigatório | ~3h |
| 6 | **SP (TJSP)** | 17.011 | FÁCIL-MÉDIA | Via API | Alto (CID, doença, tipo, tecnologia) | Nenhum | ~3h |
| 7 | **SC (JFSC)** | ~10-20 | MÉDIA | Via CNJ (ext.) | Médio (data, tecn., indicação) | Nenhum | ~2h |
| 8 | **TRF4 Telessaúde** | 400+ | MÉDIA | Via e-NatJus (token) | Alto (ID, data, CID, dx, princípio ativo) | Nenhum | ~2h |
| 9 | **RR (TJRR)** | Pequeno | MÉDIA | Portal transparência | Médio (nº processo) | Baixo | ~2-3h |
| 10 | **MG (TJMG)** | 3.911 | MÉDIA-DIFÍCIL | Via REST API (UUID) | Alto (ID, título, data, resumo) | Rate limit + bot detect | ~4-6h |
| 11 | **CE (TJCE)** | 2.452 | DIFÍCIL | Links diretos | Baixo (título) | reCAPTCHA v2 + bot | ~6-8h |
| 12 | **TRF3 (SP/MS)** | 1.799 | MÉDIA | URLs estáticas (trf3.jus.br) | Alto (CID, vara, medicamento, resposta) | Nenhum (PDFs diretos) | ~4-6h |

---

## Recomendação de Prioridade para Implementação

### Fase 1 — Quick wins (1-2 dias)

**Bases**: TRF4 (3 bases), RJ, DF
- **Total**: ~1.500+ pareceres
- **Esforço**: ~7h
- **Tecnologia**: Python + requests + BeautifulSoup

### Fase 2 — APIs acessíveis (1-2 dias)

**Bases**: SP, RN
- **Total**: ~17.300+ pareceres
- **Esforço**: ~6h
- **Tecnologia**: Python + requests (chamadas diretas à API)

### Fase 3 — Acesso indireto (1-2 dias)

**Bases**: SC, Telessaúde/TRF4, RR, **TRF3 (SP/MS)**
- **Total**: ~2.230+ pareceres
- **Esforço**: ~10-12h
- **Tecnologia**: Python + requests + **Playwright** (para extração de links do Power BI)

### Fase 4 — Desafiadores (2-3 dias)

**Bases**: MG, CE
- **Total**: ~6.363 pareceres
- **Esforço**: ~10-14h
- **Tecnologia**: Python + Playwright (reCAPTCHA, bot detection)

---

**Total estimado do acervo raspável (Fases 1-4)**: ~27.400+ pareceres/notas técnicas
**Esforço total estimado (Fases 1-4)**: ~33-39h de desenvolvimento
