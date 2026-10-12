import json
import os
import time
import urllib.parse
import urllib.request


def _carregar_env():
    candidatos = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    for caminho in candidatos:
        if os.path.isfile(caminho):
            try:
                with open(caminho, "r", encoding="utf-8") as f:
                    for linha in f:
                        linha = linha.strip()
                        if linha and not linha.startswith("#") and "=" in linha:
                            k, v = linha.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            if k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass


_carregar_env()


def _agora():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log_caminho():
    if os.environ.get("TELEGRAM_ENVIOS_LOG"):
        return os.environ.get("TELEGRAM_ENVIOS_LOG")
    pasta = os.environ.get("PASTA_SAIDA") or (
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados")
        if os.path.isdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dados"))
        else os.getcwd()
    )
    return os.path.join(pasta, "envios_telegram.log")


def registrar_envio(tipo, conteudo, ok, arquivo=None):
    registro = {
        "data": _agora(),
        "tipo": tipo,
        "conteudo": conteudo,
        "arquivo": arquivo,
        "ok": ok,
    }
    caminho = log_caminho()
    diretorio = os.path.dirname(caminho)
    if diretorio:
        os.makedirs(diretorio, exist_ok=True)
    with open(caminho, "a", encoding="utf-8") as f:
        f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    return registro


def _token():
    _carregar_env()
    return os.environ.get("TELEGRAM_BOT_TOKEN")


def _chat_id():
    _carregar_env()
    return os.environ.get("TELEGRAM_CHAT_ID")


def _credenciais():
    token = _token()
    chat = _chat_id()
    if not token or not chat:
        registrar_envio("erro", "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID nao configurados", False)
        return None
    return token, chat


def enviar_texto(texto, chat_id=None):
    token = _token()
    chat = chat_id or _chat_id()
    if not token or not chat:
        registrar_envio("erro", "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID nao configurados", False)
        return None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    corpo = urllib.parse.urlencode({"chat_id": chat, "text": texto}).encode("utf-8")
    req = urllib.request.Request(url, data=corpo)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resultado = json.loads(resp.read().decode("utf-8", errors="replace"))
        ok = bool(resultado.get("ok"))
        if not ok:
            print(f"Falha ao enviar texto: {resultado}")
        registrar_envio("texto", texto, ok)
        return resultado
    except Exception as e:
        print(f"Erro ao enviar texto para chat {chat}: {e}")
        registrar_envio("texto", f"Erro: {e}", False)
        return None


def ler_updates(offset=0, timeout=30):
    token = _token()
    if not token:
        return []
    qs = urllib.parse.urlencode({"timeout": timeout, "offset": offset})
    url = f"https://api.telegram.org/bot{token}/getUpdates?{qs}"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout + 20) as resp:
            resultado = json.loads(resp.read().decode("utf-8", errors="replace"))
        if not resultado.get("ok"):
            print(f"Falha ao ler updates: {resultado}")
            return []
        return resultado.get("result", [])
    except Exception as e:
        print(f"Erro ao ler updates: {e}")
        return []


def enviar_documento(arquivo, legenda=None, chat_id=None):
    token = _token()
    chat = chat_id or _chat_id()
    if not token or not chat:
        registrar_envio("erro", "TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID nao configurados", False)
        return None
    if not os.path.exists(arquivo):
        registrar_envio("arquivo", legenda or "", False, arquivo=os.path.basename(arquivo))
        return None

    with open(arquivo, "rb") as f:
        dados = f.read()
    nome = os.path.basename(arquivo)
    if len(dados) > 50 * 1024 * 1024:
        registrar_envio("arquivo", "arquivo maior que 50MB, nao enviado", False, arquivo=nome)
        return None

    boundary = "----python-" + os.urandom(16).hex()
    partes = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n".encode()
    ]
    if legenda:
        partes.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{legenda}\r\n".encode("utf-8")
        )
    partes.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{nome}\"\r\n"
        "Content-Type: application/octet-stream\r\n\r\n".encode()
    )
    corpo = b"".join(partes) + dados + f"\r\n--{boundary}--\r\n".encode()

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    req = urllib.request.Request(
        url,
        data=corpo,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            resultado = json.loads(resp.read().decode("utf-8", errors="replace"))
        ok = bool(resultado.get("ok"))
        if not ok:
            print(f"Falha ao enviar documento: {resultado}")
        registrar_envio("arquivo", legenda or "", ok, arquivo=nome)
        return resultado
    except Exception as e:
        print(f"Erro ao enviar documento para chat {chat}: {e}")
        registrar_envio("arquivo", f"Erro: {e}", False, arquivo=nome)
        return None