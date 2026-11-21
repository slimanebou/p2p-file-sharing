"""Tests de la P7 : un fichier téléchargé devient partagé et le central est mis à jour."""
import os
import tempfile
from pathlib import Path

from p2p.client import download, share_downloaded
from p2p.file_server import FileServer
from p2p.protocol import sha256_file
from p2p.shared import load_descriptions, scan_shared
from tests.test_central import CentralTestCase


def fichier(name, desc="d"):
    return {"name": name, "desc": desc, "author": "", "date": "2026-01-01", "size": 1, "sha256": ""}


class TestUpdateCentral(CentralTestCase):
    def logged(self, user):
        c = self.client()
        c.register(user, "pw")
        c.login(user, "pw")
        return c

    def test_ajout_et_remplacement(self):
        c = self.logged("alice")
        c.publish(None, 6001, [fichier("a.txt")])
        self.assertEqual(c.update([fichier("b.txt")]), 2)
        self.assertEqual(c.update([fichier("b.txt", "nouvelle description")]), 2)  # même nom
        files = {f["name"]: f for f in self.srv.state.peers["alice"]["files"]}
        self.assertEqual(files["b.txt"]["desc"], "nouvelle description")

    def test_update_sans_publish(self):
        c = self.logged("alice")
        r = self.req({"type": "UPDATE", "token": c.token, "files": []})
        self.assertEqual(r["error"], "not_published")


class TestScenarioComplet(CentralTestCase):
    """carol partage un fichier, alice le télécharge, bob le trouve chez les deux."""

    def setUp(self):
        super().setUp()
        self.tmp2 = tempfile.TemporaryDirectory()
        base = Path(self.tmp2.name)
        self.carol_dir, self.alice_dir = base / "carol", base / "alice"
        self.carol_dir.mkdir()
        self.alice_dir.mkdir()
        (self.carol_dir / "image.bin").write_bytes(os.urandom(500_000))
        (self.carol_dir / "descriptions.json").write_text(
            '{"image.bin": {"desc": "Image de test", "author": "Carol"}}', encoding="utf-8")

        self.servers = []
        self.carol = self.peer("carol", self.carol_dir)
        self.alice = self.peer("alice", self.alice_dir)
        self.bob = self.client()
        self.bob.register("bob", "pw")
        self.bob.login("bob", "pw")

    def peer(self, user, shared):
        files = scan_shared(shared)
        fs = FileServer(("127.0.0.1", 0), shared, files)
        fs.start()
        self.servers.append(fs)
        c = self.client()
        c.register(user, "pw")
        c.login(user, "pw")
        c.publish("127.0.0.1", fs.server_address[1], files)
        c.file_server = fs
        return c

    def tearDown(self):
        for fs in self.servers:
            fs.shutdown()
            fs.server_close()
        self.tmp2.cleanup()
        super().tearDown()

    def test_fichier_telecharge_repartage(self):
        self.assertEqual([i["user"] for i in self.bob.search("image")], ["carol"])

        item = self.alice.search("image")[0]
        download(item, self.alice_dir)
        share_downloaded(item, self.alice_dir, self.alice.file_server, self.alice)

        # la description a été recopiée localement
        self.assertEqual(load_descriptions(self.alice_dir)["image.bin"]["desc"], "Image de test")
        # le central connaît maintenant deux sources
        self.assertEqual(sorted(i["user"] for i in self.bob.search("image")), ["alice", "carol"])
        # et bob peut vraiment télécharger depuis alice
        bob_dir = Path(self.tmp2.name) / "bob"
        bob_dir.mkdir()
        from_alice = next(i for i in self.bob.search("image") if i["user"] == "alice")
        path = download(from_alice, bob_dir)
        self.assertEqual(sha256_file(path), sha256_file(self.carol_dir / "image.bin"))