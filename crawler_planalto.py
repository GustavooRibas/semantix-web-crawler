import os
import time
import json
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from collections import deque
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- CONFIGURAÇÕES ---
OUTPUT_DIR = "dataset_planalto_completo"
STATE_FILE = "estado_crawler.json" # Arquivo para salvar o progresso
MAX_DEPTH = 3
DELAY = 0.5 

'''
    "http://www.planalto.gov.br/ccivil_03/leis/leis_complementares.htm",
    "http://www.planalto.gov.br/ccivil_03/legislacao/leisordinarias.htm",
    "http://www.planalto.gov.br/ccivil_03/medida_provisoria/quadro_mpv.htm",
    "http://www.planalto.gov.br/ccivil_03/decreto/quadro_decreto.htm",
    "http://www.planalto.gov.br/ccivil_03/constituicao/emendas/emc/quadro_emc.htm",
    "http://www.planalto.gov.br/ccivil_03/constituicao/constituicao.htm"
'''

# URLs Sementes
SEEDS = [
    "https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2019/decreto/D10046.htm"
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Variáveis globais de estado
visited_urls = set()
download_queue = deque()

def criar_sessao_robusta():
    """Cria uma sessão que tenta reconectar automaticamente em caso de falha."""
    session = requests.Session()
    retry = Retry(
        total=5,  # Tenta 5 vezes
        backoff_factor=1,  # Espera 1s, 2s, 4s, 8s...
        status_forcelist=[500, 502, 503, 504], # Erros de servidor para tentar de novo
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    return session

def carregar_estado():
    """Carrega o progresso anterior se existir."""
    global visited_urls, download_queue
    
    if os.path.exists(STATE_FILE):
        print("Encontrado arquivo de progresso. Retomando...")
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                visited_urls = set(data['visited'])
                # A fila é salva como lista de listas [url, depth], convertemos para tuplas
                download_queue = deque([(item[0], item[1]) for item in data['queue']])
            print(f"Retomando com {len(visited_urls)} links visitados e {len(download_queue)} na fila.")
            return True
        except Exception as e:
            print(f"Erro ao ler arquivo de estado: {e}. Começando do zero.")
    
    # Se não houver estado salvo, inicia com as sementes
    for seed in SEEDS:
        download_queue.append((seed, 0))
    return False

def salvar_estado():
    """Salva o progresso em disco."""
    try:
        data = {
            'visited': list(visited_urls),
            'queue': list(download_queue)
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Erro ao salvar estado: {e}")

def is_valid_url(url):
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1].lower()
    
    # BLOQUEIO EXPLÍCITO DE ARQUIVOS NÃO-TEXTO
    invalid_extensions = ['.pdf', '.doc', '.docx', '.zip', '.img', '.jpg', '.gif']
    if ext in invalid_extensions:
        return False

    # Aceita se for do domínio anatel OU se for ccivil_03
    is_gov = "in.gov.br" in parsed.netloc
    is_anatel = "informacoes.anatel.gov.br" in parsed.netloc
    is_planalto = "ccivil_03" in parsed.path

    return (is_anatel or is_planalto or is_gov) and "mailto:" not in url

def is_content_file(url):
    filename = url.split('/')[-1].lower()
    ignore_terms = ['login', 'form', 'search', 'print=1', 'tmpl=component']
    
    if any(term in filename for term in ignore_terms):
        return False
    
    # Regra para o Diário Oficial (DOU)
    if "in.gov.br" in url and "/web/dou/-/" in url:
        return True
        
    # Lógica para Anatel: Se tiver "resolucao" ou "lei" na URL, consideramos conteúdo
    if "resolucao" in url.lower() or "lei" in url.lower():
        return True

    # Lógica para Planalto
    return filename.endswith('.htm') or filename.endswith('.html')

def save_html(url, content):
    path_parts = urlparse(url).path.split('/')
    
    # Define um nome seguro para o arquivo
    if "in.gov.br" in url:
        # Pega o final da URL do DOU (ex: resolucao-anatel-n-765...)
        safe_name = path_parts[-1]
    elif len(path_parts) >= 2:
        safe_name = f"{path_parts[-2]}_{path_parts[-1]}"
    else:
        safe_name = path_parts[-1]
    
    safe_name = safe_name.replace(':', '').replace('?', '')
    # Garante extensão .html
    if not safe_name.endswith('.html'):
        safe_name += ".html"
    
    filepath = os.path.join(OUTPUT_DIR, safe_name)
    
    # --- TRATAMENTO DO CONTEÚDO ---
    soup = BeautifulSoup(content, 'html.parser')
    html_to_save = content # Por padrão, salva tudo

    # Se for Diário Oficial, tenta limpar para garantir que pegamos o texto
    if "in.gov.br" in url:
        dou_content = soup.find('div', class_='texto-dou')
        if dou_content:
            # Reconstrói um HTML mínimo válido apenas com o texto da lei
            html_to_save = f"<html><body><h1>Fonte: {url}</h1>{str(dou_content)}</body></html>"
        else:
            print(f"   [AVISO] Estrutura 'texto-dou' não encontrada em {url}. Salvando página completa.")

    # Se for Anatel, tenta limpar também
    elif "anatel.gov.br" in url:
        anatel_content = soup.find('div', class_='item-page')
        if anatel_content:
             html_to_save = f"<html><body><h1>Fonte: {url}</h1>{str(anatel_content)}</body></html>"

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_to_save)
        return True
    except Exception as e:
        print(f"Erro de I/O ao salvar {safe_name}: {e}")
        return False

def crawl():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    
    carregar_estado()
    session = criar_sessao_robusta()
    
    count_saved = 0
    loops_since_save = 0
    
    try:
        while download_queue:
            current_url, depth = download_queue.popleft()
            
            if current_url in visited_urls:
                continue
            
            visited_urls.add(current_url)
            
            # Salva o estado a cada 50 iterações para segurança
            loops_since_save += 1
            if loops_since_save >= 50:
                salvar_estado()
                loops_since_save = 0
                print("--- [Checkpoint: Progresso Salvo] ---")

            if depth > MAX_DEPTH:
                continue

            try:
                # print(f"Processando ({depth}): {current_url}") # Comentado para limpar o log
                
                # Timeout aumentado para lidar com lentidão
                response = session.get(current_url, timeout=20)
    
                if "in.gov.br" in current_url or "anatel.gov.br" in current_url:
                    # Sites DOU e Anatel
                    response.encoding = 'utf-8'
                else:
                    # Site Planalto
                    if response.encoding != 'utf-8':
                        response.encoding = 'windows-1252'

                html_content = response.text
                
                if is_content_file(current_url):
                    if save_html(current_url, html_content):
                        count_saved += 1
                        print(f"-> [SALVO] {count_saved} | URL: {current_url.split('/')[-1]}")

                if depth < MAX_DEPTH:
                    soup = BeautifulSoup(html_content, 'html.parser')
                    links = soup.find_all('a', href=True)
                    for link in links:
                        href = link['href']
                        # Tratamento de URL relativa
                        full_url = urljoin(current_url, href).split('#')[0]
                        
                        if is_valid_url(full_url) and full_url not in visited_urls:
                            download_queue.append((full_url, depth + 1))
                
                time.sleep(DELAY)
                
            except requests.exceptions.RequestException as e:
                # Erros de rede não crasham mais o script, apenas logamos e seguimos
                print(f"   [AVISO DE REDE] Pulei {current_url}: {e}")
            except Exception as e:
                print(f"   [ERRO GENÉRICO] {current_url}: {e}")

    except KeyboardInterrupt:
        print("\n\nParando script... Salvando progresso...")
        salvar_estado()
        print("Progresso salvo. Pode fechar.")

if __name__ == "__main__":
    print("Iniciando Crawler Robusto (Com Resume e Retry)...")
    crawl()