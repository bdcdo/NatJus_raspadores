import asyncio
import csv
import re
import os
from playwright.async_api import async_playwright

URL_TRF3 = "https://app.powerbi.com/view?r=eyJrIjoiMTVkM2Y2NTctYjZkOS00NzExLWJhYmUtM2EzMmRiMTRhMTgwIiwidCI6IjExMjBlOWFjLTRmMGUtNDkxOS1hZDY4LTU4ZTU5YzIwNDZjZiJ9"
OUTPUT_FILE = "gemini-work/trf3_natjus_resultados.csv"

def parse_metadata(url, tipo):
    if not url:
        return {'id': '', 'ano': '', 'medicamento': '', 'data': '', 'favorabilidade': 'N/A'}
        
    filename = url.split('/')[-1].replace('.pdf', '').replace('.PDF', '')
    id_val, ano, medicamento, data = "", "", "", ""
    favorabilidade = "Favorável" if "NT_" in filename.upper() else "Resposta Técnica"
    clean_name = filename.replace('_', ' ').replace('-', ' ').replace('  ', ' ')
    
    match_id_ano = re.search(r'(RT|NT)\s+(\d+)\s+(?:A\s+)?(\d{4})', clean_name, re.I)
    if match_id_ano:
        id_val, ano = match_id_ano.group(2), match_id_ano.group(3)
        rest = clean_name[match_id_ano.end():].strip()
    else:
        rest = clean_name.replace('RT ', '').replace('NT ', '').strip()
        match_id = re.search(r'(\d{4,6})', clean_name)
        if match_id: id_val = match_id.group(1)

    match_data = re.search(r'(\d{2}\s\d{2}\s\d{2,4})$', rest)
    if match_data:
        data = match_data.group(1).replace(' ', '-')
        medicamento = rest[:match_data.start()].strip()
    else:
        match_data_orig = re.search(r'(\d{2}-\d{2}-\d{2,4})', filename)
        if match_data_orig:
            data = match_data_orig.group(1)
            parts = filename.split(data)[0].split('_')
            medicamento = parts[-2] if len(parts) > 1 else parts[0]
        else:
            medicamento = rest

    return {'id': id_val, 'ano': ano, 'medicamento': medicamento.strip(), 'data': data, 'favorabilidade': favorabilidade}

async def scrape_trf3():
    # Carrega base existente
    seen_urls = set()
    seen_titles = set() # Para itens sem URL
    file_exists = os.path.exists(OUTPUT_FILE)
    if file_exists:
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['url_pdf']: seen_urls.add(row['url_pdf'])
                else: seen_titles.add(row['titulo'])

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        
        print(f"Acessando Dashboard TRF3 (Meta: 1905 solicitações)...")
        await page.goto(URL_TRF3)
        await asyncio.sleep(30)
        
        containers = page.locator('visual-container')
        count = await containers.count()
        new_results = []

        for i in range(count):
            container = containers.nth(i)
            text = await container.inner_text()
            
            # Identifica as tabelas de interesse
            target_table = None
            if "Notas técnicas" in text and "Notas complementares" not in text:
                target_table = "Notas técnicas"
            elif "Notas complementares" in text:
                target_table = "Notas complementares"
            elif "Solicitações de notas técnicas" in text and "Vara/Gabinete" in text:
                target_table = "Solicitações (Geral)"

            if target_table:
                print(f"Processando: {target_table}")
                await container.scroll_into_view_if_needed()
                await asyncio.sleep(1)
                
                # Foca no grid
                try:
                    await container.locator('.pivotTableCellWrap').first.click(force=True)
                except:
                    await container.click(force=True)
                
                viewport = container.locator('.mid-viewport')
                no_new_data_count = 0
                
                while no_new_data_count < 30:
                    found_new_in_step = False
                    
                    # 1. Se for a tabela geral, pega dados das células (pode não ter link)
                    if target_table == "Solicitações (Geral)":
                        rows = await container.locator('.row').all()
                        for row in rows:
                            cells = await row.locator('.pivotTableCellWrap').all()
                            if len(cells) >= 2:
                                vara = await cells[0].inner_text()
                                qtd = await cells[1].inner_text()
                                key = f"{vara}_{qtd}"
                                if key not in seen_titles:
                                    seen_titles.add(key)
                                    new_results.append({
                                        'base': 'TRF3',
                                        'tipo': 'Solicitação',
                                        'id': '', 'ano': '', 'data': '',
                                        'medicamento': vara,
                                        'favorabilidade': 'N/A',
                                        'url_pdf': '',
                                        'titulo': f"Qtd: {qtd}"
                                    })
                                    found_new_in_step = True
                    
                    # 2. Se for tabela de links
                    else:
                        links_count = await container.locator('a').count()
                        for idx in range(links_count):
                            try:
                                link = container.locator('a').nth(idx)
                                href = await link.get_attribute('href', timeout=1000)
                                if href and 'trf3.jus.br' in href and href not in seen_urls:
                                    seen_urls.add(href)
                                    meta = parse_metadata(href, target_table)
                                    entry = {'base': 'TRF3', 'tipo': target_table, 'url_pdf': href, 'titulo': href.split('/')[-1]}
                                    entry.update(meta)
                                    new_results.append(entry)
                                    found_new_in_step = True
                            except:
                                continue
                    
                    if found_new_in_step:
                        no_new_data_count = 0
                        print(f"  {target_table}: {len(new_results)} novos itens encontrados...")
                    else:
                        no_new_data_count += 1
                    
                    # Scroll
                    if await viewport.count() > 0:
                        await viewport.first.evaluate('el => el.scrollTop += 300')
                        await page.keyboard.press("ArrowDown")
                        await asyncio.sleep(0.4)
                    else:
                        break

        if new_results:
            keys = ['base', 'tipo', 'id', 'ano', 'data', 'medicamento', 'favorabilidade', 'url_pdf', 'titulo']
            mode = 'a' if file_exists else 'w'
            with open(OUTPUT_FILE, mode, newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                if not file_exists: writer.writeheader()
                writer.writerows(new_results)
            print(f"Concluído! {len(new_results)} novos registros adicionados.")
        else:
            print("Nenhuma novidade encontrada.")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_trf3())
