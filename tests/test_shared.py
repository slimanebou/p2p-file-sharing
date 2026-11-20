"""Tests du scan du dossier partagé et de la publication."""
import json
import os
import tempfile
import unittest

from p2p.shared import DESC_FILE, scan_shared
from tests.test_central import CentralTestCase


class TestShared(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        os.makedirs(os.path.join(self.d, "sous", "dossier"))
        for rel, content in [("a.txt", "AAA"), ("sous/dossier/b.txt", "BB"), ("c.part", "x")]:
            with open(os.path.join(self.d, rel), "w") as f:
                f.write(content)
        with open(os.path.join(self.d, DESC_FILE), "w", encoding="utf-8") as f:
            json.dump({"a.txt": {"desc": "Fichier A", "author": "moi"}}, f)

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan(self):
        files = scan_shared(self.d)
        names = [f["name"] for f in files]
        # sous-dossier inclus, chemin avec des /, descriptions.json et .part ignorés
        self.assertEqual(names, ["a.txt", "sous/dossier/b.txt"])
        a = files[0]
        self.assertEqual((a["desc"], a["author"], a["size"]), ("Fichier A", "moi", 3))
        self.assertEqual(len(a["sha256"]), 64)
        self.assertEqual(files[1]["desc"], "")          # pas de description : vide

    def test_dossier_absent(self):
        with self.assertRaises(FileNotFoundError):
            scan_shared(os.path.join(self.d, "nexistepas"))


class TestPublish(CentralTestCase):
    def logged(self, user="alice"):
        c = self.client()
        c.register(user, "pw")
        c.login(user, "pw")
        return c

    def test_publication(self):
        c = self.logged()
        files = [{"name": "x.txt", "desc": "test", "author": "", "date": "2026-11-20",
                  "size": 3, "sha256": "0" * 64}]
        self.assertEqual(c.publish("10.0.0.5", 6001, files), 1)
        peer = self.srv.state.peers["alice"]
        self.assertEqual((peer["host"], peer["port"]), ("10.0.0.5", 6001))
        self.assertEqual(peer["files"][0]["name"], "x.txt")

    def test_adresse_par_defaut(self):
        c = self.logged()
        c.publish(None, 6001, [])
        self.assertEqual(self.srv.state.peers["alice"]["host"], "127.0.0.1")

    def test_token_invalide(self):
        r = self.req({"type": "PUBLISH", "token": "faux", "port": 6001, "files": []})
        self.assertEqual(r, {"ok": False, "error": "bad_token"})

    def test_fichiers_mal_formes(self):
        c = self.logged()
        r = self.req({"type": "PUBLISH", "token": c.token, "port": 6001,
                      "files": [{"name": "x", "size": "pas un nombre"}]})
        self.assertEqual(r, {"ok": False, "error": "bad_request"})

    def test_republication_remplace(self):
        c = self.logged()
        c.publish(None, 6001, [{"name": "a", "desc": "", "size": 1, "sha256": ""}])
        c.publish(None, 6001, [])
        self.assertEqual(self.srv.state.peers["alice"]["files"], [])


if __name__ == "__main__":
    unittest.main()