"""Tests de la couche protocole, sans réseau réel : socket.socketpair() crée deux sockets reliées."""
import os
import socket
import tempfile
import threading
import unittest

from p2p.protocol import Connection, ProtocolError, sha256_file


class TestProtocol(unittest.TestCase):
    def setUp(self):
        a, b = socket.socketpair()
        self.a, self.b = Connection(a), Connection(b)

    def tearDown(self):
        self.a.close()
        self.b.close()

    def test_un_message(self):
        self.a.send_msg({"type": "PING", "texte": "héhé"})
        self.assertEqual(self.b.recv_msg(), {"type": "PING", "texte": "héhé"})

    def test_mille_messages_colles(self):
        # Envoyés d'un coup : TCP peut les livrer collés, on doit les séparer.
        # L'envoi tourne dans un thread : sinon le tampon de la socket se remplit
        # et send() bloque, puisque personne ne lit encore.
        t = threading.Thread(target=lambda: [self.a.send_msg({"n": i}) for i in range(1000)])
        t.start()
        for i in range(1000):
            self.assertEqual(self.b.recv_msg(), {"n": i})
        t.join()

    def test_message_coupe_en_morceaux(self):
        # Un message qui arrive en deux recv() distincts.
        self.a.sock.sendall(b'{"type": "SEA')
        self.a.sock.sendall(b'RCH"}\n')
        self.assertEqual(self.b.recv_msg(), {"type": "SEARCH"})

    def test_fermeture_propre(self):
        self.a.close()
        self.assertIsNone(self.b.recv_msg())

    def test_json_invalide(self):
        self.a.sock.sendall(b"pas du json\n")
        with self.assertRaises(ProtocolError):
            self.b.recv_msg()

    def test_fichier_puis_message(self):
        # En-tête JSON, octets du fichier, puis un autre message : rien ne doit se mélanger.
        data = os.urandom(300_000)
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "src.bin"), os.path.join(d, "dst.bin")
            with open(src, "wb") as f:
                f.write(data)

            def emetteur():
                self.a.send_msg({"size": len(data)})
                self.a.send_file(src)
                self.a.send_msg({"type": "FIN"})

            t = threading.Thread(target=emetteur)
            t.start()
            head = self.b.recv_msg()
            digest = self.b.recv_file(dst, head["size"])
            fin = self.b.recv_msg()
            t.join()

            self.assertEqual(digest, sha256_file(src))
            self.assertEqual(fin, {"type": "FIN"})


if __name__ == "__main__":
    unittest.main()