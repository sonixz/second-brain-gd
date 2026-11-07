"""Loop 37B: typed items. A recipe page becomes a recipe item without AI; agents can define their own types."""
import json
import tempfile
import unittest
from pathlib import Path

from engine import brain, database
from engine.assistant.llm import FakeChat
from engine.brain import archivist, types
from engine.brain.seed import seed_all
from engine.sources import core, recipe

# Our own sample recipe (not copied from any site), wrapped the way recipe sites nest it: a @graph with a WebSite.
RECIPE = {
    "@context": "https://schema.org",
    "@graph": [
        {"@type": "WebSite", "name": "Cuisine de test"},
        {"@type": ["Recipe"], "name": "Paella du samedi", "recipeYield": ["4", "4 portions"],
         "prepTime": "PT25M", "cookTime": "PT40M", "totalTime": "PT1H5M",
         "aggregateRating": {"@type": "AggregateRating", "ratingValue": "4.6", "ratingCount": "212"},
         "recipeCategory": "Plats principaux", "recipeCuisine": "Espagnole", "keywords": "riz, fruits de mer, safran",
         "image": ["https://example.com/img/1x1/paella.jpg", "https://example.com/img/4x3/paella.jpg"],
         "description": "Une paella simple pour la famille.",
         "recipeIngredient": ["375 ml (1 ½ tasse) de riz à paella", "2 c. à soupe (30 ml) d'huile d'olive",
                              "1 oignon, haché", "1 boîte de 796 ml (28 oz) de tomates en dés",
                              "454 g (1 lb) de crevettes, décortiquées", "1 pincée de safran", "Sel et poivre"],
         "recipeInstructions": [
             {"@type": "HowToSection", "name": "Riz", "itemListElement": [
                 {"@type": "HowToStep", "text": "Dans une grande poêle, dorer l'oignon dans l'huile."},
                 {"@type": "HowToStep", "text": "Ajouter le riz, les tomates et le safran."}]},
             {"@type": "HowToSection", "name": "Crevettes", "itemListElement": [
                 {"@type": "HowToStep", "text": "Déposer les crevettes sur le riz et cuire 10 minutes."}]}]}]}
PAGE = ("<html><head><title>Paella du samedi | Cuisine de test</title><script type='application/ld+json'>"
        + json.dumps(RECIPE, ensure_ascii=False) + "</script></head><body><h1>Paella du samedi</h1>"
        + "<p>Une paella simple pour la famille, prête en une heure.</p>" * 6 + "</body></html>")


