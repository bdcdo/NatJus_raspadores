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
URL_ALVO = "https://www.jfrn.jus.br/jud-saude/nota-tecnica"
OUTPUT_FILE = "gemini-work/jfrn_natjus_resultados.csv"

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def extract_id_from_url(url):
    match = re.search(r'idNotaTecnica=(\d+)', url)
    return match.group(1) if match else ""

def main():
    print(f"Iniciando raspagem JFRN (Formato Padronizado): {URL_ALVO}")
    driver = setup_driver()
    resultados = []
    paginas_processadas = set()
    
    try:
        driver.get(URL_ALVO)
        time.sleep(15) 
        
        pagina_atual = 1
        while True:
            try:
                active_page = driver.find_element(By.CSS_SELECTOR, ".pagination .active, .pager .current").text.strip()
            except:
                active_page = str(pagina_atual)
            
            if active_page in paginas_processadas: break
                
            print(f"Processando Página {active_page}...")
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            time.sleep(2)
            
            rows = driver.find_elements(By.CSS_SELECTOR, "table tbody tr")
            for row in rows:
                cols = row.find_elements(By.TAG_NAME, "td")
                if len(cols) >= 4:
                    cid = cols[0].text.strip()
                    doenca = cols[1].text.strip()
                    tipo = cols[2].text.strip()
                    tratamento = cols[3].text.strip()
                    
                    link_pdf = ""
                    try:
                        link_el = row.find_element(By.TAG_NAME, "a")
                        link_pdf = link_el.get_attribute("href") or ""
                    except: pass
                    
                    if cid or doenca or tratamento:
                        resultados.append({
                            'base': 'JFRN',
                            'id': extract_id_from_url(link_pdf) if link_pdf else "",
                            'titulo': f"{tratamento} - {doenca}",
                            'url_pdf': link_pdf,
                            'data': '', # Não disponível na listagem
                            'cid': cid,
                            'doenca': doenca,
                            'medicamento': tratamento,
                            'caminho_local': ''
                        })
            
            paginas_processadas.add(active_page)
            if pagina_atual >= 55: break

            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, "button.p-paginator-next")
                if "p-disabled" not in next_btn.get_attribute("class"):
                    driver.execute_script("arguments[0].click();", next_btn)
                    time.sleep(5)
                    pagina_atual += 1
                else: break
            except: break

    except Exception as e:
        print(f"Erro: {e}")
    finally:
        driver.quit()

    if resultados:
        headers = ['base', 'id', 'titulo', 'url_pdf', 'data', 'cid', 'doenca', 'medicamento', 'caminho_local']
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(resultados)
        print(f"Sucesso! {len(resultados)} registros salvos em {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
