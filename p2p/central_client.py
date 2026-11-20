"""Fonctions côté hôte pour parler au serveur central (utilisées par le serveur de fichiers et le client)."""
from p2p import auth
from p2p.protocol import request


class CentralError(Exception):
    """Le central a répondu ok=false."""


class CentralClient:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.token = None
        self.user = None

    def _call(self, msg: dict) -> dict:
        reply = request(self.host, self.port, msg)
        if not reply.get("ok"):
            raise CentralError(reply.get("error", "erreur inconnue"))
        return reply

    def register(self, user: str, password: str) -> None:
        salt = auth.new_salt()
        pw_hash = auth.hash_password(password, salt)       # calculé ici, en local
        self._call({"type": "REGISTER", "user": user, "salt": salt, "hash": pw_hash})

    def login(self, user: str, password: str) -> str:
        chal = self._call({"type": "CHALLENGE", "user": user})
        pw_hash = auth.hash_password(password, chal["salt"])
        proof = auth.make_proof(pw_hash, chal["nonce"])
        self.token = self._call({"type": "LOGIN", "user": user, "proof": proof})["token"]
        self.user = user
        return self.token

    def publish(self, host: str, port: int, files: list) -> int:
        """Annonce au central l'adresse du serveur de fichiers et la liste des fichiers partagés."""
        reply = self._call({"type": "PUBLISH", "token": self.token,
                            "host": host, "port": port, "files": files})
        return reply["count"]

    def search(self, keyword: str, sort: str = "relevance") -> list:
        """Demande au central les fichiers qui correspondent au mot-clé, triés."""
        return self._call({"type": "SEARCH", "token": self.token,
                           "keyword": keyword, "sort": sort})["items"]