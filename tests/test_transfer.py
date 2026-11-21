"""Tests du serveur de fichiers et du téléchargement."""
import os
import tempfile
import unittest
from pathlib import Path

from p2p.client import DownloadError, download
from p2p.file_server import FileServer
from p2p.protocol import request, sha256_file
from p2p.shared import scan_shared


class TestTransfer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.src, self.dst = base / "src", base / "dst"
        (self.src / "sous").mkdir(parents=True)
        self.dst.mkdir()
        (self.src / "petit.txt").write_text("bonjour")
        (self.src / "sous" / "gros.bin").write_bytes(os.urandom(3 * 1024 * 1024))
        (base / "secret.txt").write_text("ne doit jamais sortir")
        self.files = scan_shared(self.src)
        (self.src / "non_publie.txt").write_text("ajouté après la publication")

        self.srv = FileServer(("127.0.0.1", 0), self.src, self.files)
        self.port = self.srv.server_address[1]
        self.srv.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def item(self, name):
        entry = next(f for f in self.files if f["name"] == name)
        return dict(entry, host="127.0.0.1", port=self.port, user="test")

    def get(self, name):
        return request("127.0.0.1", self.port, {"type": "GET", "name": name})

    def test_gros_fichier_binaire_sous_dossier(self):
        path = download(self.item("sous/gros.bin"), self.dst)
        self.assertEqual(sha256_file(path), sha256_file(self.src / "sous" / "gros.bin"))
        self.assertFalse(list(self.dst.rglob("*.part")))      # plus de fichier temporaire

    def test_introuvable(self):
        self.assertEqual(self.get("absent.txt"), {"ok": False, "error": "not_found"})

    def test_path_traversal(self):
        self.assertEqual(self.get("../secret.txt")["error"], "not_found")

    def test_fichier_non_publie(self):
        self.assertEqual(self.get("non_publie.txt")["error"], "not_found")

    def test_pas_d_upload(self):
        r = request("127.0.0.1", self.port, {"type": "PUT", "name": "x"})
        self.assertEqual(r["error"], "unknown_type")

    def test_empreinte_fausse_rejetee(self):
        item = self.item("petit.txt")
        item["sha256"] = "0" * 64
        with self.assertRaisesRegex(DownloadError, "SHA-256"):
            download(item, self.dst)
        self.assertEqual(list(self.dst.iterdir()), [])        # rien n'est resté

    def test_deja_present(self):
        download(self.item("petit.txt"), self.dst)
        with self.assertRaisesRegex(DownloadError, "existe déjà"):
            download(self.item("petit.txt"), self.dst)

    def test_nom_piege(self):
        item = self.item("petit.txt")
        item["name"] = "../../evil.txt"
        with self.assertRaisesRegex(DownloadError, "refusé"):
            download(item, self.dst)


if __name__ == "__main__":
    unittest.main()