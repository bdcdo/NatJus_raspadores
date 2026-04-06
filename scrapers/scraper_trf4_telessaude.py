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
URL_ALVO = "https://www.trf4.jus.br/trf4/controlador.php?acao=pagina_visualizar&id_pagina=3574"
OUTPUT_FILE = "gemini-work/trf4_telessaude_resultados.csv"

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

def extract_id_from_url(url):
    # Padrão 1: idNotaTecnica=265691
    m = re.search(r'idNotaTecnica=(\d+)', url)
    if m: return m.group(1)
    # Padrão 2: token=nt:3614:1591734231...
    m = re.search(r'token=nt:(\d+):', url)
    if m: return m.group(1)
    return ""

def extract_cid(text):
    # Procura padrão CID: Letra + 2 ou 3 números
    match = re.search(r'\b([A-Z]\d{2}(?:\.\d+)?)\b', text)
    if match:
        return match.group(1).upper()
    return ""

def main():
    print(f"Iniciando raspagem TRF4 Telessaúde: {URL_ALVO}")
    driver = setup_driver()
    resultados = []
    
    try:
        driver.get(URL_ALVO)
        # Espera carregar o conteúdo principal (pode demorar pelo tamanho da página)
        time.sleep(10)
        
        # O conteúdo está dentro da div de conteúdo da página
        # No TRF4 geralmente é .infraAreaPagina ou similar, mas vamos focar nos <p> que contêm as notas
        ps = driver.find_elements(By.TAG_NAME, "p")
        print(f"Encontrados {len(ps)} parágrafos. Analisando notas...")
        
        for p in ps:
            text = p.text.strip()
            if "Nota Técnica" not in text and "Nota tcnica" not in text:
                continue
                
            try:
                link_el = p.find_element(By.TAG_NAME, "a")
                url_pdf = link_el.get_attribute("href")
            except:
                continue # Se não tem link, não é o parágrafo da nota que queremos
            
            # Parsing do texto do parágrafo
            # Exemplo:
            # Nota tcnica: Nota Técnica 265691
            # Data de conclusão: 25/09/2024
            # Diagnóstico: Neoplasia maligna do rim, exceto pelve renal.
            # Princípio Ativo: PEMBROLIZUMABE
            
            lines = text.split('\n')
            
            titulo = ""
            data = ""
            doenca = ""
            medicamento = ""
            cid = ""
            
            for line in lines:
                line = line.strip()
                if "Nota" in line and not titulo:
                    titulo = line
                elif "Data" in line:
                    data = line.replace("Data de conclusão:", "").replace("Data:", "").strip()
                elif "Diagnóstico" in line:
                    doenca = line.replace("Diagnóstico:", "").strip()
                    cid = extract_cid(doenca)
                elif "Princípio Ativo" in line:
                    medicamento = line.replace("Princípio Ativo:", "").strip()
                elif "Descrição" in line and not medicamento:
                    medicamento = line.replace("Descrição:", "").strip()
                elif "Procedimento" in line and not medicamento:
                    medicamento = line.replace("Procedimento:", "").strip()

            if titulo:
                resultados.append({
                    'base': 'TRF4-Telessaúde',
                    'id': extract_id_from_url(url_pdf),
                    'titulo': titulo,
                    'url_pdf': url_pdf,
                    'data': data,
                    'cid': cid,
                    'doenca': doenca,
                    'medicamento': medicamento,
                    'caminho_local': ''
                })

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
    else:
        print("Nenhum resultado encontrado.")

if __name__ == "__main__":
    main()
