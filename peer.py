"""Hôte P2P : se connecte au central, publie ses fichiers partagés.
(Le serveur de fichiers et le client interactif arrivent en P5 et P6.)

Usage :
  py peer.py --central-host 127.0.0.1 --central-port 5000 --shared demo/alice --port 6001
  py peer.py ... --register        # crée le compte avant de se connecter
"""
import argparse
import getpass
import socket
import sys
from p2p.client import Shell

from p2p.central_client import CentralClient, CentralError
from p2p.shared import scan_shared


def parse_args():
    ap = argparse.ArgumentParser(description="Hôte P2P (serveur de fichiers + client)")
    ap.add_argument("--central-host", required=True, help="adresse du serveur central")
    ap.add_argument("--central-port", type=int, default=5000, help="port du serveur central")
    ap.add_argument("--shared", required=True, help="dossier des fichiers partagés")
    ap.add_argument("--port", type=int, default=6001, help="port du serveur de fichiers local")
    ap.add_argument("--host", default=None,
                    help="adresse annoncée aux autres hôtes (défaut : celle vue par le central)")
    ap.add_argument("--register", action="store_true", help="créer le compte avant de se connecter")
    return ap.parse_args()


def authenticate(central: CentralClient, register: bool) -> None:
    """Demande login / mot de passe et s'authentifie (le mot de passe reste local)."""
    user = input("Nom d'utilisateur : ").strip()
    password = getpass.getpass("Mot de passe : ")        # rien ne s'affiche en tapant
    if register:
        if getpass.getpass("Confirmer le mot de passe : ") != password:
            sys.exit("Les mots de passe ne correspondent pas.")
        central.register(user, password)
        print(f"Compte {user} créé.")
    central.login(user, password)
    print(f"Authentifié en tant que {user}.")


def main():
    args = parse_args()
    central = CentralClient(args.central_host, args.central_port)
    try:
        authenticate(central, args.register)
        files = scan_shared(args.shared)
        count = central.publish(args.host, args.port, files)
    except CentralError as e:
        sys.exit(f"Refusé par le central : {e}")
    except (ConnectionError, socket.timeout, OSError) as e:
        sys.exit(f"Central injoignable ({args.central_host}:{args.central_port}) : {e}")

    print(f"{count} fichier(s) publié(s) depuis {args.shared} :")
    for f in files:
        print(f"  - {f['name']:<30} {f['size']:>9} o  {f['desc']}")
    try:
        Shell(central).cmdloop()
    except KeyboardInterrupt:
        pass
    print("Arrêt.")


if __name__ == "__main__":
    main()