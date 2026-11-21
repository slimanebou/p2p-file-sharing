"""Client interactif d'un hôte : recherche, tri, téléchargement."""
import cmd
import os
from pathlib import Path

from p2p.central_client import CentralError
from p2p.index import SORT_KEYS, sort_items
from p2p.protocol import ProtocolError, connect
from p2p.shared import file_entry, load_descriptions, save_descriptions


class DownloadError(Exception):
    pass


def download(item: dict, shared_dir, progress=None) -> Path:
    """Télécharge un fichier depuis l'hôte qui le partage, dans le dossier partagé local.

    Écrit d'abord dans un .part, vérifie le SHA-256, puis renomme : un fichier
    incomplet ou corrompu n'apparaît jamais sous son vrai nom.
    """
    root = Path(shared_dir).resolve()
    dest = (root / item["name"]).resolve()
    if not dest.is_relative_to(root):                       # nom piégé renvoyé par le central
        raise DownloadError("nom de fichier refusé")
    if dest.exists():
        raise DownloadError(f"{item['name']} existe déjà dans {shared_dir}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")

    conn = connect(item["host"], item["port"], timeout=30)
    try:
        conn.send_msg({"type": "GET", "name": item["name"]})
        head = conn.recv_msg()
        if head is None or not head.get("ok"):
            raise DownloadError((head or {}).get("error", "pas de réponse"))
        digest = conn.recv_file(part, int(head["size"]), progress)
    except (ProtocolError, OSError) as e:
        part.unlink(missing_ok=True)
        raise DownloadError(f"transfert interrompu : {e}") from None
    finally:
        conn.close()

    if digest != item["sha256"]:                            # comparé à l'empreinte publiée
        part.unlink(missing_ok=True)
        raise DownloadError("empreinte SHA-256 différente : fichier rejeté")
    os.replace(part, dest)
    return dest

def share_downloaded(item: dict, shared_dir, file_server, central) -> dict:
    """Rend un fichier téléchargé disponible aux autres (exigence du sujet).

    1. sa description est ajoutée au descriptions.json local ;
    2. le serveur de fichiers local accepte désormais de le servir ;
    3. le central est prévenu par un UPDATE.
    """
    meta = {"desc": item["desc"], "author": item.get("author", ""), "date": item["date"]}
    descriptions = load_descriptions(shared_dir)
    descriptions[item["name"]] = meta
    save_descriptions(shared_dir, descriptions)

    entry = file_entry(shared_dir, item["name"], meta)
    file_server.add_file(entry)
    central.update([entry])
    return entry

def progress_bar(done: int, total: int) -> None:
    pct = done * 100 // total if total else 100
    if pct == getattr(progress_bar, "last", None) and done < total:
        return                                   # n'affiche que si le pourcentage change
    progress_bar.last = pct
    bar = "#" * (pct // 4)
    print(f"\r  [{bar:<25}] {pct:3d} %  {human_size(done):<10}", end="", flush=True)

def human_size(n: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or unit == "Go":
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}"
        n /= 1024


class Shell(cmd.Cmd):
    intro = "Tape « help » pour la liste des commandes."

    def __init__(self, central, shared_dir, file_server):
        super().__init__()
        self.central = central
        self.shared_dir = shared_dir
        self.file_server = file_server
        self.prompt = f"p2p:{central.user}> "
        self.results = []          # derniers résultats, numérotés à l'affichage

    # ---------- affichage ----------
    def show(self):
        if not self.results:
            print("Aucun résultat.")
            return
        print(f"{'n°':>3}  {'fichier':<28} {'taille':>9}  {'date':<10}  {'hôte':<21}  description")
        for i, it in enumerate(self.results, 1):
            where = f"{it['user']}@{it['host']}:{it['port']}"
            print(f"{i:>3}  {it['name'][:28]:<28} {human_size(it['size']):>9}  "
                  f"{it['date']:<10}  {where[:21]:<21}  {it['desc'][:50]}")

    # ---------- commandes ----------
    def do_search(self, arg):
        """search <mot-clé> [tri] : cherche un fichier (tri : relevance, name, size, host, date)."""
        parts = arg.split()
        if not parts:
            print("Usage : search <mot-clé> [tri]")
            return
        if len(parts) > 1 and parts[-1] in SORT_KEYS:     # « search tcp size »
            keyword, sort = " ".join(parts[:-1]), parts[-1]
        else:                                             # « search tcp »
            keyword, sort = " ".join(parts), "relevance"
        try:
            self.results = self.central.search(keyword, sort)
        except CentralError as e:
            print(f"Erreur du central : {e}")
            return
        self.show()

    def do_sort(self, arg):
        """sort <critère> : retrie les derniers résultats sans interroger le central."""
        key = arg.strip() or "relevance"
        try:
            self.results = sort_items(self.results, key)
        except ValueError:
            print(f"Critères possibles : {', '.join(SORT_KEYS)}")
            return
        self.show()

    def do_get(self, arg):
        """get <n°> : télécharge le fichier n° des derniers résultats depuis l'hôte qui le partage."""
        try:
            item = self.results[int(arg) - 1]
            if int(arg) < 1:
                raise IndexError
        except (ValueError, IndexError):
            print("Usage : get <n°>  (numéro affiché par search)")
            return
        print(f"Téléchargement de {item['name']} depuis {item['user']}@{item['host']}:{item['port']}")
        try:
            path = download(item, self.shared_dir, progress_bar)
        except (DownloadError, OSError) as e:     # OSError : hôte injoignable, refusé, timeout
            print(f"\nÉchec : {e}")
            return
        print(f"\nOK : {path} (SHA-256 vérifié)")
        
        try:
            share_downloaded(item, self.shared_dir, self.file_server, self.central)
            print("Fichier ajouté à tes partages et liste mise à jour auprès du central.")
        except (CentralError, OSError) as e:
            print(f"Téléchargé, mais mise à jour du central impossible : {e}")

    def do_list(self, arg):
        """list : réaffiche les derniers résultats."""
        self.show()

    def do_quit(self, arg):
        """quit : quitte le programme."""
        return True

    do_exit = do_quit
    do_EOF = do_quit

    def emptyline(self):
        pass                       # Entrée sur une ligne vide ne répète pas la commande