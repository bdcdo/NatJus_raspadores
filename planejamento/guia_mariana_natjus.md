# Guia de Raspagem NatJus — Mariana

## Contexto

Dividimos a raspagem dos NatJus com bases próprias em duas frentes:

- **Bruno**: CE (TJCE), SP (TJSP), RJ (TRF2)
- **Mariana (você!)**: DF, RN, SC, TRF4 (3 sub-bases), RR, TRF3
- **MG (TJMG)**: já concluído por você ✓

Este guia organiza as suas bases **da mais fácil para a mais complexa**, com dicas práticas para cada uma. A ideia é começar pelas quick wins para ganhar ritmo e deixar as mais trabalhosas pro final.

---

## Resumo das suas bases

| # | Base | Acervo | Dificuldade | Esforço estimado | Tecnologia principal |
|---|------|--------|-------------|------------------|---------------------|
| 1 | TRF4 Curitiba | ~50 | FÁCIL | ~0.5h | requests + BS4 |
| 2 | TRF4 Londrina | 45 | FÁCIL | ~0.5h | requests + BS4 |
| 3 | DF (TJDFT) | ~1.000 | FÁCIL | ~2h | requests + BS4 |
| 4 | RN (JFRN) | ~200-300 | FÁCIL-MÉDIA | ~3h | requests (API REST) |
| 5 | SC (JFSC) | ~10-20 | MÉDIA | ~2h | requests + BS4 |
| 6 | TRF4 Telessaúde | 400+ | MÉDIA | ~2h | requests + BS4 |
| 7 | RR (TJRR) | Pequeno | MÉDIA | ~2-3h | requests + BS4 |
| 8 | TRF3 (SP/MS) | 1.799 | MÉDIA | ~4-6h | Playwright + requests |
| — | MG (TJMG) | 3.911 | MÉDIA-DIFÍCIL | ✓ concluído | — |

**Total estimado**: ~5.900+ pareceres · ~15-19h de desenvolvimento

---

## Detalhamento por base

### 1. TRF4 Curitiba — FÁCIL (~0.5h)

**URL**: https://www.trf4.jus.br/trf4/controlador.php?acao=pagina_visualizar&id_pagina=2616

**O que esperar**: Lista HTML simples (`<ul>` com `<a>` links). Todos os ~50 PDFs estão numa única página, com links diretos para arquivos em `/upload/jfpr/2019/12/{medicamento}.pdf`.

**Abordagem**:
1. GET na URL da página
2. BeautifulSoup para extrair todos os `<a href="...pdf">`
3. Download direto dos PDFs

**Dicas**:
- Não tem paginação — tudo numa página só
- Os metadados são mínimos (só nome do medicamento no texto do link), então extraia o que puder do nome do arquivo
- Sem anti-scraping

---

### 2. TRF4 Londrina — FÁCIL (~0.5h)

**URL**: https://www.trf4.jus.br/trf4/controlador.php?acao=pagina_visualizar&id_pagina=2736

**O que esperar**: Mesma estrutura de Curitiba. Lista HTML com 45 PDFs, nomeados `NT01_NATJUSLONDRINA_{medicamento}.pdf` até NT45.

**Abordagem**: Idêntica à de Curitiba.

**Dicas**:
- Os nomes dos arquivos seguem padrão `NT{nn}_NATJUSLONDRINA_...`, então dá pra extrair o número da NT do nome
- Considere reaproveitar o mesmo script de Curitiba, apenas mudando a URL

---

### 3. DF — TJDFT — FÁCIL (~2h)

**URL**: https://www.tjdft.jus.br/informacoes/notas-laudos-e-pareceres/natjus-df

**O que esperar**: CMS Plone. Lista paginada de artigos (~20 páginas × 50 itens = ~1.000 pareceres). Cada item tem link direto para PDF.

**Abordagem**:
1. Iterar pelas páginas usando offset: `?b_start:int=0`, `?b_start:int=50`, `?b_start:int=100`, ...
2. Em cada página, extrair os links dos PDFs com BeautifulSoup
3. Download direto

**Dicas**:
- A paginação é por offset (`b_start:int`), incrementando de 50 em 50
- Pare de iterar quando a página não retornar mais itens ou quando o número de links for 0
- URLs dos PDFs seguem o padrão `https://www.tjdft.jus.br/informacoes/notas-laudos-e-pareceres/natjus-df/{id}.pdf`
- Metadados: o título de cada item contém medicamento + doença. Número do processo e vara estão *dentro* do PDF (não dá pra extrair da listagem)
- Sem anti-scraping, cookies são opcionais

---

### 4. RN — JFRN — FÁCIL-MÉDIA (~3h)

**URL**: https://www.jfrn.jus.br/jud-saude/nota-tecnica

