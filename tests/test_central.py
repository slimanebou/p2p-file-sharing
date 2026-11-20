"""Tests du serveur central : on le lance sur un port libre, dans un thread."""
import threading
import unittest

from central import CentralServer
from p2p.protocol import connect, request


class CentralTestCase(unittest.TestCase):
    """Base réutilisée par les tests des phases suivantes."""

    def setUp(self):
        self.srv = CentralServer(("127.0.0.1", 0))      # port 0 = le système choisit
        self.port = self.srv.server_address[1]
        self.thread = threading.Thread(target=self.srv.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

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


if __name__ == "__main__":
    unittest.main()