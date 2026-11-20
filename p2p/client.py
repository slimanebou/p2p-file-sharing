"""Client interactif d'un hôte : recherche, tri, (téléchargement en P6)."""
import cmd

from p2p.central_client import CentralError
from p2p.index import SORT_KEYS, sort_items


def human_size(n: int) -> str:
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024 or unit == "Go":
            return f"{n:.0f} {unit}" if unit == "o" else f"{n:.1f} {unit}"
        n /= 1024


class Shell(cmd.Cmd):
    intro = "Tape « help » pour la liste des commandes."

    def __init__(self, central):
        super().__init__()
        self.central = central
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