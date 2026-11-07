"""Loop 37C: the table view and the grocery list added up from ticked recipes."""
import tempfile
import unittest
from pathlib import Path

from engine import brain, database
from engine.brain import table, types
from engine.brain.seed import seed_all
from engine.brain import structure


class TableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "data" / "second_brain.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        database.set_setting(self.conn, "ui_language", "fr")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _recipe(self, title, servings, lines, **more):
        n = brain.create_note(self.conn, title, "")
        types.set_props(self.conn, n["id"], "recipe", {"servings": servings, "ingredients": lines, **more}, merge=False,
                        rewrite_body=True)
        return n["id"]

    def test_rows_of_a_type_with_its_fields_and_search(self):
        a = self._recipe("Paella", 4, ["375 ml de riz", "454 g de crevettes"], total_min=65, rating=4.5)
        self._recipe("Pâté chinois", 4, ["450 g de boeuf haché"], total_min=80, tried=True)
        brain.create_note(self.conn, "Une idée", "rien à voir")
        r = table.rows(self.conn, "recipe", lang="fr")
        keys = [c["key"] for c in r["columns"]]
        self.assertEqual(keys[:2], ["title", "place"])
        self.assertIn("total_min", keys)
        self.assertNotIn("ingredients", keys, "long fields stay on the card")
        self.assertEqual({x["title"] for x in r["rows"]}, {"Paella", "Pâté chinois"})
        paella = next(x for x in r["rows"] if x["id"] == a)
        self.assertEqual((paella["total_min"], paella["rating"], paella["_ingredients"]), (65, 4.5, 2))
        self.assertEqual([x["title"] for x in table.rows(self.conn, "recipe", query="crevette")["rows"]], ["Paella"],
                         "search reaches the ingredients")
        everything = table.rows(self.conn, "", lang="fr")
        self.assertIn("item_type", [c["key"] for c in everything["columns"]])
        self.assertIn("Une idée", [x["title"] for x in everything["rows"]])
        with self.assertRaises(types.TypeError_):
            table.rows(self.conn, "nope")

    def test_saved_views(self):
        table.save_view(self.conn, "Rapides", "recipe", "", "total_min")
        table.save_view(self.conn, "rapides", "recipe", "poulet", "total_min", True)
        v = table.views(self.conn)
        self.assertEqual(len(v), 1, "the same name replaces the view")
        self.assertEqual((v[0]["query"], v[0]["desc"]), ("poulet", True))
        self.assertEqual(table.delete_view(self.conn, "RAPIDES"), [])

    def test_the_grocery_list_adds_up_by_aisle(self):
        a = self._recipe("Paella", 4, ["375 ml (1 ½ tasse) de riz", "2 c. à soupe (30 ml) d'huile d'olive", "1 oignon, haché",
                                       "1 boîte de 796 ml (28 oz) de tomates en dés", "454 g de crevettes", "Sel et poivre"])
        b = self._recipe("Chili", 6, ["2 oignons moyens", "1 boîte de 796 ml de tomates en dés", "1 c. à soupe d’huile d’olive",
                                      "1 kg de boeuf haché", "1 lb de boeuf haché", "Sel"])
        g = table.grocery(self.conn, [{"id": a, "servings": 8}, {"id": b}], "fr")
        flat = {i["name"]: i for grp in g["groups"] for i in grp["items"]}
        self.assertEqual(flat["oignon"]["display"], "4", "2 (paella ×2) + 2 medium onions")
        self.assertEqual(flat["tomates en dés"]["display"], "3 boîtes de 796 ml")
        self.assertEqual(flat["huile d'olive"]["display"], "75 ml", "60 ml + 1 tbsp (15 ml)")
        self.assertEqual(flat["riz"]["display"], "750 ml")
        self.assertEqual(flat["boeuf haché"]["display"], "1,45 kg")
        self.assertEqual(flat["Sel et poivre"]["display"], "au goût")
        self.assertEqual(sorted(flat["oignon"]["recipes"]), ["Chili", "Paella"])
        aisles = [grp["aisle"] for grp in g["groups"]]
        self.assertEqual(aisles, sorted(aisles, key=table.AISLES.index), "aisles in shop order")
        self.assertEqual(flat["crevettes"]["aisle"], "meat")
        self.assertEqual(flat["tomates en dés"]["aisle"], "pantry")
        self.assertEqual(table.aisle_of("quinoa"), "other", "unknown words are not guessed")

    def test_saving_the_list_makes_a_note_and_fills_the_groceries_checklist(self):
        a = self._recipe("Paella", 4, ["375 ml de riz", "1 oignon"])
        try:
            cl = structure.find_checklist(self.conn, "Épicerie")
        except brain.NotFound:
            cl = structure.create_checklist(self.conn, "Épicerie", brain.create_space(self.conn, "Maison", "area")["id"])
        out = table.save_grocery(self.conn, [{"id": a}], "fr")
        note = brain.get_note(self.conn, out["note_id"])
        self.assertTrue(note["title"].startswith("Liste d'épicerie du "))
        self.assertIn("- [ ] riz — 375 ml", note["body"])
        self.assertIn("[[Paella]]", note["body"])
        linked = self.conn.execute("SELECT 1 FROM links WHERE from_note = ? AND to_note = ?", (out["note_id"], a)).fetchone()
        self.assertIsNotNone(linked, "the list links to its recipes")
        items = [i["text"] for i in structure.get_checklist(self.conn, cl["id"])["items"]]
        self.assertTrue({"oignon — 1", "riz — 375 ml"} <= set(items))
        with self.assertRaises(ValueError):
            table.save_grocery(self.conn, [{"id": brain.create_note(self.conn, "x", "")["id"]}], "fr")


if __name__ == "__main__":
    unittest.main()
