"""Serveur de fichiers d'un hôte : répond aux GET des autres hôtes. Aucun upload possible.

Sécurité : on ne sert que les fichiers publiés, et le chemin demandé doit rester
à l'intérieur du dossier partagé (protection contre « ../../etc/passwd »).
"""
import logging
import os
import socketserver
import threading
from pathlib import Path

from p2p.protocol import Connection, ProtocolError

log = logging.getLogger("file_server")


class FileHandler(socketserver.BaseRequestHandler):
    """Une connexion = une requête GET = un fichier envoyé."""

    def handle(self):
        srv = self.server
        client = f"{self.client_address[0]}:{self.client_address[1]}"
        self.request.settimeout(30)              # un client muet ne bloque pas un thread à vie
        conn = Connection(self.request)
        try:
            msg = conn.recv_msg()
            if msg is None:
                return
            if msg.get("type") != "GET":         # seul GET existe : pas d'upload
                conn.send_msg({"ok": False, "error": "unknown_type"})
                return
            name = msg.get("name")
            path = srv.resolve(name)
            if path is None:
                log.warning("%s : GET %r refusé (introuvable ou hors du dossier)", client, name)
                conn.send_msg({"ok": False, "error": "not_found"})
                return
            size = path.stat().st_size
            conn.send_msg({"ok": True, "size": size, "sha256": srv.files[name]["sha256"]})
            conn.send_file(path)
            log.info("%s : %s envoyé (%d octets)", client, name, size)
        except (ProtocolError, OSError) as e:
            log.warning("%s : transfert interrompu (%s)", client, e)


class FileServer(socketserver.ThreadingTCPServer):
    # Sous Windows, SO_REUSEADDR permettrait à deux programmes d'écouter sur le même port.
    allow_reuse_address = os.name != "nt"
    daemon_threads = True

    def __init__(self, addr, shared_dir, files):
        super().__init__(addr, FileHandler)
        self.root = Path(shared_dir).resolve()
        self.lock = threading.Lock()
        self.files = {f["name"]: f for f in files}     # fichiers publiés, par nom

    def resolve(self, name):
        """Chemin réel du fichier demandé, ou None s'il ne doit pas être servi."""
        if not isinstance(name, str):
            return None
        with self.lock:
            if name not in self.files:                 # uniquement ce qui a été publié
                return None
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root) or not path.is_file():
            return None
        return path

    def add_file(self, entry):
        """Ajoute un fichier à la liste servie (utilisé après un téléchargement, P7)."""
        with self.lock:
            self.files[entry["name"]] = entry

    def start(self):
        threading.Thread(target=self.serve_forever, daemon=True).start()