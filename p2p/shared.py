"""Dossier partagé d'un hôte : liste des fichiers et de leurs descriptions.

Le fichier descriptions.json, à la racine du dossier partagé, associe à chaque
fichier (chemin relatif, avec des / ) sa description et des champs optionnels :

{
  "MP3.txt": {"desc": "FAQ sur la compression audio MPEG-2", "author": "Slimane"},
  "cours/tcp.pdf": {"desc": "Cours sur le protocole TCP"}
}

Un fichier absent de descriptions.json est quand même partagé, avec une
description vide (la recherche se fera alors sur son nom).
"""
import json
import os
from datetime import datetime
from pathlib import Path

from p2p.protocol import sha256_file

DESC_FILE = "descriptions.json"
IGNORED_SUFFIXES = (".part", ".tmp")


def load_descriptions(shared_dir) -> dict:
    path = Path(shared_dir) / DESC_FILE
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_descriptions(shared_dir, descriptions: dict) -> None:
    path = Path(shared_dir) / DESC_FILE
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(descriptions, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def file_entry(shared_dir, rel_name: str, meta: dict) -> dict:
    """Décrit un fichier comme le protocole l'attend : {name, desc, author, date, size, sha256}."""
    full = Path(shared_dir) / rel_name
    st = full.stat()
    return {
        "name": rel_name,
        "desc": meta.get("desc", ""),
        "author": meta.get("author", ""),
        "date": meta.get("date") or datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d"),
        "size": st.st_size,
        "sha256": sha256_file(full),
    }


def scan_shared(shared_dir) -> list:
    """Parcourt le dossier partagé et ses sous-dossiers, renvoie la liste triée des fichiers."""
    root = Path(shared_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"dossier partagé introuvable : {root}")
    descriptions = load_descriptions(root)
    entries = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()     # chemin relatif, toujours avec des /
        if rel == DESC_FILE or rel.endswith(IGNORED_SUFFIXES):
            continue
        entries.append(file_entry(root, rel, descriptions.get(rel, {})))
    return sorted(entries, key=lambda e: e["name"].lower())