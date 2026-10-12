import json
import os
import re
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import baixar_capitulo
import one_piece_capitulo as monitor
import telegram

PORTA = int(__import__("os").environ.get("PORTA", "8000"))

OFFSET_FILE = os.path.join(
    os.path.dirname(telegram.log_caminho()), "telegram_offset.json"
)

_aguardando_capitulo = {}  # chat_id -> bool


def _carregar_offset():
    try:
        with open(OFFSET_FILE, "r", encoding="utf-8") as f:
            return int(json.load(f).get("offset", 0))
    except (OSError, ValueError):
        return 0


def _salvar_offset(offset):
    try:
        with open(OFFSET_FILE, "w", encoding="utf-8") as f:
            json.dump({"offset": offset}, f)
    except OSError:
        pass


def _resposta_do_check(r):
    if r.get("atualizado") and r.get("ultimo_capitulo"):
        return f"Novo capitulo de One Piece lancado: Capítulo {r['ultimo_capitulo']} 🏴‍☠️☠️!"
    if r.get("ultimo_capitulo"):
        return f"Sem novidade: o ultimo capitulo de One Piece foi o {r['ultimo_capitulo']} ☠️."
    return "Nao consegui consultar o site agora."


def _executar_download_telegram(numero, chat_id):
    try:
        telegram.enviar_texto(
            f"🏴‍☠️ Baixando o Capítulo {numero}... Aguarde enquanto as imagens são baixadas e o CBR é gerado.",
            chat_id=chat_id,
        )
        imagens = baixar_capitulo.baixar_imagens(
            numero,
            forcar_envio=True,
            chat_id=chat_id,
        )
        if not imagens:
            telegram.enviar_texto(
                f"❌ Não foi possível encontrar imagens para o Capítulo {numero}.\n"
                f"Verifique se o capítulo já foi lançado.",
                chat_id=chat_id,
            )
    except Exception as e:
        print(f"Erro ao processar download do capítulo {numero}: {e}")
        telegram.enviar_texto(
            f"⚠️ Erro ao processar o Capítulo {numero}: {e}",
            chat_id=chat_id,
        )


def _processar_mensagem_telegram(chat_id, texto):
    t = (texto or "").strip()
    t_lower = t.lower()

    if not t:
        return

    # Cancelar espera de capítulo
    if t_lower in ("/cancelar", "cancelar", "cancel"):
        if _aguardando_capitulo.pop(chat_id, None):
            telegram.enviar_texto("❌ Pedido cancelado.", chat_id=chat_id)
        else:
            telegram.enviar_texto("Nenhum pedido em andamento para cancelar.", chat_id=chat_id)
        return

    # Menu de ajuda / Start
    if t_lower in ("/start", "/help", "/ajuda", "ajuda", "comandos"):
        _aguardando_capitulo.pop(chat_id, None)
        msg_ajuda = (
            "🏴‍☠️ *Poneglyph - Bot One Piece* 🏴‍☠️\n\n"
            "Comandos disponíveis:\n"
            "• `/baixar <número>` - Baixa e envia o capítulo especificado (ex: `/baixar 1110`)\n"
            "• `/baixar` - O bot pergunta qual capítulo você quer baixar\n"
            "• `/ultimo` - Baixa e envia o último capítulo salvo\n"
            "• `/check` - Verifica no site se saiu um capítulo novo\n"
            "• `/estado` - Mostra o último capítulo registrado\n\n"
            "💡 Dica: Você também pode enviar diretamente o número do capítulo desejado (ex: `1110`)."
        )
        telegram.enviar_texto(msg_ajuda, chat_id=chat_id)
        return

    # Consulta de estado
    if t_lower in ("/estado", "estado"):
        _aguardando_capitulo.pop(chat_id, None)
        estado = monitor.carregar_estado()
        ult = estado.get("ultimo_capitulo", "Desconhecido")
        data = estado.get("data", "Sem data")
        telegram.enviar_texto(
            f"📊 *Status Atual:*\n• Último capítulo: {ult}\n• Data: {data}",
            chat_id=chat_id,
        )
        return

    # Se o chat estava aguardando o número do capítulo
    if _aguardando_capitulo.get(chat_id):
        m_num = re.search(r"\b(\d+)\b", t)
        if m_num:
            _aguardando_capitulo.pop(chat_id, None)
            numero = int(m_num.group(1))
            threading.Thread(
                target=_executar_download_telegram,
                args=(numero, chat_id),
                daemon=True,
            ).start()
            return
        elif t.startswith("/"):
            # Usuário enviou outro comando, cancela a espera e processa o comando a seguir
            _aguardando_capitulo.pop(chat_id, None)
        else:
            telegram.enviar_texto(
                "⚠️ Por favor, envie o número do capítulo (ex: `1110`) ou envie `/cancelar`.",
                chat_id=chat_id,
            )
            return

    # Comando /baixar sem especificar número -> pergunta qual capítulo
    if t_lower in ("/baixar", "baixar", "/download", "download"):
        _aguardando_capitulo[chat_id] = True
        telegram.enviar_texto(
            "🏴‍☠️ Qual capítulo de One Piece você deseja baixar?\n\n"
            "Envie o número (ex: `1110`) ou envie `/cancelar` para cancelar.",
            chat_id=chat_id,
        )
        return

    # Comando /ultimo -> baixa o último capítulo salvo
    if t_lower in ("/ultimo", "ultimo", "/latest", "latest"):
        estado = monitor.carregar_estado()
        numero = int(estado.get("ultimo_capitulo", 1190))
        threading.Thread(
            target=_executar_download_telegram,
            args=(numero, chat_id),
            daemon=True,
        ).start()
        return

    # Comando com número: ex /baixar 1110, /capitulo 1110, baixar 1110, capitulo 1110
    m_cmd_num = re.search(
        r"(?:/baixar|/capitulo|/download|baixar|capitulo)\s*(?:capitulo\s*|cap\s*|n[ºo]?\s*)?(\d+)",
        t_lower,
    )
    if m_cmd_num:
        numero = int(m_cmd_num.group(1))
        threading.Thread(
            target=_executar_download_telegram,
            args=(numero, chat_id),
            daemon=True,
        ).start()
        return

    # Se o usuário mandou apenas um número direto (ex: "1110")
    if re.match(r"^\d+$", t_lower):
        numero = int(t_lower)
        if 1 <= numero <= 3000:
            threading.Thread(
                target=_executar_download_telegram,
                args=(numero, chat_id),
                daemon=True,
            ).start()
            return

    # Checar se saiu novo capítulo
    if (
        ("capitulo" in t_lower and "novo" in t_lower)
        or t_lower == "/capitulo"
        or t_lower.startswith("/check")
        or t_lower == "check"
    ):
        try:
            r = monitor.checar()
            if r.get("atualizado") and r.get("ultimo_capitulo"):
                threading.Thread(
                    target=_executar_download_telegram,
                    args=(r["ultimo_capitulo"], chat_id),
                    daemon=True,
                ).start()
            telegram.enviar_texto(_resposta_do_check(r), chat_id=chat_id)
        except Exception as e:
            telegram.enviar_texto(f"Erro ao consultar o site: {e}", chat_id=chat_id)
        return

    # Mensagem de comando não reconhecido
    if t.startswith("/"):
        telegram.enviar_texto(
            "Comando não reconhecido. Envie `/ajuda` para ver os comandos disponíveis.",
            chat_id=chat_id,
        )


