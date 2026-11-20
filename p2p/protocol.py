"""Couche protocole : messages JSON (une ligne chacun) et fichiers sur une socket TCP.

TCP livre un flux d'octets, sans frontières de messages. Cette classe garde
un tampon de réception : les octets reçus en trop (le début du message
suivant, ou les premiers octets d'un fichier) ne sont jamais perdus.
"""
import hashlib
import json
import socket

ENCODING = "utf-8"
CHUNK = 64 * 1024            # taille des blocs pour les fichiers (64 Kio)
MAX_LINE = 1024 * 1024       # une ligne JSON ne dépasse pas 1 Mio (protection mémoire)


class ProtocolError(Exception):
    """Message mal formé, trop long, ou connexion coupée au milieu d'un échange."""


class Connection:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self._buf = b""

    # ---------- messages de contrôle ----------
    def send_msg(self, msg: dict) -> None:
        data = json.dumps(msg, ensure_ascii=False).encode(ENCODING) + b"\n"
        self.sock.sendall(data)          # sendall boucle jusqu'à tout envoyer

    def recv_msg(self):
        """Renvoie le prochain message (dict), ou None si l'autre côté a fermé proprement."""
        while b"\n" not in self._buf:
            if len(self._buf) > MAX_LINE:
                raise ProtocolError("ligne trop longue")
            chunk = self.sock.recv(CHUNK)
            if not chunk:                # connexion fermée
                if self._buf:
                    raise ProtocolError("connexion fermée au milieu d'un message")
                return None
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        try:
            msg = json.loads(line.decode(ENCODING))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ProtocolError(f"JSON invalide : {e}") from None
        if not isinstance(msg, dict):
            raise ProtocolError("un message doit être un objet JSON")
        return msg

    # ---------- octets bruts (fichiers) ----------
    def _recv_exact(self, n: int) -> bytes:
        """Lit exactement n octets (en vidant d'abord le tampon)."""
        while len(self._buf) < n:
            chunk = self.sock.recv(CHUNK)
            if not chunk:
                raise ProtocolError("connexion fermée pendant le transfert")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def send_file(self, path) -> None:
        with open(path, "rb") as f:
            while block := f.read(CHUNK):
                self.sock.sendall(block)

    def recv_file(self, path, size: int, progress=None) -> str:
        """Écrit exactement `size` octets dans `path` et renvoie leur SHA-256."""
        h = hashlib.sha256()
        remaining = size
        with open(path, "wb") as f:
            while remaining > 0:
                block = self._recv_exact(min(CHUNK, remaining))
                f.write(block)
                h.update(block)
                remaining -= len(block)
                if progress:
                    progress(size - remaining, size)
        return h.hexdigest()

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def connect(host: str, port: int, timeout: float = 10.0) -> Connection:
    """Ouvre une connexion TCP vers host:port."""
    return Connection(socket.create_connection((host, port), timeout=timeout))


def request(host: str, port: int, msg: dict, timeout: float = 10.0) -> dict:
    """Envoie un message, attend une réponse, ferme. Pour les échanges simples."""
    conn = connect(host, port, timeout)
    try:
        conn.send_msg(msg)
        reply = conn.recv_msg()
        if reply is None:
            raise ProtocolError("le serveur a fermé la connexion sans répondre")
        return reply
    finally:
        conn.close()


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()