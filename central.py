"""Serveur central : authentification, index des fichiers partagés, recherche.

Usage : py central.py [--host 0.0.0.0] [--port 5000]
"""
import argparse
import logging
import socketserver
import threading

from p2p.protocol import Connection, ProtocolError

log = logging.getLogger("central")


class State:
    """Tout ce que le central garde en mémoire, partagé entre les threads."""

    def __init__(self):
        self.lock = threading.Lock()   # à prendre avant toute lecture/écriture ci-dessous
        self.sessions = {}             # token -> user            (P3)
        self.peers = {}                # user -> {host, port, files, last_seen}  (P4)


# ---------- gestionnaires de messages ----------
# Chaque gestionnaire reçoit (state, msg, client) et renvoie le dict de réponse.
# Les phases suivantes ajoutent les leurs dans HANDLERS.

def handle_ping(state, msg, client):
    return {"ok": True, "type": "PONG"}


HANDLERS = {
    "PING": handle_ping,
}


def dispatch(state, msg, client):
    handler = HANDLERS.get(msg.get("type"))
    if handler is None:
        return {"ok": False, "error": "unknown_type"}
    try:
        return handler(state, msg, client)
    except (KeyError, TypeError, ValueError) as e:   # champ manquant ou mal typé
        log.warning("%s : requête invalide (%s)", client, e)
        return {"ok": False, "error": "bad_request"}


# ---------- serveur TCP multi-thread ----------
class Handler(socketserver.BaseRequestHandler):
    """Un objet Handler, donc un thread, par connexion TCP."""

    def handle(self):
        client = f"{self.client_address[0]}:{self.client_address[1]}"
        conn = Connection(self.request)
        log.info("%s connecté", client)
        try:
            while True:                       # plusieurs messages possibles par connexion
                msg = conn.recv_msg()
                if msg is None:               # le client a fermé
                    break
                reply = dispatch(self.server.state, msg, client)
                log.info("%s %s -> %s", client, msg.get("type"),
                         "ok" if reply.get("ok") else reply.get("error"))
                conn.send_msg(reply)
        except ProtocolError as e:
            log.warning("%s : %s", client, e)
            try:
                conn.send_msg({"ok": False, "error": "protocol_error"})
            except OSError:
                pass
        except OSError as e:                  # connexion coupée brutalement
            log.warning("%s : connexion perdue (%s)", client, e)
        finally:
            log.info("%s déconnecté", client)


class CentralServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True   # relancer tout de suite sans « address already in use »
    daemon_threads = True        # Ctrl+C ne reste pas bloqué par les threads clients

    def __init__(self, addr):
        super().__init__(addr, Handler)
        self.state = State()


def main():
    ap = argparse.ArgumentParser(description="Serveur central P2P")
    ap.add_argument("--host", default="0.0.0.0", help="adresse d'écoute (défaut : toutes)")
    ap.add_argument("--port", type=int, default=5000, help="port d'écoute (défaut : 5000)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    with CentralServer((args.host, args.port)) as srv:
        log.info("serveur central à l'écoute sur %s:%d", args.host, args.port)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            log.info("arrêt demandé")


if __name__ == "__main__":
    main()