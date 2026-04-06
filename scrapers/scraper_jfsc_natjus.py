import time
import csv
import os
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Configurações
URLS_JFSC = [
    "https://portal.jfsc.jus.br/novo_portal/conteudo/servicos_judiciais/listaNotasTecnicas.php",
    "https://portal.jfsc.jus.br/novo_portal/conteudo/servicos_judiciais/listaPareceresTecnicos.php"
]
OUTPUT_FILE = "gemini-work/jfsc_natjus_resultados.csv"
BASE_DOMAIN = "https://portal.jfsc.jus.br"

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    # Ignorar erros de certificado SSL (comum em sites do governo)
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def extract_id_from_url(url):
    m = re.search(r'idValorCampoMateria=(\d+)', url)
    if m: return m.group(1)
    m = re.search(r'id_parecer_tecnico=(\d+)', url)
    if m: return m.group(1)
    return ""

def extract_cid(text):
    # Procura padrão CID: Letra + 2 ou 3 números (opcionalmente ponto + número)
    # Exemplos: J44, I48.0, CID 10 J45
    match = re.search(r'(?:CID\s*(?:10)?\s*[:\-\s]*)?\b([A-Z]\d{2,3}(?:\.\d+)?)\b', text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""

def scrape_jfsc_page(driver, url):
    print(f"Processando JFSC: {url}")
    driver.get(url)
    time.sleep(5)
    
    resultados_pagina = []
    
    try:
        # No JFSC os itens estão em TRs com valign='top'
        rows = driver.find_elements(By.CSS_SELECTOR, "tr[valign='top']")
        print(f"Encontrados {len(rows)} itens.")
        
        for row in rows:
            try:
                # O link e os dados estão no segundo ou único TD relevante
                tds = row.find_elements(By.TAG_NAME, "td")
                if not tds: continue
                
                # Procura o <a> dentro de qualquer TD da linha
                link_el = None
                target_td = None
                for td in tds:
                    try:
                        link_el = td.find_element(By.TAG_NAME, "a")
                        target_td = td
                        break
                    except: continue
                
                if not link_el: continue
                
                # Extração do link
                raw_href = link_el.get_attribute("href") or ""
                link_pdf = ""
                
                # DEBUG: print(f"Raw href: {raw_href}")

                if "abrirJanela" in raw_href:
                    # Pode vir com %27 ou '
                    # Usar grupo não capturador para as aspas/codificação
                    m = re.search(r"abrirJanela\((?:'|%27)(.*?)(?:'|%27),", raw_href)
                    if m:
                        link_pdf = m.group(1)
                        if link_pdf.startswith('/'):
                            link_pdf = BASE_DOMAIN + link_pdf
                else:
                    link_pdf = raw_href

                # Extração da data (dentro de um span)
                date = ""
                try:
                    date_el = target_td.find_element(By.TAG_NAME, "span")
                    date = date_el.text.strip()
                except: pass
                
                # Extração do título
                full_text = link_el.text.strip()
                # Limpar o título removendo a data se ela vier junto no .text
                title = full_text.replace(date, "").strip()
                title = re.sub(r'\s+', ' ', title)
                
                # Tentar quebrar medicamento e doença
                medicamento = ""
                doenca = ""
                if " - " in title:
                    parts = title.split(" - ")
                    if len(parts) >= 3:
                        medicamento = parts[1].strip()
                        doenca = parts[2].strip()
                    elif len(parts) == 2:
                        medicamento = parts[0].strip()
                        doenca = parts[1].strip()

                cid_encontrado = extract_cid(title)

                resultados_pagina.append({
                    'base': 'JFSC',
                    'id': extract_id_from_url(link_pdf),
                    'titulo': title,
                    'url_pdf': link_pdf,
                    'data': date,
                    'cid': cid_encontrado,
                    'doenca': doenca,
                    'medicamento': medicamento,
                    'caminho_local': ''
                })
            except Exception as e:
                # print(f"Erro ao processar linha: {e}")
                continue
                
    except Exception as e:
        print(f"Erro na página {url}: {e}")
        
    return resultados_pagina

def main():
    print("Iniciando raspagem JFSC (Simulando padrão JFRN)...")
    driver = setup_driver()
    todos_resultados = []
    
    try:
        for url in URLS_JFSC:
            res = scrape_jfsc_page(driver, url)
            if res:
                todos_resultados.extend(res)
    finally:
        driver.quit()

    if todos_resultados:
        headers = ['base', 'id', 'titulo', 'url_pdf', 'data', 'cid', 'doenca', 'medicamento', 'caminho_local']
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(todos_resultados)
        print(f"Sucesso! {len(todos_resultados)} registros salvos em {OUTPUT_FILE}")
    else:
        print("Nenhum resultado encontrado.")

if __name__ == "__main__":
    main()