**O que esperar**: SPA (Single Page App) com API REST no backend. A página em si precisa de JavaScript, mas a API pode ser chamada diretamente.

**API REST**:
- **Listagem**: `GET https://servicos.jfrn.jus.br/siteApi/camarastecnicas/?pagina=0&qtd=10&texto=&tratamento=&doenca=&cid=`
- **Tipos de tratamento**: `GET https://servicos.jfrn.jus.br/siteApi/tipostratamento`

**Abordagem**:
1. Chamar a API de listagem diretamente com `requests`, incrementando `pagina` (começando em 0)
2. Definir `qtd` para um valor maior (ex: 50 ou 100) para reduzir o número de requisições
3. Parsear o JSON de resposta para extrair IDs
4. Para cada item, acessar a detail page: `https://judsaude.jfrn.jus.br/judsaude/exibirNotaTecnica?idNotaTecnica={id}`
5. Baixar o PDF da detail page

**Dicas**:
- Teste primeiro se a API aceita `qtd=100` ou `qtd=1000` — pode economizar muitas requisições
- A API não exige autenticação
- Metadados ricos disponíveis no JSON: CID, doença, tipo de tratamento, descrição do tratamento
- A detail page para download do PDF pode exigir Playwright se for uma página renderizada em JS. Teste com `requests` primeiro — se o HTML retornado tiver o link do PDF, ótimo; se não, use Playwright

---

### 5. SC — JFSC — MÉDIA (~2h)

**URL**: https://portal.jfsc.jus.br/novo_portal/conteudo/servicos_judiciais/listaNotasTecnicas.php + listaPareceresTecnicos.php

**O que esperar**: Base muito pequena (~10-20 pareceres). Tabela HTML expansível. O detalhe é que os PDFs não estão hospedados no JFSC — eles apontam para o CNJ.

**Abordagem**:
1. Parsear o HTML das duas páginas (notas técnicas + pareceres técnicos)
2. Extrair os IDs dos pareceres dos links JavaScript: `javascript:abrirJanela('https://www.cnj.jus.br/e-natjus/base_conhecimento_publica_pesquisa.php?acao=gerar_documento_pt&id_parecer_tecnico={id}', 800, 600)`
3. Para cada ID, fazer GET na URL do CNJ para baixar o PDF

**Dicas**:
- Os links estão em atributos `onclick` ou `href` com `javascript:`. Use regex para extrair o ID: algo como `id_parecer_tecnico=(\d+)`
- Teste a URL do CNJ primeiro no navegador para ver se retorna o PDF direto ou se precisa de sessão/cookies
- Se o CNJ bloquear requests direto, tente Playwright
- Metadados disponíveis na tabela: data, tecnologia/medicamento, indicação clínica, ID do parecer
- Base tão pequena que dá pra fazer manualmente se o scraper der muito trabalho, mas o script é bom pra ter o processo documentado

---

### 6. TRF4 Telessaúde — MÉDIA (~2h)

**URL**: https://www.trf4.jus.br/trf4/controlador.php?acao=pagina_visualizar&id_pagina=3574

**O que esperar**: Lista HTML com 400+ notas técnicas, tudo numa página só. Os metadados são ricos (ID, data, CID, diagnóstico, princípio ativo). O detalhe é que os PDFs não são links diretos — eles apontam para o sistema e-NatJus do PJe.

**Abordagem**:
1. Parsear o HTML para extrair metadados e IDs de cada nota técnica
2. Para cada item, acessar a detail page: `https://www.pje.jus.br/e-natjus/notaTecnica-dados.php?idNotaTecnica={id}`
3. Na detail page, localizar o botão "PDF Nota Técnica" e extrair o link do PDF (que pode ter um token dinâmico)
4. Baixar o PDF

**Dicas**:
- A listagem está toda numa única página (sem paginação), o que facilita a extração
- O link do PDF na detail page do e-NatJus pode conter um token temporário. Isso significa que você precisa acessar a detail page e baixar o PDF na mesma sessão
- Use `requests.Session()` para manter cookies entre a detail page e o download
- Se o e-NatJus exigir JavaScript para renderizar o link do PDF, use Playwright
- Metadados ricos: ID da NT, data de conclusão, CID, diagnóstico, princípio ativo — todos extraíveis do HTML da listagem

---

### 7. RR — TJRR — MÉDIA (~2-3h)

**URL**: https://www.tjrr.jus.br/index.php/notas-tecnicas-natjus → redireciona para https://transparencia.tjrr.jus.br/index.php/natjus

**O que esperar**: Site Joomla que redireciona para um portal de transparência. Acervo pequeno (apenas notas de 2025). A estrutura do portal de transparência precisa ser investigada.

