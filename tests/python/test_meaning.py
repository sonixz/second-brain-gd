import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import brain, database
from engine.assistant.llm import FakeChat
from engine.brain import meaning
from engine.brain.seed import seed_all

M = "fake-embed"


class MeaningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "m.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        self.client = FakeChat()
        database.set_setting(self.conn, "embeddings_model", M)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def note(self, title, body):
        return brain.create_note(self.conn, title, body)["id"]

    def test_keywords_drop_common_words(self):
        self.assertEqual(meaning.keywords("comment mieux dormir le soir"), ["mieux", "dormir", "soir"])
        self.assertEqual(meaning.keywords("le la"), ["le", "la"])  # nothing left: keep everything

    def test_embeds_new_and_changed_notes_only(self):
        a = self.note("Dormir", "dormir tôt repos sommeil")
        first = meaning.embed_notes(self.conn, self.client, M)["embedded"]
        self.assertGreaterEqual(first, 1)
        self.assertEqual(meaning.embed_notes(self.conn, self.client, M)["embedded"], 0)
        brain.update_note(self.conn, a, body="dormir tôt repos sommeil profond")
        self.assertEqual(meaning.embed_notes(self.conn, self.client, M)["embedded"], 1)
        st = meaning.status(self.conn, M)
        self.assertEqual(st["pending"], 0)
        self.assertEqual(st["embedded"], st["notes"])

    def test_related_ideas_and_cascade(self):
        a = self.note("Sommeil", "dormir tôt repos sommeil fatigue")
        b = self.note("Repos", "dormir tôt repos sommeil soir")
        c = self.note("Gâteau", "chocolat ballons mauves anniversaire")
        meaning.embed_notes(self.conn, self.client, M)
        rel = [r["id"] for r in meaning.related(self.conn, a)]
        self.assertEqual(rel[0], b)
        self.assertNotIn(c, rel)
        edges = meaning.related_edges(self.conn)
        self.assertIn(tuple(sorted((a, b))), {tuple(sorted((e["from"], e["to"]))) for e in edges})
        graph_edges = [e for e in brain.graph(self.conn)["edges"] if e["type"] == "related"]
        self.assertTrue(graph_edges)
        brain.delete_note(self.conn, b)
        self.assertNotIn(b, [r["id"] for r in meaning.related(self.conn, a)])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM note_embeddings WHERE note_id = ?", (b,)).fetchone()[0], 0)

    def test_already_linked_items_are_not_suggested(self):
        a = self.note("Sommeil", "dormir tôt repos sommeil fatigue")
        b = self.note("Repos", "dormir tôt repos sommeil soir")
        meaning.embed_notes(self.conn, self.client, M)
        self.assertIn(b, [r["id"] for r in meaning.related(self.conn, a)])
        self.conn.execute("INSERT INTO links (from_note, to_note, kind, created_by, created_at) VALUES (?, ?, 'wiki', 'user', '2026-11-05')",
                          (a, b))
        self.assertNotIn(b, [r["id"] for r in meaning.related(self.conn, a)])  # keeping it would only double the link
        self.assertNotIn(tuple(sorted((a, b))), {tuple(sorted((e["from"], e["to"]))) for e in meaning.related_edges(self.conn)})

    def test_new_note_becomes_closest_of_older_note(self):
        a = self.note("Atlas", "migration atlas bascule dimanche tables")
        meaning.embed_notes(self.conn, self.client, M)
        b = self.note("Bascule", "migration atlas bascule dimanche tables inventaire")
        meaning.embed_notes(self.conn, self.client, M)
        owners = {r["owner"] for r in self.conn.execute("SELECT owner FROM note_related WHERE other IN (?, ?)", (a, b))}
        self.assertIn(a, owners)  # the older note now picks the new one too
        self.assertIn(b, owners)

    def test_search_by_meaning_then_words(self):
        a = self.note("Sommeil", "dormir tôt repos sommeil")
        meaning.embed_notes(self.conn, self.client, M)
        database.set_setting(self.conn, "embeddings_status", {"available": True})
        hits = meaning.search_notes(self.conn, self.client, "dormir repos sommeil", 5)
        self.assertEqual(hits[0]["id"], a)
        self.assertEqual(hits[0]["match"], "meaning")
        words_only = meaning.search_notes(self.conn, None, "sommeil", 5)
        self.assertEqual(words_only[0]["match"], "words")

    def test_keyword_search_any_word_fallback(self):
        a = self.note("Poignée", "réparer la poignée de porte")
        hits = brain.search(self.conn, "poignée chaise")  # no note has both words
        self.assertEqual([h["id"] for h in hits], [a])

    def test_unavailable_is_recorded_and_worker_skips(self):
        self.note("X", "quelque chose")
        with mock.patch.object(FakeChat, "embed", side_effect=RuntimeError("403 no access")):
            out = meaning.embed_notes(self.conn, self.client, M)
        self.assertEqual(out["embedded"], 0)
        self.assertFalse(database.get_setting(self.conn, "embeddings_status")["available"])
        self.conn.commit()
        w = meaning.Worker(self.db, lambda: self.client)
        self.assertEqual(w.tick(), {"skipped": "embeddings unavailable"})

    def test_worker_tick_embeds(self):
        self.note("Y", "une idée neuve")
        self.conn.commit()
        self.assertEqual(meaning.Worker(self.db, lambda: None).tick(), {"skipped": "no key"})
        out = meaning.Worker(self.db, lambda: self.client).tick()
        self.assertGreaterEqual(out["notes"]["embedded"], 1)


if __name__ == "__main__":
    unittest.main()
