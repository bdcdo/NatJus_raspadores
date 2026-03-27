import requests
import re
import csv
import time
import os

# Configurações para TJDFT
BASE_URL = "https://www.tjdft.jus.br/informacoes/notas-laudos-e-pareceres/natjus-df"
OUTPUT_FILE = "gemini-work/tjdft_natjus_resultados.csv"

def extract_id_from_url(url):
    match = re.search(r'df/(\d+)\.pdf', url)
    return match.group(1) if match else ""

def main():
    start = 0
    resultados = []
    print(f"Iniciando raspagem TJDFT padronizada...")
    
    while True:
        url_paginada = f"{BASE_URL}?b_start:int={start}"
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url_paginada, headers=headers, timeout=30)
            response.raise_for_status()
            html_content = response.text
            
            padrao = r'<a href="([^"]+)" class="[^"]*url"[^>]*>([^<]+)</a>'
            matches = re.findall(padrao, html_content)
            
            if not matches: break
            
            for link, nome in matches:
                nome_limpo = re.sub(r'\s+', ' ', nome).strip()
                link_base = link if link.startswith('http') else "https://www.tjdft.jus.br" + link
                link_pdf = link_base.replace('/view', '')
                
                # Tenta extrair medicamento/doença
                med, doenca = nome_limpo, ""
                if "/" in nome_limpo:
                    partes = nome_limpo.split("/", 1)
                    med, doenca = partes[0].strip(), partes[1].strip()
                
                resultados.append({
                    'base': 'TJDFT',
                    'id': extract_id_from_url(link_pdf),
                    'titulo': nome_limpo,
                    'url_pdf': link_pdf,
                    'data': '',
                    'cid': '',
                    'doenca': doenca,
                    'medicamento': med,
                    'caminho_local': ''
                })
            
            if len(matches) < 40: break
            start += 50
            time.sleep(0.5)
            print(f"Processados {start} registros...")
        except Exception as e:
            print(f"Erro: {e}")
            break
            
    if resultados:
        headers = ['base', 'id', 'titulo', 'url_pdf', 'data', 'cid', 'doenca', 'medicamento', 'caminho_local']
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(resultados)
        print(f"Sucesso! {len(resultados)} registros salvos.")

if __name__ == "__main__":
    main()
