import requests
import re
import csv
import os

# Configurações
URL_ALVO = "https://www.trf4.jus.br/trf4/controlador.php?acao=pagina_visualizar&id_pagina=2616"
BASE_URL = "https://www.trf4.jus.br/trf4/"
OUTPUT_FILE = "gemini-work/trf4_natjus_resultados.csv"

def main():
    print(f"Acessando: {URL_ALVO}")
    
    try:
        # Faz a requisição
        response = requests.get(URL_ALVO, timeout=30)
        response.raise_for_status()
        
        # O site do TRF4 usa ISO-8859-1, vamos garantir a decodificação correta
        response.encoding = 'iso-8859-1'
        html_content = response.text
        
        # Regex para capturar o link e o nome do medicamento
        # Padrão: <div class="wp-block-file"><a href="URL">NOME</a></div>
        padrao = r'<div class="wp-block-file"><a href="([^"]+)">([^<]+)</a></div>'
        matches = re.findall(padrao, html_content)
        
        if not matches:
            print("Nenhum medicamento encontrado. Verifique se a estrutura da página mudou.")
            return

        print(f"Encontrados {len(matches)} medicamentos/notas técnicas.")
        
        resultados = []
        for link, nome in matches:
            # Limpa o nome (remove espaços extras e caracteres estranhos se houver)
            nome_limpo = nome.strip()
            
            # Constrói o link completo se for relativo
            link_completo = link if link.startswith('http') else BASE_URL + link
            
            resultados.append({
                'medicamento': nome_limpo,
                'link_pdf': link_completo
            })
            
        # Salva em CSV
        chaves = ['medicamento', 'link_pdf']
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=chaves)
            writer.writeheader()
            writer.writerows(resultados)
            
        print(f"Sucesso! Arquivo salvo em: {OUTPUT_FILE}")
        print(f"Total de registros: {len(resultados)}")

    except Exception as e:
        print(f"Erro ao processar a página: {e}")

if __name__ == "__main__":
    main()
