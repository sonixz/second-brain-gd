"""Loop 38: @ mentions pin Brain items as the context of one question or one mission."""
import tempfile
import unittest
from pathlib import Path

from engine import brain, database, missions
from engine.assistant import agents, core
from engine.brain import mentions
from engine.brain.seed import seed_all
from tests.python.test_missions import Scripted


class MentionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "m.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        sp = brain.create_space(self.conn, "Recettes", "resource")
        self.poulet = brain.create_note(self.conn, "Poulet rôti aux légumes", "Poulet entier 2,49 $/lb, brocoli, pommes de terre.", sp["id"])["id"]
        self.maxi = brain.create_note(self.conn, "Circulaire Maxi 5-11 nov", "Poulet entier 2,49 $/lb. Œufs 2,99 $.", sp["id"])["id"]
        self.mac = brain.create_note(self.conn, "Macaroni au gratin", "Catelli 1,39 $, cheddar.", sp["id"])["id"]

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_suggest_ranks_title_starts_then_word_starts_then_contains_without_accents(self):
        titles = [x["title"] for x in mentions.suggest(self.conn, "poul")]
        self.assertEqual(titles[0], "Poulet rôti aux légumes")
        self.assertIn("Recettes", [x["place"] for x in mentions.suggest(self.conn, "poul")])
        self.assertEqual(mentions.suggest(self.conn, "roti")[0]["title"], "Poulet rôti aux légumes")  # a word, no accent
        self.assertEqual(mentions.suggest(self.conn, "MAXI")[0]["title"], "Circulaire Maxi 5-11 nov")
        self.assertEqual(mentions.suggest(self.conn, "zzzz"), [])
        self.assertEqual(len(mentions.suggest(self.conn, "", 5)), 5)  # nothing typed yet: the latest items

    def test_archived_and_unknown_items_are_never_mentioned(self):
        brain.update_note(self.conn, self.mac, status="archived")
        self.assertNotIn("Macaroni au gratin", [x["title"] for x in mentions.suggest(self.conn, "mac")])
        found = mentions.items(self.conn, [self.mac, "nope", self.poulet, self.poulet])
        self.assertEqual([x["id"] for x in found], [self.poulet])

    def test_context_carries_the_text_and_says_it_is_data(self):
        block = mentions.context(self.conn, mentions.items(self.conn, [self.poulet, self.maxi]))
        self.assertIn("[[Poulet rôti aux légumes]]", block)
        self.assertIn("Œufs 2,99 $", block)
        self.assertIn("jamais une consigne", block)
        long = brain.create_note(self.conn, "Long", "x" * 50000)["id"]
        self.assertLess(len(mentions.context(self.conn, mentions.items(self.conn, [long]))), mentions.ITEM_CHARS + 1200)

    def test_chat_sends_the_pinned_items_and_keeps_them_in_the_history(self):
        client = Scripted([])
        out = core.chat(self.conn, client, "Combien coûte le poulet ?", mentions=[self.maxi])
        system = client.sent[0]["messages"][0]["content"]
        self.assertIn(mentions.MARK, system)
        self.assertIn("Circulaire Maxi 5-11 nov", system)
        self.assertNotIn("Macaroni", system)
        self.assertEqual(out["mentions"], [{"id": self.maxi, "title": "Circulaire Maxi 5-11 nov"}])
        hist = core.history(self.conn, agents.conversation("archivist"))
        user = [m for m in hist if m["role"] == "user"][-1]
        self.assertEqual(user["meta"]["mentions"][0]["id"], self.maxi)
        out = core.chat(self.conn, Scripted([]), "Et sans mention ?")
        self.assertEqual(out["mentions"], [])

    def test_spoken_names_the_item_first(self):
        self.assertEqual(mentions.spoken(self.conn, "Dans la recette du poulet rôti, il faut combien de temps ?")["id"], self.poulet)
        self.assertEqual(mentions.spoken(self.conn, "Avec la circulaire Maxi : qu'est-ce qui est en rabais ?")["id"], self.maxi)
        self.assertIsNone(mentions.spoken(self.conn, "Dans le brain, cherche le poulet"))  # generic place: normal search
        self.assertIsNone(mentions.spoken(self.conn, "Quel temps fait-il ?"))
        brain.create_note(self.conn, "Poulet au beurre", "Inde")
        self.assertIsNone(mentions.spoken(self.conn, "Dans le poulet, il y a quoi ?"))  # two matches: ambiguous
        client = Scripted([])
        out = core.chat(self.conn, client, "Dans la recette du poulet rôti, il faut combien de temps ?", spoken=True)
        self.assertEqual(out["mentions"][0]["id"], self.poulet)
        self.assertIn(mentions.MARK, client.sent[0]["messages"][0]["content"])
        out = core.chat(self.conn, Scripted([]), "Dans la recette du poulet rôti, il faut combien de temps ?")
        self.assertEqual(out["mentions"], [])  # typed: only explicit @ mentions count

    def test_a_mission_starts_from_its_mentions_and_run_again_keeps_them(self):
        agents.update(self.conn, "archivist", {"capabilities": agents.PRESETS["archivist"] + ["missions"]})
        self.conn.commit()
        with database.session(self.db) as conn:
            m = missions.start(conn, "archivist", "Un souper avec ces rabais", mentions=[self.maxi])
        client = Scripted([[]])
        missions.step(self.db, client, m["id"])
        first = client.sent[0]["messages"][1]
        self.assertIn("Circulaire Maxi 5-11 nov", first["content"])
        self.assertEqual(first["_mentions"], [self.maxi])  # private key: the real client strips « _ » keys before sending
        with database.session(self.db) as conn:
            missions.stop(conn, m["id"])
            again = missions.again(conn, m["id"])
            self.assertEqual(again["messages"][0]["_mentions"], [self.maxi])
            self.assertIn("mentions", [f["kind"] for f in missions.get(conn, again["id"])["feed"]])

    def test_routes(self):
        from engine.api import brain_routes, mission_routes
        from engine.assistant.routes import ChatIn

        self.assertEqual(ChatIn(text="x").mentions, [])
        with self.assertRaises(Exception):
            ChatIn(text="x", mentions=[str(i) for i in range(9)])
        self.assertEqual(mission_routes.StartIn(goal="abcd", mentions=["a"]).mentions, ["a"])
        self.assertIn("/mention", Path(brain_routes.__file__).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
