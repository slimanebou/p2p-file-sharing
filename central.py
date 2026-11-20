"""Serveur central : authentification, index des fichiers partagés, recherche.

Usage : py central.py [--host 0.0.0.0] [--port 5000]
"""
import argparse
import json
import logging
import os
import socketserver
import threading
import time

from p2p import auth
from p2p.protocol import Connection, ProtocolError

log = logging.getLogger("central")


CHALLENGE_TTL = 30   # secondes de validité d'un nonce


class UserStore:
    """Utilisateurs enregistrés : {user: {salt, hash}} dans un fichier JSON."""

    def __init__(self, path):
        self.path = path
        self.users = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.users = json.load(f)

    def save(self):
        # Écriture atomique : on écrit un fichier temporaire puis on le renomme.
        # Un arrêt brutal pendant l'écriture ne corrompt jamais users.json.
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.users, f, indent=2)
        os.replace(tmp, self.path)


class State:
    """Tout ce que le central garde en mémoire, partagé entre les threads."""

    def __init__(self, users_path="users.json"):
        self.lock = threading.Lock()   # à prendre avant toute lecture/écriture ci-dessous
        self.users = UserStore(users_path)
        self.challenges = {}           # user -> (nonce, date d'émission)
        self.sessions = {}             # token -> user
        self.peers = {}                # user -> {host, port, files, last_seen}  (P4)


def require_session(state, msg):
    """Renvoie l'utilisateur associé au token, ou None. À appeler avec state.lock pris."""
    return state.sessions.get(msg.get("token"))


# ---------- gestionnaires de messages ----------
# Chaque gestionnaire reçoit (state, msg, client) et renvoie le dict de réponse.
# Les phases suivantes ajoutent les leurs dans HANDLERS.

def handle_ping(state, msg, client):
    return {"ok": True, "type": "PONG"}


def handle_register(state, msg, client):
    user, salt, pw_hash = msg["user"], msg["salt"], msg["hash"]
    if not auth.valid_username(user):
        return {"ok": False, "error": "bad_username"}
    bytes.fromhex(salt), bytes.fromhex(pw_hash)       # ValueError -> bad_request
    with state.lock:
        if user in state.users.users:
            return {"ok": False, "error": "exists"}
        state.users.users[user] = {"salt": salt, "hash": pw_hash}
        state.users.save()
    log.info("%s : nouvel utilisateur %s", client, user)
    return {"ok": True}


def handle_challenge(state, msg, client):
    user = msg["user"]
    with state.lock:
        record = state.users.users.get(user)
        if record is None:
            return {"ok": False, "error": "unknown_user"}
        nonce = auth.new_nonce()
        state.challenges[user] = (nonce, time.monotonic())
    return {"ok": True, "salt": record["salt"], "nonce": nonce}


def handle_login(state, msg, client):
    user, proof = msg["user"], msg["proof"]
    with state.lock:
        # pop : un nonce ne sert qu'une fois, même si la preuve est fausse
        nonce, issued = state.challenges.pop(user, (None, 0))
        record = state.users.users.get(user)
        if (nonce is None or record is None
                or time.monotonic() - issued > CHALLENGE_TTL
                or not auth.check_proof(record["hash"], nonce, proof)):
            log.warning("%s : échec d'authentification pour %s", client, user)
            return {"ok": False, "error": "auth_failed"}
        # une seule session par utilisateur : l'ancienne est fermée
        for tok in [t for t, u in state.sessions.items() if u == user]:
            del state.sessions[tok]
        token = auth.new_token()
        state.sessions[token] = user
    log.info("%s : %s authentifié", client, user)
    return {"ok": True, "token": token}


HANDLERS = {
    "PING": handle_ping,
    "REGISTER": handle_register,
    "CHALLENGE": handle_challenge,
    "LOGIN": handle_login,
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

    def __init__(self, addr, users_path="users.json"):
        super().__init__(addr, Handler)
        self.state = State(users_path)


def main():
    ap = argparse.ArgumentParser(description="Serveur central P2P")
    ap.add_argument("--host", default="0.0.0.0", help="adresse d'écoute (défaut : toutes)")
    ap.add_argument("--port", type=int, default=5000, help="port d'écoute (défaut : 5000)")
    ap.add_argument("--users", default="users.json", help="fichier des utilisateurs")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    with CentralServer((args.host, args.port), args.users) as srv:
        log.info("serveur central à l'écoute sur %s:%d", args.host, args.port)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            log.info("arrêt demandé")


if __name__ == "__main__":
    main()