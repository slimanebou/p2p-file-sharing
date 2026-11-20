"""Tests du serveur central : on le lance sur un port libre, dans un thread."""
import json
import os
import tempfile
import threading
import unittest

from central import CentralServer
from p2p import auth
from p2p.central_client import CentralClient, CentralError
from p2p.protocol import connect, request


class CentralTestCase(unittest.TestCase):
    """Base réutilisée par les tests des phases suivantes."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.users_path = os.path.join(self.tmp.name, "users.json")
        self.srv = CentralServer(("127.0.0.1", 0), self.users_path)  # port 0 = le système choisit
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def client(self):
        return CentralClient("127.0.0.1", self.port)

    def req(self, msg):
        return request("127.0.0.1", self.port, msg)


class TestCentral(CentralTestCase):
    def test_ping(self):
        self.assertEqual(self.req({"type": "PING"}), {"ok": True, "type": "PONG"})

    def test_type_inconnu(self):
        self.assertEqual(self.req({"type": "NIMPORTEQUOI"}),
                         {"ok": False, "error": "unknown_type"})

    def test_plusieurs_messages_meme_connexion(self):
        conn = connect("127.0.0.1", self.port)
        for _ in range(5):
            conn.send_msg({"type": "PING"})
            self.assertTrue(conn.recv_msg()["ok"])
        conn.close()

    def test_json_invalide(self):
        conn = connect("127.0.0.1", self.port)
        conn.sock.sendall(b"ceci n'est pas du json\n")
        self.assertEqual(conn.recv_msg(), {"ok": False, "error": "protocol_error"})
        conn.close()

    def test_vingt_clients_en_meme_temps(self):
        # 20 connexions ouvertes simultanément : chacune doit avoir sa réponse.
        conns = [connect("127.0.0.1", self.port) for _ in range(20)]
        results = []

        def client(c):
            c.send_msg({"type": "PING"})
            results.append(c.recv_msg())
            c.close()

        threads = [threading.Thread(target=client, args=(c,)) for c in conns]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(results), 20)
        self.assertTrue(all(r["ok"] for r in results))

class TestAuth(CentralTestCase):
    def test_enregistrement_puis_connexion(self):
        self.client().register("alice", "motdepasse")
        token = self.client().login("alice", "motdepasse")
        self.assertEqual(len(token), 32)

    def test_utilisateur_existant(self):
        self.client().register("alice", "a")
        with self.assertRaisesRegex(CentralError, "exists"):
            self.client().register("alice", "b")

    def test_nom_invalide(self):
        with self.assertRaisesRegex(CentralError, "bad_username"):
            self.client().register("a b", "x")

    def test_mauvais_mot_de_passe(self):
        self.client().register("alice", "bon")
        with self.assertRaisesRegex(CentralError, "auth_failed"):
            self.client().login("alice", "mauvais")

    def test_utilisateur_inconnu(self):
        with self.assertRaisesRegex(CentralError, "unknown_user"):
            self.client().login("bob", "x")

    def test_rejeu_impossible(self):
        # Un attaquant capture une preuve valide et la renvoie : refusé, le nonce est consommé.
        self.client().register("alice", "secret")
        chal = self.req({"type": "CHALLENGE", "user": "alice"})
        proof = auth.make_proof(auth.hash_password("secret", chal["salt"]), chal["nonce"])
        self.assertTrue(self.req({"type": "LOGIN", "user": "alice", "proof": proof})["ok"])
        rejeu = self.req({"type": "LOGIN", "user": "alice", "proof": proof})
        self.assertEqual(rejeu, {"ok": False, "error": "auth_failed"})

    def test_mot_de_passe_jamais_stocke(self):
        self.client().register("alice", "TresSecret42")
        with open(self.users_path, encoding="utf-8") as f:
            contenu = f.read()
        self.assertNotIn("TresSecret42", contenu)
        self.assertEqual(set(json.loads(contenu)["alice"]), {"salt", "hash"})

    def test_meme_mot_de_passe_hash_differents(self):
        self.client().register("alice", "pareil")
        self.client().register("bob", "pareil")
        with open(self.users_path, encoding="utf-8") as f:
            users = json.load(f)
        self.assertNotEqual(users["alice"]["hash"], users["bob"]["hash"])

    def test_enregistrements_simultanes(self):
        threads = [threading.Thread(target=lambda i=i: self.client().register(f"user{i}", "pw"))
                   for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with open(self.users_path, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 10)

if __name__ == "__main__":
    unittest.main()