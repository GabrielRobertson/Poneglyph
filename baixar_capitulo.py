import json
import os
import re
import sys
import urllib.request
import zipfile

import telegram

CDN_BASE = "https://cdn.leituramanga.net/"
URL_CAPITULO = "https://leituramanga.net/manga/one-piece/chapter/{numero}"
PASTA_SAIDA = os.environ.get("PASTA_SAIDA") or (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
    if os.path.isdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados"))
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "one-piece_imgs")
)
ESTADO_FILE = os.environ.get("ESTADO_FILE") or (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados", "ultimo_capitulo.json")
    if os.path.isdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados"))
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "ultimo_capitulo.json")
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    "Referer": "https://leituramanga.net/",
}


def obter_pagina(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def extrair_imagens(html):
    padrao = re.compile(r'\\?"url\\?":\s*\\?"(one-piece/[^"\\]+?\.webp)')
    urls = []
    for m in padrao.finditer(html):
        if m.group(1) not in urls:
            urls.append(m.group(1))
    return [CDN_BASE + u for u in urls]


def baixar_imagem(url, caminho):
    if os.path.exists(caminho):
        return False
    req = urllib.request.Request(url, headers={**HEADERS, "Referer": url})
    with urllib.request.urlopen(req, timeout=30) as resp:
        dados = resp.read()
    tmp = caminho + ".tmp"
    with open(tmp, "wb") as f:
        f.write(dados)
    os.replace(tmp, caminho)
    return True


def criar_cbr(numero, pasta=PASTA_SAIDA):
    destino = os.path.join(pasta, f"capitulo-{numero}")
    if not os.path.isdir(destino):
        return None

    imagens = sorted(
        f for f in os.listdir(destino)
        if f.lower().endswith((".webp", ".jpg", ".jpeg", ".png"))
    )
    if not imagens:
        return None

    arquivo_cbr = os.path.join(pasta, f"One Piece_{numero}.cbr")
    print(f"Gerando {os.path.basename(arquivo_cbr)}...")
    with zipfile.ZipFile(arquivo_cbr, "w", zipfile.ZIP_DEFLATED) as z:
        for nome in imagens:
            z.write(os.path.join(destino, nome), arcname=nome)

    return arquivo_cbr if os.path.exists(arquivo_cbr) else None


def cbr_desatualizado(arquivo_cbr, destino):
    if not os.path.exists(arquivo_cbr):
        return True
    mt_cbr = os.path.getmtime(arquivo_cbr)
    for nome in os.listdir(destino):
        caminho = os.path.join(destino, nome)
        if os.path.isfile(caminho) and os.path.getmtime(caminho) > mt_cbr:
            return True
    return False


def baixar_imagens(numero, pasta=PASTA_SAIDA, forcar_envio=False, chat_id=None):
    destino = os.path.join(pasta, f"capitulo-{numero}")
    os.makedirs(destino, exist_ok=True)

    html = obter_pagina(URL_CAPITULO.format(numero=numero))
    imagens = extrair_imagens(html)
    if not imagens:
        print(f"Capitulo {numero}: nenhuma imagem encontrada.")
        return []

    digitos = len(str(len(imagens)))
    baixadas = 0
    for indice, url in enumerate(imagens, 1):
        ext = url.rsplit(".", 1)[-1]
        nome = f"{numero}_{str(indice).zfill(digitos)}.{ext}"
        caminho = os.path.join(destino, nome)
        try:
            if baixar_imagem(url, caminho):
                baixadas += 1
                print(f"Capitulo {numero}: ({indice}/{len(imagens)}) {nome} baixada")
        except Exception as e:
            print(f"Capitulo {numero}: erro ao baixar {nome}: {e}")

    for arq in os.listdir(destino):
        if arq.startswith("page-"):
            os.remove(os.path.join(destino, arq))

    arquivo_cbr = os.path.join(pasta, f"One Piece_{numero}.cbr")
    precisa_criar = cbr_desatualizado(arquivo_cbr, destino)
    if precisa_criar:
        criar_cbr(numero, pasta=pasta)

    if os.path.exists(arquivo_cbr):
        if precisa_criar or forcar_envio:
            try:
                print(f"Capitulo {numero}: enviando CBR para o Telegram...", flush=True)
                resp = telegram.enviar_documento(
                    arquivo_cbr,
                    legenda=f"One Piece - Capítulo {numero} 🏴‍☠️",
                    chat_id=chat_id,
                )
                if resp and resp.get("ok"):
                    print(f"Capitulo {numero}: enviado para o Telegram com sucesso!", flush=True)
                else:
                    print(f"Capitulo {numero}: falha ao enviar CBR ao Telegram. (Resposta: {resp})", flush=True)
            except Exception as e:
                print(f"Erro ao enviar CBR ao Telegram: {e}", flush=True)
        else:
            print(f"Capitulo {numero}: imagens ja em {destino} e CBR atualizado.", flush=True)
    else:
        print(f"Capitulo {numero}: arquivo CBR nao gerado.", flush=True)

    return imagens


def ultimo_capitulo_salvo():
    if os.path.exists(ESTADO_FILE):
        with open(ESTADO_FILE, "r", encoding="utf-8-sig") as f:
            try:
                return int(json.load(f).get("ultimo_capitulo", 1190))
            except (ValueError, TypeError):
                pass
    return 1190


def main():
    args = sys.argv[1:]
    if "--todos" in args:
        ultimo = ultimo_capitulo_salvo()
        print(f"Baixando todos os capitulos de 1 a {ultimo}. Pressione Ctrl+C para cancelar.", flush=True)
        for n in range(1, ultimo + 1):
            try:
                baixar_imagens(n, forcar_envio=True)
            except Exception as e:
                print(f"Capitulo {n}: erro ao acessar: {e}", flush=True)
    elif "--capitulo" in args:
        try:
            numero = int(args[args.index("--capitulo") + 1])
        except (ValueError, IndexError):
            print("Uso: python baixar_capitulo.py --capitulo <NUMERO>")
            return
        baixar_imagens(numero, forcar_envio=True)
    elif len(args) == 1 and args[0].isdigit():
        numero = int(args[0])
        baixar_imagens(numero, forcar_envio=True)
    else:
        ultimo = ultimo_capitulo_salvo()
        if sys.stdin.isatty():
            try:
                entrada = input(f"Qual capítulo você deseja baixar? [Pressione Enter para o último: {ultimo}]: ").strip()
                if not entrada:
                    numero = ultimo
                elif entrada.lower() in ("todos", "all"):
                    print(f"Baixando todos os capítulos de 1 a {ultimo}...", flush=True)
                    for n in range(1, ultimo + 1):
                        try:
                            baixar_imagens(n, forcar_envio=True)
                        except Exception as e:
                            print(f"Capitulo {n}: erro ao acessar: {e}", flush=True)
                    return
                else:
                    numero = int(entrada)
            except (KeyboardInterrupt, EOFError):
                print("\nOperação cancelada pelo usuário.", flush=True)
                return
            except ValueError:
                print(f"Entrada inválida. Usando o capítulo padrão ({ultimo}).", flush=True)
                numero = ultimo
        else:
            numero = ultimo
            print(f"Execução não-interativa. Baixando o último capítulo salvo ({numero}).", flush=True)

        print(f"Baixando o capítulo {numero}...", flush=True)
        baixar_imagens(numero, forcar_envio=True)


if __name__ == "__main__":
    main()