**Abordagem**:
1. Acessar a URL de redirecionamento e verificar a estrutura do portal de transparência
2. Parsear HTML para localizar links de PDFs
3. Download direto

**Dicas**:
- Comece acessando `https://transparencia.tjrr.jus.br/index.php/natjus` no navegador para entender a estrutura antes de codar
- Site Joomla padrão, sem anti-scraping significativo
- Base pequena, então mesmo que precise de ajustes manuais será rápido
- Os pareceres incluem número do processo nos metadados
- Como é uma base nova (só 2025), pode crescer — vale fazer o script robusto o suficiente pra rodar de novo no futuro

---

### 8. TRF3 — SP/MS Justiça Federal — MÉDIA (~4-6h)

**URL do Dashboard**: https://app.powerbi.com/view?r=eyJrIjoiMTVkM2Y2NTctYjZkOS00NzExLWJhYmUtM2EzMmRiMTRhMTgwIiwidCI6IjExMjBlOWFjLTRmMGUtNDkxOS1hZDY4LTU4ZTU5YzIwNDZjZiJ9

**O que esperar**: Dashboard Power BI público com 1.799 solicitações. As tabelas mostram ~20 links por vez e precisam de scroll. A boa notícia é que os PDFs em si são URLs estáticas no trf3.jus.br, acessíveis via GET direto sem autenticação.

**Abordagem recomendada (Playwright)**:
1. Abrir o dashboard com Playwright
2. Aguardar carregamento completo (~10-15 segundos)
3. Para cada tabela (Notas técnicas + Notas complementares):
   a. Capturar links visíveis no DOM
   b. Clicar no botão "Rolar para baixo" repetidamente
   c. Após cada scroll, capturar novos links
   d. Parar quando não aparecerem links novos
4. Com a lista completa de URLs, baixar todos os PDFs com `requests` (GET direto)

**Dicas**:
- Esta é a base que **vai exigir Playwright** — o Power BI não tem API pública documentada
- Os PDFs seguem padrões de URL previsíveis:
  - Respostas técnicas: `https://www.trf3.jus.br/documentos/natjus/respostas_tecnicas/RT_{medicamento}_{data}.pdf`
  - Notas técnicas: `https://www.trf3.jus.br/documentos/natjus/notas_tecnicas/RT_{id}_{ano}_{medicamento}_{data}.pdf`
  - Complementares: `https://www.trf3.jus.br/documentos/natjus/notas_tecnicas/NT_{id}_A_{ano}_{medicamento}_{data}.pdf`
- Depois de extrair os links do Power BI, o download dos PDFs é trivial (sem auth, sem rate limit)
- Metadados extraíveis das URLs: ID, ano, medicamento, data
- O dashboard também tem tabelas de CID e Varas — vale capturar para enriquecer os metadados
- **Dica de otimização**: use os filtros do Power BI (Medicamento/Patologia) para segmentar os resultados. Isso pode facilitar o scroll se uma tabela tiver muitos itens
- O dashboard demora pra carregar. Use `page.wait_for_load_state('networkidle')` ou um `wait_for_selector` do primeiro elemento da tabela

---

## Dicas gerais

### Estrutura de output sugerida
Organize os downloads assim:
```
output/
├── trf4_curitiba/
│   ├── pdfs/
│   └── metadados.csv
├── trf4_londrina/
│   ├── pdfs/
│   └── metadados.csv
├── df_tjdft/
│   ├── pdfs/
│   └── metadados.csv
...
```

### Rate limiting e boas práticas
- Adicione `time.sleep(0.5)` ou `time.sleep(1)` entre requisições, mesmo em sites sem rate limiting explícito. É uma questão de respeito ao servidor
- Use `requests.Session()` sempre — mantém cookies e pode melhorar a performance
- Salve progresso incrementalmente (ex: CSV com o que já foi baixado) para poder retomar se o script cair
- Nomeie os PDFs de forma padronizada: `{base}_{id}_{data}.pdf` ou similar

### Lidando com erros
- Implemente retry com backoff para erros HTTP 5xx e timeouts
- Logue URLs que falharem para tentar de novo depois
- Verifique se o arquivo baixado é realmente um PDF (cheque os primeiros bytes: `%PDF`)

### Metadados
- Salve os metadados num CSV com colunas padronizadas: `base, id, titulo, url_pdf, data, cid, doenca, medicamento, caminho_local`
- Nem todas as bases terão todos os campos — deixe vazio o que não tiver

### Playwright (para TRF3)
- Instale com: `pip install playwright && playwright install chromium`
- Use modo headless em produção, mas rode com `headless=False` durante o desenvolvimento para ver o que está acontecendo
- Para o Power BI, espere o carregamento com timeouts generosos (30s+)