class TypedItemTests(unittest.TestCase):
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

    def test_ingredient_lines_are_understood(self):
        cases = {
            "2 c. à soupe (30 ml) d'huile d'olive": (2, "tbsp", "huile d'olive", {"qty": 30, "unit": "ml"}, None),
            "1 boîte de 796 ml (28 oz) de tomates en dés": (1, "can", "tomates en dés", None, {"qty": 796, "unit": "ml"}),
            "1 ½ tasse (375 ml) de lait": (1.5, "cup", "lait", {"qty": 375, "unit": "ml"}, None),
            "2 gousses d’ail, hachées": (2, "clove", "ail", None, None),
            "1 poulet entier d’environ 1,4 kg (3 lb)": (1, None, "poulet entier d’environ 1,4 kg", None, None),
            "Sel et poivre": (None, None, "Sel et poivre", None, None),
            "1 (28 oz) can crushed tomatoes": (1, "can", "crushed tomatoes", None, {"qty": 28, "unit": "oz"}),
            "2 to 3 cups flour": (2, "cup", "flour", None, None),
        }
        for line, (q, u, name, metric, size) in cases.items():
            i = recipe.parse_ingredient(line)
            self.assertEqual((i["qty"], i["unit"], i["name"], i["metric"], i["size"]), (q, u, name, metric, size), line)
        self.assertEqual(recipe.parse_ingredient("2 gousses d’ail, hachées")["note"], "hachées")
        self.assertEqual(recipe.parse_ingredient("2 to 3 cups flour")["qty_max"], 3)
        self.assertEqual(recipe.base_amount(recipe.parse_ingredient("2 c. à soupe (30 ml) d'huile")), (30.0, "ml"))
        self.assertEqual(recipe.base_amount(recipe.parse_ingredient("1 lb de boeuf")), (454.0, "g"))
        self.assertIsNone(recipe.base_amount(recipe.parse_ingredient("1 oignon")))
        self.assertEqual([recipe.minutes(x) for x in ("PT1H20M", "P0DT0H30M", "PT45M", "", "PT0M")], [80, 30, 45, None, None])
        self.assertEqual(recipe.fmt_qty(1.5), "1 ½")
        self.assertEqual(recipe.fmt_qty(0.333), "⅓")

    def test_a_recipe_page_becomes_a_recipe_without_ai(self):
        src = core.ingest_page(self.conn, None, "https://example.com/recettes/paella", "Paella | Cuisine de test", PAGE, "")
        self.assertIn("recipe", src)
        nid = src["note_id"]
        note = brain.get_note(self.conn, nid)
        self.assertEqual(note["title"], "Paella du samedi")
        p = types.get_props(self.conn, nid)
        self.assertEqual(p["type"], "recipe")
        props = p["props"]
        self.assertEqual((props["servings"], props["prep_min"], props["cook_min"], props["total_min"]), (4, 25, 40, 65))
        self.assertEqual((props["rating"], props["votes"]), (4.6, 212))
        self.assertEqual(props["picture"], "https://example.com/img/4x3/paella.jpg")
        self.assertEqual(props["keywords"], ["riz", "fruits de mer", "safran"])
        self.assertEqual(len(props["ingredients"]), 7)
        self.assertEqual([s["section"] for s in props["steps"]], ["Riz", "Riz", "Crevettes"])
        self.assertIn("Pour 4 portions · Préparation 25 min · Cuisson 40 min · Total 1 h 05 · ★ 4,6 (212 votes)", note["body"])
        self.assertIn("- 1 boîte de 796 ml (28 oz) de tomates en dés", note["body"])
        self.assertIn("Crevettes :\n3. Déposer les crevettes", note["body"])
        self.assertIn("Source: https://example.com/recettes/paella", note["body"])
        item = archivist.item(self.conn, nid, True)
        self.assertEqual((item["item_type"], item["type_def"]["fr"]), ("recipe", "Recette"))
        self.assertEqual(self.conn.execute("SELECT title FROM sources WHERE note_id = ?", (nid,)).fetchone()[0], "Paella du samedi")
        # filing it afterwards keeps it a recipe
        archivist.file_item(self.conn, FakeChat(), nid)
        self.assertEqual(archivist.item(self.conn, nid)["item_type"], "recipe")

    def test_a_page_without_a_recipe_stays_a_page(self):
        page = "<html><head><title>Article</title></head><body>" + "<p>Un article sans recette.</p>" * 20 + "</body></html>"
        src = core.ingest_page(self.conn, None, "https://example.com/article", "Article", page, "")
        self.assertNotIn("recipe", src)
        self.assertIsNone(types.get_props(self.conn, src["note_id"]))

    def test_fields_are_edited_merged_and_cleared_and_notes_survive(self):
        src = core.ingest_page(self.conn, None, "https://example.com/recettes/paella", "Paella", PAGE, "")
        nid = src["note_id"]
        brain.update_note(self.conn, nid, body=brain.get_note(self.conn, nid)["body"] + "\n\nMes notes :\nLes enfants ont adoré.")
        types.set_props(self.conn, nid, "recipe", {"servings": "6", "tried": "oui", "rating": 9, "prep_min": ""},
                        rewrite_body=True)
        props = types.get_props(self.conn, nid)["props"]
        self.assertEqual((props["servings"], props["tried"], props["rating"]), (6, True, 5.0))
        self.assertNotIn("prep_min", props, "an empty value clears the field")
        self.assertEqual(len(props["ingredients"]), 7, "the other fields stay")
        body = brain.get_note(self.conn, nid)["body"]
        self.assertIn("Pour 6 portions", body)
        self.assertIn("Mes notes :\nLes enfants ont adoré.", body, "what the user wrote is kept")

    def test_an_agent_defines_its_own_type(self):
        t = types.define_type(self.conn, "Book", "Livre", [
            {"key": "author", "en": "Author", "fr": "Auteur"}, {"key": "year", "fr": "Année", "kind": "number"},
            {"key": "status", "fr": "Statut", "kind": "choice", "choices": ["à lire", "lu"]},
            {"key": "title", "fr": "Titre"}, {"key": "weird", "kind": "spaceship"}], created_by="Bibliothécaire")
        self.assertEqual(t["id"], "book")
        self.assertEqual([f["key"] for f in t["fields"]], ["author", "year", "status", "weird"], "title is the item's own")
        self.assertEqual(t["fields"][3]["kind"], "text", "an unknown kind becomes text")
        n = brain.create_note(self.conn, "Les Belles-sœurs", "")
        types.set_props(self.conn, n["id"], "book", {"author": "Michel Tremblay", "year": "1968", "status": "LU", "x": 1},
                        rewrite_body=True)
        p = types.get_props(self.conn, n["id"])["props"]
        self.assertEqual(p, {"author": "Michel Tremblay", "year": 1968, "status": "lu"})
        self.assertIn("Auteur : Michel Tremblay", brain.get_note(self.conn, n["id"])["body"])
        listed = {x["id"]: x for x in types.list_types(self.conn)}
        self.assertEqual((listed["book"]["count"], listed["recipe"]["builtin"]), (1, True))
        with self.assertRaises(types.TypeError_):
            types.define_type(self.conn, "Recipe", "Recette", [{"key": "x"}], type_id="recipe")
        with self.assertRaises(types.TypeError_):
            types.set_props(self.conn, n["id"], "nope", {})

    def test_the_assistant_reads_scales_and_saves_typed_items(self):
        from engine.assistant import core as assistant
        core.ingest_page(self.conn, None, "https://example.com/recettes/paella", "Paella", PAGE, "")
        acts: list = []
        out = assistant.run_tool(self.conn, "item_fields", {"item": "paella du samedi", "servings": 6}, acts)
        self.assertEqual((out["type"], out["scaled_from"], out["fields"]["servings"]), ("recipe", 4, 6))
        self.assertIn("560 ml riz à paella", out["fields"]["ingredients"][0])
        self.assertEqual(out["fields"]["ingredients"][-1], "Sel et poivre")
        self.assertEqual(out["fields"]["steps"][0], "Dans une grande poêle, dorer l'oignon dans l'huile.")
        out = assistant.run_tool(self.conn, "set_item_fields", {"item": "Paella du samedi", "fields": {"tried": True}}, acts)
        self.assertTrue(out["fields"]["tried"])
        assistant.run_tool(self.conn, "define_item_type", {"name_en": "Book", "name_fr": "Livre",
                                                           "fields": [{"key": "author", "fr": "Auteur"}]}, acts)
        saved = assistant.run_tool(self.conn, "save_typed_item", {"title": "Kamouraska", "type": "book",
                                                                  "fields": {"author": "Anne Hébert"}}, acts)
        self.assertEqual(types.get_props(self.conn, saved["saved"])["props"], {"author": "Anne Hébert"})
        self.assertEqual(acts[-1]["kind"], "create_note")
        listed = assistant.run_tool(self.conn, "list_item_types", {}, acts)
        self.assertEqual({t["id"] for t in listed["types"]}, {"recipe", "book"})

    def test_a_mission_saves_typed_items(self):
        from engine import missions
        m = missions.start(self.conn, "archivist", "Trois recettes")
        missions._save(self.conn, m, status="draft", draft={"title": "Recettes", "summary": "x", "place": "", "items": [
            {"title": "Pâtes au thon", "body": "", "type": "recipe",
             "fields": {"servings": 2, "ingredients": ["250 g de pâtes", "1 boîte de 170 g de thon"], "steps": ["Cuire.", "Mélanger."]}}]})
        done = missions.approve(self.conn, m["id"])
        nid = done["result"]["note_ids"][0]
        p = types.get_props(self.conn, nid)["props"]
        self.assertEqual((p["servings"], p["ingredients"][1]["unit"], p["ingredients"][1]["size"]), (2, "can", {"qty": 170.0, "unit": "g"}))
        self.assertIn("Pour 2 portions", brain.get_note(self.conn, nid)["body"])

    def test_scaling(self):
        ings = [recipe.parse_ingredient(x) for x in ("375 ml (1 ½ tasse) de riz", "1 oignon", "Sel")]
        big = recipe.scale(ings, 1.5)
        self.assertEqual([i["qty"] for i in big], [562.5, 1.5, None])
        self.assertEqual(types.ingredient_line(big[1]), "1 ½ oignon")
        self.assertEqual(types.ingredient_line(recipe.scale([recipe.parse_ingredient("2 c. à soupe (30 ml) d'huile")], 2)[0]),
                         "4 c. à soupe (60 ml) huile")


if __name__ == "__main__":
    unittest.main()
