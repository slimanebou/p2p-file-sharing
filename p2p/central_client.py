"""Fonctions côté hôte pour parler au serveur central (utilisées par le serveur de fichiers et le client)."""
import logging
import threading

from p2p import auth
from p2p.protocol import request

log = logging.getLogger("heartbeat")
HEARTBEAT_INTERVAL = 10   # secondes (le central attend 30 s : 3 heartbeats perdus avant l'oubli)


class CentralError(Exception):
    """Le central a répondu ok=false."""


class CentralClient:
    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.token = None
        self.user = None
        self.published_addr = None       # (host, port) de la dernière publication
        self._stop = threading.Event()

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
        self.published_addr = (host, port)
        return reply["count"]

    def search(self, keyword: str, sort: str = "relevance") -> list:
        """Demande au central les fichiers qui correspondent au mot-clé, triés."""
        return self._call({"type": "SEARCH", "token": self.token,
                           "keyword": keyword, "sort": sort})["items"]

    def update(self, files: list) -> int:
        """Ajoute des fichiers (ou met à jour leur description) dans la liste publiée."""
        return self._call({"type": "UPDATE", "token": self.token, "files": files})["count"]

    def heartbeat(self) -> None:
        self._call({"type": "HEARTBEAT", "token": self.token})

    def logout(self) -> None:
        """Prévient le central : nos fichiers sortent immédiatement des recherches."""
        self._stop.set()
        self._call({"type": "LOGOUT", "token": self.token})

    def start_heartbeat(self, get_files, interval: float = HEARTBEAT_INTERVAL) -> None:
        """Lance un thread qui signale au central, toutes les `interval` s, que l'hôte est vivant.

        get_files() renvoie la liste actuelle des fichiers : si le central nous a oubliés
        (coupure réseau trop longue), on republie automatiquement.
        """
        def loop():
            last_problem = None              # n'affiche un problème qu'une fois, pas toutes les 10 s
            while not self._stop.wait(interval):
                try:
                    self.heartbeat()
                    if last_problem:
                        log.info("heartbeat de nouveau accepté")
                    last_problem = None
                except CentralError as e:
                    if str(e) == "not_published":
                        self.publish(*self.published_addr, get_files())
                        log.info("le central nous avait oubliés : fichiers republiés")
                    elif last_problem != str(e):
                        log.warning("heartbeat refusé : %s", e)
                        last_problem = str(e)
                except OSError as e:
                    if last_problem != "offline":
                        log.warning("central injoignable (%s), nouvel essai dans %d s", e, interval)
                        last_problem = "offline"
        threading.Thread(target=loop, daemon=True).start()