import json
import os
import re
import sys
import time
import urllib.request
import webbrowser

URL = "https://leituramanga.net/manga/one-piece"
ESTADO_FILE = os.environ.get("ESTADO_FILE") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "ultimo_capitulo.json"
)
ULTIMO_CAPITULO_BASE = 1190
INTERVALO_PADRAO = 3600

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}


def obter_pagina():
    req = urllib.request.Request(URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extrair_total_capitulos(html):
    m = re.search(r'totalChapter\\?":\s*(\d+)', html)
    return int(m.group(1)) if m else None


def extrair_data_ultimo(html):
    m = re.search(r'latestChapterDate\\?":\s*\\?"([0-9A-Za-z:.TZ+-]+)', html)
    return m.group(1) if m else None


def carregar_estado():
    if os.path.exists(ESTADO_FILE):
        with open(ESTADO_FILE, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return {"ultimo_capitulo": ULTIMO_CAPITULO_BASE}


def salvar_estado(estado):
    with open(ESTADO_FILE, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)


def checar():
    html = obter_pagina()
    total = extrair_total_capitulos(html)
    data = extrair_data_ultimo(html)
    estado = carregar_estado()
    anterior = int(estado.get("ultimo_capitulo", ULTIMO_CAPITULO_BASE))
    atualizado = total is not None and total != anterior
    if atualizado:
        estado["ultimo_capitulo"] = total
        estado["data"] = data
        salvar_estado(estado)
    return {
        "capitulo_anterior": anterior,
        "ultimo_capitulo": total,
        "atualizado": atualizado,
        "data": data,
    }


def verificar():
    try:
        r = checar()
    except Exception as e:
        print(f"Erro ao acessar o site: {e}")
        return

    total = r["ultimo_capitulo"]
    data = r["data"]
    anterior = r["capitulo_anterior"]

    if total is None:
        print("Nao foi possivel obter o ultimo capitulo da pagina.")
        return

    if r["atualizado"]:
        print(f"ATUALIZACAO! Antes: Capitulo {anterior} -> Agora: Capitulo {total}")
        if data:
            print(f"Data do ultimo capitulo: {data}")
        url_capitulo = f"https://leituramanga.net/manga/one-piece/chapter/{total}"
        print(f"Abrindo: {url_capitulo}")
        webbrowser.open(url_capitulo)
        try:
            import baixar_capitulo
            print("Baixando as imagens do novo capitulo...")
            baixar_capitulo.baixar_imagens(total)
        except Exception as e:
            print(f"Erro ao baixar as imagens: {e}")
    else:
        print(f"Sem atualizacoes. Ultimo capitulo continua sendo o {total}.")
        if data:
            print(f"Data do ultimo capitulo: {data}")


def main():
    args = sys.argv[1:]
    if "--watch" in args:
        try:
            idx = args.index("--intervalo")
            intervalo = int(args[idx + 1])
        except (ValueError, IndexError):
            intervalo = INTERVALO_PADRAO
        print(f"Monitorando a cada {intervalo}s. Pressione Ctrl+C para parar.")
        while True:
            verificar()
            time.sleep(intervalo)
    else:
        verificar()


if __name__ == "__main__":
    main()