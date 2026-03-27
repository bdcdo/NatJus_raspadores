import requests
import re
import csv
import time
import os

# Configurações para TJDFT
BASE_URL = "https://www.tjdft.jus.br/informacoes/notas-laudos-e-pareceres/natjus-df"
OUTPUT_FILE = "gemini-work/tjdft_natjus_resultados.csv"

def main():
    start = 0
    resultados = []
    
    while True:
        url_paginada = f"{BASE_URL}?b_start:int={start}"
        print(f"Processando registros começando em {start}...")
        
        try:
            # Simulando um navegador para evitar bloqueios
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url_paginada, headers=headers, timeout=30)
            response.raise_for_status()
            html_content = response.text
            
            # Regex para capturar o link e o nome do documento
            padrao = r'<a href="([^"]+)" class="[^"]*url"[^>]*>([^<]+)</a>'
            matches = re.findall(padrao, html_content)
            
            if not matches:
                break

            print(f"  > Encontrados {len(matches)} itens nesta página.")
            
            for link, nome in matches:
                nome_limpo = re.sub(r'\s+', ' ', nome).strip()
                
                # Garante que o link é absoluto
                link_base = link if link.startswith('http') else "https://www.tjdft.jus.br" + link
                
                # AJUSTE DEFINITIVO: Apenas removemos o '/view' para o link ser o PDF direto
                if link_base.endswith('/view'):
                    link_pdf_direto = link_base.replace('/view', '')
                else:
                    link_pdf_direto = link_base
                
                resultados.append({
                    'documento': nome_limpo,
                    'link_pdf': link_pdf_direto
                })
            
            if len(matches) < 40:
                break
                
            start += 50
            time.sleep(0.5)

        except Exception as e:
            print(f"Erro ao processar página (start={start}): {e}")
            break
            
    if resultados:
        chaves = ['documento', 'link_pdf']
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=chaves)
            writer.writeheader()
            writer.writerows(resultados)
            
        print(f"\nSucesso! Arquivo atualizado em: {OUTPUT_FILE}")
        print(f"Total de registros com links DIRETOS (PDF): {len(resultados)}")

if __name__ == "__main__":
    main()
