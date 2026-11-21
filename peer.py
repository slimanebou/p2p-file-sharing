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
import logging
from p2p.client import Shell

from p2p.central_client import CentralClient, CentralError
from p2p.shared import scan_shared
from p2p.file_server import FileServer


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
    logging.basicConfig(level=logging.INFO, format="  [%(name)s] %(message)s")
    
    try:
        files = scan_shared(args.shared)
    except FileNotFoundError as e:
        sys.exit(str(e))

    # Le serveur de fichiers démarre AVANT la publication : l'adresse annoncée doit répondre.
    try:
        file_server = FileServer(("0.0.0.0", args.port), args.shared, files)
    except OSError as e:
        sys.exit(f"Impossible d'écouter sur le port {args.port} : {e}")
    file_server.start()

    central = CentralClient(args.central_host, args.central_port)
    try:
        authenticate(central, args.register)
        count = central.publish(args.host, args.port, files)
    except CentralError as e:
        sys.exit(f"Refusé par le central : {e}")
    except (ConnectionError, socket.timeout, OSError) as e:
        sys.exit(f"Central injoignable ({args.central_host}:{args.central_port}) : {e}")

    print(f"Serveur de fichiers à l'écoute sur le port {args.port}.")
    print(f"{count} fichier(s) publié(s) depuis {args.shared} :")
    for f in files:
        print(f"  - {f['name']:<30} {f['size']:>9} o  {f['desc']}")
    central.start_heartbeat(lambda: list(file_server.files.values()))
    try:
        Shell(central, args.shared, file_server).cmdloop()
    except KeyboardInterrupt:
        pass
    
    finally:
        # Déconnexion annoncée : le central retire nos fichiers tout de suite.
        try:
            central.logout()
            print("Déconnecté du central.")
        except CentralError as e:
            print(f"Déconnexion refusée par le central ({e}).")
        except OSError:
            print("Central injoignable : il nous retirera seul après 30 s sans heartbeat.")
        file_server.shutdown()
        print("Arrêt.")


if __name__ == "__main__":
    main()