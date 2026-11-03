import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from engine import brain, database
from engine.brain import structure
from engine.brain.seed import seed_all


class StructureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "s.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def area(self, name):
        return next(a for a in structure.structure(self.conn)["areas"] if a["name"] == name)

    def test_seed_areas_and_grocery_list_once(self):
        names = [a["name"] for a in structure.structure(self.conn)["areas"]]
        self.assertEqual(sorted(names), ["Famille", "Maison", "Santé", "Vision au travail"])
        self.assertEqual([c["name"] for c in structure.list_checklists(self.conn)], ["Épicerie"])
        self.assertFalse(structure.seed_structure(self.conn))

    def test_project_under_area_with_next_actions(self):
        p = structure.create_project(self.conn, "Vacances d'été", self.area("Famille")["id"], goal="Une semaine au lac",
                                     due_date="2027-06-30")
        self.assertEqual(p["area_id"], self.area("Famille")["id"])
        self.assertIn(p["id"], [x["id"] for x in self.area("Famille")["projects"]])
        today = date.today()
        structure.add_task(self.conn, "Réserver le chalet", p["id"], (today - timedelta(days=1)).isoformat())
        t2 = structure.add_task(self.conn, "Faire la liste", p["id"], today.isoformat())
        t3 = structure.add_task(self.conn, "Acheter des lunettes", p["id"], (today + timedelta(days=3)).isoformat())
        d = structure.today(self.conn)
        self.assertEqual([t["title"] for t in d["overdue"]], ["Réserver le chalet"])
        self.assertEqual([t["title"] for t in d["today"]], ["Faire la liste"])
        self.assertEqual([t["title"] for t in d["soon"]], ["Acheter des lunettes"])
        self.assertEqual(d["next_actions"][0]["remaining"], 3)
        structure.set_task(self.conn, t2["id"], done=True)
        self.assertEqual(brain.get_note(self.conn, t2["id"])["status"], "done")
        self.assertIsNotNone(brain.get_note(self.conn, t2["id"])["done_at"])
        structure.set_task(self.conn, t3["id"], due_date=None)
        self.assertIsNone(brain.get_note(self.conn, t3["id"])["due_date"])
        card = structure.card(self.conn, p["id"])
        self.assertEqual(card["goal"], "Une semaine au lac")
        self.assertEqual(len(card["tasks"]), 3)

    def test_project_without_tasks_is_flagged(self):
        structure.create_project(self.conn, "Idée floue")
        self.assertIn("Idée floue", [p["name"] for p in structure.today(self.conn)["projects_without_next_action"]])

    def test_validation(self):
        with self.assertRaises(ValueError):
            structure.create_project(self.conn, "X", due_date="demain")
        with self.assertRaises(ValueError):
            structure.update_space(self.conn, brain.INBOX_ID, name="Boîte")
        p = structure.create_project(self.conn, "P")
        with self.assertRaises(ValueError):
            structure.update_space(self.conn, p["id"], area_id=p["id"])

    def test_checklist_items(self):
        groceries = structure.find_checklist(self.conn, "épicerie")
        structure.add_items(self.conn, groceries["id"], ["Lait", "Oeufs", "lait", "  "])
        cl = structure.get_checklist(self.conn, groceries["id"])
        self.assertEqual([i["text"] for i in cl["items"]], ["Lait", "Oeufs"])
        structure.set_item(self.conn, cl["items"][0]["id"], done=True)
        cl = structure.clear_done(self.conn, groceries["id"])
        self.assertEqual([i["text"] for i in cl["items"]], ["Oeufs"])

    def test_graph_links_projects_to_areas(self):
        p = structure.create_project(self.conn, "Atlas", self.area("Vision au travail")["id"])
        edges = brain.graph(self.conn)["edges"]
        self.assertIn({"from": f"space:{p['id']}", "to": f"space:{self.area('Vision au travail')['id']}", "type": "area"}, edges)


if __name__ == "__main__":
    unittest.main()
