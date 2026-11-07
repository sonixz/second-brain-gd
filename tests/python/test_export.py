"""Loop 37D: items on Letter paper (HTML), printed to PDF by Edge when it is there."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import brain, database
from engine.brain import export_doc, table, types
from engine.brain.seed import seed_all


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "data" / "second_brain.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        n = brain.create_note(self.conn, "Paella <du> samedi", "")
        self.rid = n["id"]
        types.set_props(self.conn, self.rid, "recipe", {
            "servings": 4, "total_min": 65, "rating": 4.6, "category": "Plats principaux",
            "ingredients": ["375 ml (1 ½ tasse) de riz", "1 boîte de 796 ml de tomates en dés", "Sel et poivre"],
            "steps": [{"section": "Riz", "text": "Dorer l'oignon."}, {"section": "Fin", "text": "Servir."}]},
            merge=False, rewrite_body=True)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_a_recipe_page_has_its_own_layout_and_scales(self):
        title, doc = export_doc.page_html(self.conn, [self.rid], lang="fr", servings={self.rid: 8})
        self.assertEqual(title, "Paella <du> samedi")
        self.assertIn("@page { size: letter;", doc)
        self.assertIn("<h1>Paella &lt;du&gt; samedi</h1>", doc, "titles are escaped")
        self.assertIn("<b>Portions</b> 8", doc)
        self.assertIn("<li>750 ml de riz</li>", doc, "printed for 8: quantities doubled")
        self.assertIn("<li>2 boîtes de 796 ml de tomates en dés</li>", doc)
        self.assertIn("<h3>Riz</h3>", doc)

    def test_a_grocery_list_prints_boxes_and_notes_print_their_text(self):
        out = table.save_grocery(self.conn, [{"id": self.rid}], "fr")
        n = brain.create_note(self.conn, "Idées", "# Titre\n\nUn **point** important, voir [[Paella]].\n\n1. un\n2. deux\n\n#tag")
        _t, doc = export_doc.page_html(self.conn, [out["note_id"], n["id"]], lang="fr")
        self.assertIn('<ul class="check">', doc)
        self.assertIn("<li class=\"\">riz — 375 ml</li>", doc)
        self.assertEqual(doc.count('<section class="page">'), 2, "one page per item")
        self.assertIn("<p>Un <b>point</b> important, voir Paella.</p>", doc)
        self.assertIn("<ol>", doc)
        self.assertNotIn("#tag", doc)

    def test_without_edge_the_page_is_kept_and_said(self):
        with mock.patch.dict(os.environ, {"SBGD_EDGE": str(Path(self.tmp.name) / "no-edge.exe")}):
            out = export_doc.export(self.conn, [self.rid], "pdf", lang="fr")
        self.assertIsNone(out["pdf"])
        self.assertIn("Ctrl+P", out["why"])
        self.assertTrue(Path(out["html"]).exists())
        self.assertEqual(Path(out["html"]).parent, Path(self.tmp.name) / "exports")

    def test_edge_is_called_headless_with_a_throwaway_profile(self):
        seen = {}

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            pdf = Path(next(a for a in cmd if a.startswith("--print-to-pdf=")).split("=", 1)[1])
            pdf.write_bytes(b"%PDF-1.7 " + b"x" * 1000)
        edge = Path(self.tmp.name) / "msedge.exe"
        edge.write_text("")
        with mock.patch.dict(os.environ, {"SBGD_EDGE": str(edge)}), mock.patch.object(export_doc.subprocess, "run", fake_run):
            out = export_doc.export(self.conn, [self.rid], "pdf", lang="fr")
        self.assertTrue(out["pdf"].endswith(".pdf"))
        self.assertIn("--headless=new", seen["cmd"])
        profile = next(a for a in seen["cmd"] if a.startswith("--user-data-dir=")).split("=", 1)[1]
        self.assertFalse(Path(profile).exists(), "the temporary profile is removed")
        self.assertTrue(seen["cmd"][-1].startswith("file:"))


if __name__ == "__main__":
    unittest.main()
