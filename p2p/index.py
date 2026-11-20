"""Recherche par mot-clé et tri des résultats.

Utilisé par le central (recherche + tri par pertinence) et par le client
(nouveau tri des résultats déjà reçus, sans refaire de requête).
"""
import re
import unicodedata

SORT_KEYS = ("relevance", "name", "size", "host", "date")


def normalize(text: str) -> str:
    """Minuscules et sans accents : « Vidéo » et « video » doivent se trouver mutuellement."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def score(keyword: str, name: str, desc: str) -> int:
    """Pertinence d'un fichier pour un mot-clé (déjà normalisé). 0 = ne correspond pas.

    - mot-clé dans le nom du fichier         : +3
    - mot entier dans la description         : +2 par occurrence
    - sous-chaîne seulement (« peg » dans « mpeg ») : +1 par occurrence
    """
    name, desc = normalize(name), normalize(desc)
    whole = len(re.findall(r"\b" + re.escape(keyword) + r"\b", desc))
    partial = desc.count(keyword) - whole
    return 3 * (keyword in name) + 2 * whole + partial


def search(peers: dict, keyword: str, exclude_user=None) -> list:
    """Cherche le mot-clé dans les fichiers de tous les hôtes connectés."""
    kw = normalize(keyword.strip())
    items = []
    for user, peer in peers.items():
        if user == exclude_user:                 # pas ses propres fichiers
            continue
        for f in peer["files"]:
            s = score(kw, f["name"], f["desc"])
            if s > 0:
                items.append({"user": user, "host": peer["host"], "port": peer["port"],
                              "name": f["name"], "desc": f["desc"], "author": f["author"],
                              "size": f["size"], "date": f["date"], "sha256": f["sha256"],
                              "score": s})
    return items


def sort_items(items: list, key: str = "relevance") -> list:
    """Trie les résultats. Les égalités sont départagées par le nom puis l'hôte."""
    if key not in SORT_KEYS:
        raise ValueError(f"critère de tri inconnu : {key}")
    base = sorted(items, key=lambda i: (i["name"].lower(), i["user"]))
    if key == "relevance":
        return sorted(base, key=lambda i: -i["score"])        # plus pertinent d'abord
    if key == "size":
        return sorted(base, key=lambda i: -i["size"])         # plus gros d'abord
    if key == "date":
        return sorted(base, key=lambda i: i["date"], reverse=True)   # plus récent d'abord
    if key == "host":
        return sorted(base, key=lambda i: (i["host"], i["port"]))
    return base                                               # name