def _poll_telegram():
    offset = _carregar_offset()
    while True:
        try:
            updates = telegram.ler_updates(offset)
        except Exception as e:
            print(f"Telegram poll error: {e}")
            updates = []
        for upd in updates:
            idu = int(upd.get("update_id", 0))
            if idu >= offset:
                offset = idu + 1
                msg_obj = upd.get("message") or upd.get("channel_post") or {}
                chat_id = (msg_obj.get("chat") or {}).get("id")
                texto = msg_obj.get("text", "")
                if texto and chat_id:
                    try:
                        _processar_mensagem_telegram(chat_id, texto)
                    except Exception as e:
                        print(f"Erro ao processar mensagem '{texto}': {e}")
        _salvar_offset(offset)
        time.sleep(2)


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _capitulo_do_parametro(self, qs):
        valores = qs.get("capitulo")
        if valores:
            return int(valores[0])
        return int(monitor.carregar_estado().get("ultimo_capitulo", 1190))

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        rota = parsed.path

        try:
            if rota == "/check":
                r = monitor.checar()
                if r.get("atualizado") and r.get("ultimo_capitulo"):
                    baixar_capitulo.baixar_imagens(r["ultimo_capitulo"])
                    r["download"] = True
                self._json(r)
            elif rota == "/estado":
                self._json(monitor.carregar_estado())
            elif rota == "/envios":
                envios = []
                caminho = telegram.log_caminho()
                if os.path.exists(caminho):
                    with open(caminho, "r", encoding="utf-8") as f:
                        for linha in f:
                            linha = linha.strip()
                            if linha:
                                try:
                                    envios.append(json.loads(linha))
                                except ValueError:
                                    pass
                self._json({"total": len(envios), "envios": envios[-100:]})
            elif rota == "/baixar":
                numero = self._capitulo_do_parametro(qs)
                imagens = baixar_capitulo.baixar_imagens(numero)
                self._json({"capitulo": numero, "imagens": len(imagens)})
            else:
                self._json({"erro": "rota invalida", "rotas": ["/check", "/estado", "/baixar", "/envios"]}, 404)
        except Exception as e:
            self._json({"erro": str(e)}, 500)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    t = threading.Thread(target=_poll_telegram, daemon=True)
    t.start()
    print(f"Poneglyph-Scraper ouvindo em 0.0.0.0:{PORTA}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORTA), Handler).serve_forever()