"""Tests de la recherche par mot-clé et du tri."""
import unittest

from p2p.index import normalize, score, search, sort_items
from tests.test_central import CentralTestCase


def f(name, desc, size=10, date="2026-01-01"):
    return {"name": name, "desc": desc, "author": "", "size": size, "date": date, "sha256": ""}


PEERS = {
    "alice": {"host": "10.0.0.1", "port": 6001, "files": [
        f("MP3.txt", "FAQ sur la compression audio MPEG-2", 4000, "2026-11-01"),
        f("crepes.txt", "Recette des crêpes", 80, "2026-10-01")]},
    "bob": {"host": "10.0.0.2", "port": 6002, "files": [
        f("cours/tcp.txt", "Cours sur le protocole TCP", 100, "2026-11-15"),
        f("musique/playlist.txt", "Playlist au format MP3", 50, "2026-09-01")]},
}


class TestIndex(unittest.TestCase):
    def test_normalisation(self):
        self.assertEqual(normalize("Crêpes VIDÉO"), "crepes video")

    def test_mot_entier_et_sous_chaine(self):
        self.assertEqual(score("mpeg", "x", "audio MPEG-2"), 2)      # mot entier
        self.assertEqual(score("peg", "x", "audio MPEG-2"), 1)       # sous-chaîne (amélioré)
        self.assertEqual(score("zzz", "x", "audio MPEG-2"), 0)

    def test_nom_plus_pertinent(self):
        self.assertGreater(score("mp3", "MP3.txt", ""), score("mp3", "x", "format MP3"))

    def test_accents(self):
        names = [i["name"] for i in search(PEERS, "crepes")]
        self.assertEqual(names, ["crepes.txt"])

    def test_recherche_plusieurs_hotes(self):
        res = sort_items(search(PEERS, "mp3"))
        self.assertEqual([i["user"] for i in res], ["alice", "bob"])  # nom > description

    def test_exclusion_de_soi(self):
        self.assertEqual(search(PEERS, "mp3", exclude_user="alice")[0]["user"], "bob")

    def test_tris(self):
        res = search(PEERS, "o")       # presque tout correspond
        self.assertEqual(sort_items(res, "size")[0]["name"], "MP3.txt")
        self.assertEqual(sort_items(res, "date")[0]["name"], "cours/tcp.txt")
        self.assertEqual(sort_items(res, "name")[0]["name"], "cours/tcp.txt")
        with self.assertRaises(ValueError):
            sort_items(res, "nimporte")


class TestSearchCentral(CentralTestCase):
    def setUp(self):
        super().setUp()
        self.alice, self.bob = self.client(), self.client()
        for c, user, files in [(self.alice, "alice", PEERS["alice"]["files"]),
                               (self.bob, "bob", PEERS["bob"]["files"])]:
            c.register(user, "pw")
            c.login(user, "pw")
            c.publish(None, 6001, files)

    def test_recherche(self):
        res = self.alice.search("tcp")
        self.assertEqual([(i["user"], i["name"]) for i in res], [("bob", "cours/tcp.txt")])
        self.assertEqual(res[0]["port"], 6001)

    def test_tri_cote_serveur(self):
        res = self.bob.search("e", "size")
        sizes = [i["size"] for i in res]
        self.assertEqual(sizes, sorted(sizes, reverse=True))

    def test_mot_cle_vide(self):
        r = self.req({"type": "SEARCH", "token": self.alice.token, "keyword": "  "})
        self.assertEqual(r["error"], "bad_keyword")

    def test_sans_token(self):
        r = self.req({"type": "SEARCH", "token": "x", "keyword": "tcp"})
        self.assertEqual(r["error"], "bad_token")


if __name__ == "__main__":
    unittest.main()