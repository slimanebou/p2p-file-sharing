"""Test de charge : 20 hôtes s'authentifient et publient en même temps, puis cherchent en parallèle.

Vérifie l'exigence du sujet « plusieurs serveurs distants peuvent s'authentifier en même temps »
et que l'index reste cohérent sous accès concurrents (verrou).
"""
import threading
import time

from tests.test_central import CentralTestCase

N_PEERS = 20
N_FILES = 50


def files_of(user):
    return [{"name": f"{user}/doc{i}.txt", "desc": f"document numero {i} de {user} commun",
             "author": user, "date": "2026-11-21", "size": i, "sha256": ""}
            for i in range(N_FILES)]


class TestCharge(CentralTestCase):
    def test_vingt_hotes_simultanes(self):
        clients, errors = {}, []

        def peer(i):
            user = f"peer{i:02d}"
            try:
                c = self.client()
                c.register(user, "pw")
                c.login(user, "pw")
                c.publish("127.0.0.1", 7000 + i, files_of(user))
                clients[user] = c
            except Exception as e:            # noqa: BLE001 - on veut toute erreur
                errors.append(f"{user}: {e}")

        start = time.perf_counter()
        threads = [threading.Thread(target=peer, args=(i,)) for i in range(N_PEERS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.perf_counter() - start

        self.assertEqual(errors, [])
        self.assertEqual(len(self.srv.state.peers), N_PEERS)
        self.assertEqual(sum(len(p["files"]) for p in self.srv.state.peers.values()),
                         N_PEERS * N_FILES)

        # 20 recherches en parallèle : chacune voit les fichiers des 19 autres hôtes
        counts = []
        searches = [threading.Thread(target=lambda c=c: counts.append(len(c.search("commun"))))
                    for c in clients.values()]
        for t in searches:
            t.start()
        for t in searches:
            t.join()
        self.assertEqual(counts, [200] * N_PEERS)      # plafonné à MAX_RESULTS = 200
        self.assertEqual(len(clients["peer00"].search("peer03/doc7.txt")), 1)   # recherche précise
        print(f"\n  {N_PEERS} hôtes authentifiés et publiés en {elapsed:.2f} s")