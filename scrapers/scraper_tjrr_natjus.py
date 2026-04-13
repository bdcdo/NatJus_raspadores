import requests
import json
import csv
import os
import urllib3
import re
from urllib.parse import unquote

# Desabilitar avisos de SSL
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

BASE_URL = "https://transparencia.tjrr.jus.br/index.php"
AJAX_PARAMS = {
    "option": "com_dropfiles",
    "format": "json"
}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
OUTPUT_FILE = "gemini-work/tjrr_natjus_resultados.csv"

def get_categories(parent_id):
    params = AJAX_PARAMS.copy()
    params["view"] = "frontcategories"
    params["id"] = parent_id
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(BASE_URL, params=params, headers=headers, verify=False, timeout=30)
        if response.status_code == 200:
            return response.json().get("categories", [])
    except: pass
    return []

def get_files(category_id):
    params = AJAX_PARAMS.copy()
    params["view"] = "frontfiles"
    params["id"] = category_id
    headers = {"User-Agent": USER_AGENT}
    try:
        response = requests.get(BASE_URL, params=params, headers=headers, verify=False, timeout=30)
        if response.status_code == 200:
            return response.json().get("files", [])
    except: pass
    return []

def parse_subject_ultimate(subject):
    """
    Lógica agressiva para separar doença e medicamento.
    """
    subject = subject.strip()
    doenca = ""
    medicamento = subject
    
    # 1. Caso TEA
    if "TEA" in subject.upper():
        doenca = "TEA (Transtorno do Espectro Autista)"
        medicamento = re.sub(r'^TEA\s*[-\s]*', '', subject, flags=re.IGNORECASE).strip()
        if not medicamento: medicamento = "Acompanhamento Multidisciplinar"
        return doenca, medicamento

    # 2. Divisão por conectivos com filtros de paciente e diagnóstico
    # Procura separar [Medicamento] de [Paciente + Diagnóstico + Doença]
    pattern = r'^(.*?)\s+(?:PARA|COM|PARA\s+O\s+TRATAMENTO\s+DE)\s+(?:(?:JOVEM|CRIAN\u00c7A|PACIENTE|PESSOA|MENOR|INTERDITO|O\s+PACIENTE|A\s+PACIENTE)\s+)?(?:COM|PARA)?\s*(?:DIAGN\u00d3STICO|DIAGNOSTICO|DOEN\u00c7A|CID)?\s*(?:DE|CONG\u00caNITO)?\s*(.*)$'
    match = re.search(pattern, subject, re.IGNORECASE)
    
    if match:
        medicamento = match.group(1).strip()
        doenca = match.group(2).strip()
    
    # 3. Caso Medicamento explícito
    if subject.lower().startswith("medicamento "):
        med_only = re.sub(r'^medicamento\s+', '', subject, flags=re.IGNORECASE).strip()
        if "(" in med_only:
            parts = med_only.split("(", 1)
            medicamento = parts[0].strip()
            if not doenca: doenca = parts[1].replace(")", "").strip()
        else:
            medicamento = med_only
            
    # Limpezas Finais de prefixos redundantes na doença
    doenca = re.sub(r'^(?:DE\s+|DO\s+|DA\s+|COM\s+|CONG\u00caNITO\s+DE\s+|DIAGN\u00d3STICO\s+DE\s+)', '', doenca, flags=re.IGNORECASE).strip()
    doenca = doenca.strip(" ,.-")
    
    # Limpezas Finais no medicamento
    medicamento = re.sub(r'^(?:PEDIDO\s+DE\s+|FORNECIMENTO\s+DE\s+|SOLICITA\u00c7\u00c3O\s+DE\s+|FORNECER\s+)', '', medicamento, flags=re.IGNORECASE).strip()
    medicamento = medicamento.strip(" ,.-")
    
    return doenca, medicamento

def parse_title_full(title):
    num_match = re.search(r'n[\u00ba\u00b0o]\s*(\d+)', title, re.IGNORECASE)
    numero = num_match.group(1) if num_match else ""
    
    parts = title.split(' - ', 1)
    assunto = parts[1].strip() if len(parts) > 1 else title
    assunto = re.sub(r'^Nota T\u00e9cnica n[\u00ba\u00b0o]\s*\d+\s*(\(\d{4}\))?\s*[-\s]*', '', assunto, flags=re.IGNORECASE).strip()
    
    doenca, medicamento = parse_subject_ultimate(assunto)
    return numero, doenca, medicamento

def scrape_recursive(category_id, results):
    print(f"Scrapeando categoria ID: {category_id}...")
    files = get_files(category_id)
    for f in files:
        title = f.get("title", "")
        numero, doenca, medicamento = parse_title_full(title)
        
        # Link para visualização direta
        viewerlink = f.get("viewerlink", "")
        url_pdf = ""
        
        # Tentar extrair o ID do Google Drive da URL (geralmente uma string longa de 33+ caracteres)
        # Ex: .../15gisMJW9fpb1anIGwH_r4zN43F206GQe/...
        drive_id_match = re.search(r'/([a-zA-Z0-9_-]{33,})/', f.get("link", ""))
        if not drive_id_match and viewerlink:
            drive_id_match = re.search(r'%2F([a-zA-Z0-9_-]{33,})%2F', viewerlink)
            
        if drive_id_match:
            drive_id = drive_id_match.group(1)
            # Link de visualização que NÃO baixa e permite seleção (se o PDF tiver texto)
            url_pdf = f"https://drive.google.com/file/d/{drive_id}/view"
        elif viewerlink:
            # Remove o embedded=true para abrir o visualizador em tela cheia, que permite melhor seleção
            url_pdf = viewerlink.replace("&embedded=true", "")
        else:
            url_pdf = f.get("link", "")
            
        results.append({
            'base': 'TJRR',
            'id': numero if numero else f.get("id"),
            'titulo': title,
            'url_pdf': url_pdf,
            'data': f.get("created_time"),
            'cid': '',
            'doenca': doenca,
            'medicamento': medicamento,
            'caminho_local': '' # Removido o download local
        })
    
    subcats = get_categories(category_id)
    for sc in subcats:
        scrape_recursive(sc.get("id"), results)

def main():
    START_CAT_ID = "7853"
    all_results = []
    scrape_recursive(START_CAT_ID, all_results)
    
    if all_results:
        headers = ['base', 'id', 'titulo', 'url_pdf', 'data', 'cid', 'doenca', 'medicamento', 'caminho_local']
        with open(OUTPUT_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(all_results)
        print(f"Finalizado! {len(all_results)} notas técnicas processadas.")
        print(f"Resultados salvos em: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
