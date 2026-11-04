"""Loop 11: Brain packs — export a selection, import it elsewhere as a layer, switch it off, merge, remove."""
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from engine import brain, database
from engine.assistant.llm import FakeChat
from engine.brain import archivist, meaning, packs
from engine.brain.seed import seed_brain


def make_brain(path: Path):
    database.migrate(path)
    with database.session(path) as conn:
        seed_brain(conn)
        database.set_setting(conn, "embeddings_model", "fake-embed")
        database.set_setting(conn, "embeddings_status", {"available": True})


class PackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.a, self.b = root / "a.sqlite3", root / "b.sqlite3"
        make_brain(self.a)
        make_brain(self.b)
        self.out = root / "exports"
        client = FakeChat()
        with database.session(self.a) as conn:
            sp = brain.create_space(conn, "Game design", "resource")
            self.n2 = brain.create_note(conn, "Économie", "Ressources rares et échanges #design", sp["id"])["id"]
            self.n1 = brain.create_note(conn, "Boucle de jeu", "Explorer, récolter, construire. Voir [[Économie]] #design", sp["id"])["id"]
            self.other = brain.create_note(conn, "Recette de pain", "Farine et levain")["id"]
            archivist.save_meta(conn, self.n1, summary="Une boucle simple.", themes=["design"], filed=1)
        with database.session(self.a) as conn:
            rows = [dict(r) for r in meaning.pending_notes(conn, "fake-embed")]
            vecs = client.embed("fake-embed", [r["title"] + " " + r["body"] for r in rows])
            meaning.store_notes(conn, "fake-embed", rows, vecs, None)

    def tearDown(self):
        self.tmp.cleanup()

    def export_place(self):
        return packs.export(self.a, {"place": "Game design"}, self.out, "Game design", author="Testeur", licence="CC-BY")

    def test_preview_lists_what_leaves_and_what_never_does(self):
        with database.session(self.a) as conn:
            pv = packs.preview(conn, {"place": "Game design"})
        self.assertEqual(pv["items"], 2)
        self.assertIn("Game design", pv["places"])
        self.assertIn("your API keys", pv["never_included"])

    def test_export_holds_only_the_selection_and_no_private_tables(self):
        res = self.export_place()
        path = Path(res["path"])
        self.assertTrue(path.name.startswith("game-design-") and path.suffix == ".brain")
        with zipfile.ZipFile(path) as z:
            self.assertEqual(set(z.namelist()), {"manifest.json", "data.sqlite"})
            man = json.loads(z.read("manifest.json"))
            data = Path(self.tmp.name) / "peek.sqlite3"
            data.write_bytes(z.read("data.sqlite"))
        self.assertEqual((man["format"], man["counts"]["items"], man["embedding_model"]), ("sbgd-brain-pack", 2, "fake-embed"))
        c = database.connect(data)
        titles = sorted(r["title"] for r in c.execute("SELECT title FROM notes"))
        self.assertEqual(titles, ["Boucle de jeu", "Économie"])  # not the bread recipe, not the guide
        for private in ("application_settings", "assistant_messages", "system_events"):
            self.assertEqual(c.execute(f"SELECT COUNT(*) FROM {private}").fetchone()[0], 0, private)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM note_embeddings").fetchone()[0], 2)
        c.close()

    def test_import_as_a_layer_then_off_on_merge(self):
        res = packs.import_pack(self.b, Path(self.export_place()["path"]))
        self.assertEqual(res["counts"]["items"], 2)
        self.assertEqual(res["counts"]["vectors_copied"], 2)  # same embedding model: vectors reused
        lid = res["layer_id"]
        with database.session(self.b) as conn:
            titles = {n["title"] for n in brain.list_notes(conn)}
            self.assertTrue({"Boucle de jeu", "Économie"} <= titles)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM links WHERE created_by = 'import'").fetchone()[0], 1)
            self.assertEqual(archivist.get_meta(conn, conn.execute("SELECT id FROM notes WHERE title = 'Boucle de jeu'").fetchone()[0])["summary"],
                             "Une boucle simple.")
            packs.set_enabled(conn, lid, False)
            self.assertFalse({"Boucle de jeu"} & {n["title"] for n in brain.list_notes(conn)})
            self.assertNotIn("Game design", [s["name"] for s in brain.list_spaces(conn)])
            packs.set_enabled(conn, lid, True)
            self.assertIn("Boucle de jeu", {n["title"] for n in brain.list_notes(conn)})
            packs.merge(conn, lid)
            self.assertEqual(packs.layers(conn), [])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM notes WHERE layer_id IS NOT NULL").fetchone()[0], 0)

    def test_reimport_skips_duplicates_and_remove_only_touches_the_layer(self):
        path = Path(self.export_place()["path"])
        first = packs.import_pack(self.b, path)
        again = packs.import_pack(self.b, path)
        self.assertEqual((again["counts"]["items"], again["counts"]["duplicates"]), (0, 2))
        with database.session(self.b) as conn:
            mine = brain.create_note(conn, "Mon idée", "à moi")["id"]
            packs.remove(conn, first["layer_id"])
            titles = {n["title"] for n in brain.list_notes(conn)}
            self.assertNotIn("Boucle de jeu", titles)
            self.assertIn("Mon idée", titles)
            self.assertTrue(brain.get_note(conn, mine))

    def test_damaged_or_foreign_files_are_refused(self):
        path = Path(self.export_place()["path"])
        bad = Path(self.tmp.name) / "bad.brain"
        with zipfile.ZipFile(path) as z, zipfile.ZipFile(bad, "w") as w:
            w.writestr("manifest.json", z.read("manifest.json"))
            w.writestr("data.sqlite", z.read("data.sqlite") + b"tampered")
        with self.assertRaises(packs.PackError) as ctx:
            packs.import_pack(self.b, bad)
        self.assertIn("checksum", str(ctx.exception))
        evil = Path(self.tmp.name) / "evil.brain"
        with zipfile.ZipFile(evil, "w") as w:
            w.writestr("manifest.json", "{}")
            w.writestr("data.sqlite", b"")
            w.writestr("../escape.py", "print(1)")
        with self.assertRaises(packs.PackError):
            packs.import_pack(self.b, evil)
        text = Path(self.tmp.name) / "notes.txt"
        text.write_text("hello")
        with self.assertRaises(packs.PackError):
            packs.import_pack(self.b, text)
        with database.session(self.b) as conn:
            self.assertEqual(packs.layers(conn), [])  # nothing half-imported

    def test_other_embedding_model_leaves_items_to_re_embed(self):
        with database.session(self.b) as conn:
            database.set_setting(conn, "embeddings_model", "another-model")
        res = packs.import_pack(self.b, Path(self.export_place()["path"]))
        self.assertTrue(res["counts"]["re_embed"])
        with database.session(self.b) as conn:
            pending = {r["title"] for r in meaning.pending_notes(conn, "another-model")}
        self.assertTrue({"Boucle de jeu", "Économie"} <= pending)


