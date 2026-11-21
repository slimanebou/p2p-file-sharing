"""Tests de la P8 : déconnexion annoncée, heartbeat et retrait automatique des hôtes muets."""
import os
import tempfile
import threading
import time
import unittest

from central import CentralServer
from p2p.central_client import CentralClient, CentralError


def fichier(name):
    return {"name": name, "desc": name, "author": "", "date": "2026-01-01", "size": 1, "sha256": ""}


class HeartbeatTestCase(unittest.TestCase):
    """Central avec des délais courts : hôte oublié après 1 s, vérification toutes les 0,2 s."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.srv = CentralServer(("127.0.0.1", 0), os.path.join(self.tmp.name, "u.json"),
                                 peer_timeout=1, reap_interval=0.2)
        self.port = self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.clients = []
        self.alice = self.peer("alice", "alice.txt")
        self.bob = self.peer("bob", "bob.txt")

    def tearDown(self):
        for c in self.clients:
            c._stop.set()                       # arrête les threads de heartbeat
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def peer(self, user, filename):
        c = CentralClient("127.0.0.1", self.port)
        c.register(user, "pw")
        c.login(user, "pw")
        c.publish("127.0.0.1", 6000, [fichier(filename)])
        self.clients.append(c)
        return c

    def found(self, keyword):
        return [i["user"] for i in self.bob.search(keyword)]


class TestHeartbeat(HeartbeatTestCase):
    def test_logout_retire_immediatement(self):
        self.bob.heartbeat()
        self.assertEqual(self.found("alice"), ["alice"])
        self.alice.logout()
        self.assertEqual(self.found("alice"), [])

    def test_hote_muet_retire(self):
        # alice ne fait plus rien (comme un kill -9) : retirée après ~1 s
        self.bob.start_heartbeat(lambda: [fichier("bob.txt")], interval=0.3)
        time.sleep(1.6)
        self.assertEqual(self.found("alice"), [])
        self.assertIn("bob", self.srv.state.peers)        # bob, lui, envoie ses heartbeats

    def test_heartbeat_maintient_en_vie(self):
        self.alice.start_heartbeat(lambda: [fichier("alice.txt")], interval=0.3)
        self.bob.start_heartbeat(lambda: [fichier("bob.txt")], interval=0.3)
        time.sleep(1.6)
        self.assertEqual(self.found("alice"), ["alice"])

    def test_republication_apres_oubli(self):
        time.sleep(1.5)                                   # alice et bob oubliés
        self.assertNotIn("alice", self.srv.state.peers)
        self.alice.start_heartbeat(lambda: [fichier("alice.txt")], interval=0.2)
        self.bob.start_heartbeat(lambda: [fichier("bob.txt")], interval=0.2)
        time.sleep(0.6)                                   # heartbeat -> not_published -> republie
        self.assertEqual(self.found("alice"), ["alice"])

    def test_token_invalide_apres_logout(self):
        self.alice.logout()
        with self.assertRaisesRegex(CentralError, "bad_token"):
            self.alice.heartbeat()


if __name__ == "__main__":
    unittest.main()