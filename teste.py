import requests
from bs4 import BeautifulSoup

url = "https://www.in.gov.br/web/dou/-/resolucao-anatel-n-765-de-6-de-novembro-de-2023-522171563"

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
}

print(f"Baixando: {url}")
try:
    response = requests.get(url, headers=headers, timeout=20)
    print(f"Status Code: {response.status_code}") # Deve ser 200

    # Salva o HTML bruto para inspeção visual
    with open("debug_dou.html", "w", encoding="utf-8") as f:
        f.write(response.text)
    print("HTML bruto salvo em 'debug_dou.html'. Abra este arquivo para verificar se o texto está lá.")

    soup = BeautifulSoup(response.text, 'html.parser')

    # TENTATIVA 1: Classe padrão do DOU
    conteudo = soup.find('div', class_='texto-dou')
    
    # TENTATIVA 2: ID da matéria (comum em versões antigas ou mobile)
    if not conteudo:
        print("Aviso: 'texto-dou' não encontrado. Tentando 'materia'...")
        conteudo = soup.find('div', id='materia')

    if conteudo:
        print("\n--- SUCESSO! Conteúdo encontrado (primeiros 200 caracteres): ---")
        print(conteudo.get_text()[:200])
    else:
        print("\nERRO: O conteúdo continua vazio. Verifique o arquivo debug_dou.html")

except Exception as e:
    print(f"Erro na conexão: {e}")