class VoicePackTests(unittest.TestCase):
    def test_export_and_manage_packs_by_voice(self):
        from engine.assistant import core
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / "data").mkdir()
        db = root / "data" / "second_brain.sqlite3"
        make_brain(db)
        client = FakeChat()
        conn = database.connect(db)
        try:
            sp = brain.create_space(conn, "Atlas", "project")
            brain.create_note(conn, "Plan Atlas", "étapes", sp["id"])
            conn.commit()
            out = core.chat(conn, client, "Exporte le projet Atlas")
            conn.commit()
            self.assertEqual(out["ui_actions"][0]["action"], "pack_exported")
            path = Path(out["ui_actions"][0]["path"])
            self.assertEqual(path.parent, root / "exports")
            self.assertTrue(path.exists())
            self.assertIn("1 éléments", out["reply"])
            other = root / "data" / "other.sqlite3"
            make_brain(other)
            packs.import_pack(other, path)
            oc = database.connect(other)
            out = core.chat(oc, client, "Désactive le pack Atlas")
            oc.commit()
            self.assertFalse(packs.layers(oc)[0]["enabled"])
            out = core.chat(oc, client, "Retire le pack Atlas")
            oc.commit()
            self.assertEqual(packs.layers(oc), [])
            oc.close()
        finally:
            conn.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
