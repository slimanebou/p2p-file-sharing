"""Mots de passe : sel + PBKDF2 (comme crypt()), puis défi-réponse HMAC.

Le mot de passe ne quitte jamais la machine de l'utilisateur :
- à l'enregistrement, le client envoie seulement (sel, hash) ;
- à la connexion, le central envoie un nonce aléatoire et le client répond
  HMAC(hash, nonce). Le nonce change à chaque fois : une preuve capturée
  ne peut pas être rejouée.
"""
import hashlib
import hmac
import re
import secrets

ITERATIONS = 200_000          # volontairement lent : freine la force brute
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


def valid_username(user) -> bool:
    return isinstance(user, str) and bool(USERNAME_RE.match(user))


def new_salt() -> str:
    return secrets.token_hex(16)          # 128 bits aléatoires


def new_nonce() -> str:
    return secrets.token_hex(16)


def new_token() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    """Équivalent moderne de crypt() : dérive un hash à partir du mot de passe et du sel."""
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), ITERATIONS)
    return dk.hex()


def make_proof(pw_hash: str, nonce: str) -> str:
    """Côté client : prouve qu'on connaît le hash sans l'envoyer."""
    return hmac.new(bytes.fromhex(pw_hash), nonce.encode("ascii"), hashlib.sha256).hexdigest()


def check_proof(pw_hash: str, nonce: str, proof: str) -> bool:
    """Côté central : recalcule la preuve et compare en temps constant."""
    if not isinstance(proof, str):
        return False
    return hmac.compare_digest(make_proof(pw_hash, nonce), proof)