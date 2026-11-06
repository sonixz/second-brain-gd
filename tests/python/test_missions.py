"""Loop 32: missions, driven by a scripted model (no network, no cost)."""
import json
import tempfile
import unittest
from pathlib import Path

from engine import brain, database, missions
from engine.assistant import agents, core
from engine.brain.seed import seed_all


def call(name, **args):
    return {"id": f"c_{name}_{abs(hash(json.dumps(args, sort_keys=True))) % 10**6}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)}}


class Scripted:
    """Plays one tool-call list per model call; records what it was sent. Priced like OpenAI (costs counted)."""
    provider = "openai"

    def __init__(self, turns):
        self.turns = list(turns)
        self.sent = []

    def complete(self, model, messages, tools=None, **_):
        self.sent.append({"model": model, "messages": [dict(m) for m in messages], "tools": [t["function"]["name"] for t in tools or []]})
        calls = self.turns.pop(0) if self.turns else []
        msg = {"role": "assistant", "content": None if calls else "…", "tool_calls": calls} if calls else \
            {"role": "assistant", "content": "Je réfléchis."}
        return {"message": msg, "usage": {"prompt_tokens": 1000, "completion_tokens": 200}, "model": model}

    def web_search(self, model, query):
        return {"text": f"Rabais de la semaine pour {query}", "sources": [{"title": "Circulaire Maxi", "url": "https://example.com/maxi"}],
                "usage": {"prompt_tokens": 50, "completion_tokens": 20}, "model": model}


RECIPE = "Poulet rôti au citron"
TURNS = [
    [call("set_plan", steps=["Lire les rabais", "Demander les préférences", "Chercher des recettes", "Proposer le menu"])],
    [call("web_search", query="Maxi circulaire"),
     call("note_findings", kind="specials", rows=[{"product": "Poulet entier", "store": "Maxi", "price": "2.99/lb",
                                                    "url": "https://example.com/maxi"},
                                                   {"product": "Citrons", "store": "Maxi", "price": "0.50", "url": "https://example.com/maxi"}]),
     call("step_done", step=1, note="2 rabais")],
    [call("ask_user", question="Lesquels te tentent?", choices=["Poulet entier", "Citrons"], multiple=True)],
    [call("step_done", step=2), call("step_done", step=3),
     call("propose_draft", title="Menu de la semaine", summary="Un repas avec le poulet en rabais.", place="Cuisine",
          items=[{"title": RECIPE, "kind": "reference", "body": "Ingrédients: poulet, citron.", "url": "https://example.org/poulet",
                  "themes": ["recette", "poulet"]},
                 {"title": "Menu de la semaine", "kind": "note", "body": f"Lundi: [[{RECIPE}]]", "themes": ["menu"]}])],
]


class MissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "m.sqlite3"
        database.migrate(self.db)
        with database.session(self.db) as conn:
            seed_all(conn)
            agents.update(conn, "archivist", {"capabilities": agents.PRESETS["archivist"] + ["missions"]})

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, **kw):
        with database.session(self.db) as conn:
            return missions.start(conn, "archivist", "Le menu de la semaine avec les rabais", **kw)["id"]

    def get(self, mid):
        with database.session(self.db) as conn:
            return missions.get(conn, mid)

    def run_until_pause(self, client, mid, limit=20):
        for _ in range(limit):
            st = missions.step(self.db, client, mid)
            if st != "running":
                return st
        return "running"

    def test_a_whole_mission_plan_findings_question_draft_approval(self):
        client = Scripted(TURNS)
        mid = self.start()
        self.assertEqual(self.run_until_pause(client, mid), "waiting")
        m = self.get(mid)
        self.assertEqual([s["status"] for s in m["plan"]], ["done", "todo", "todo", "todo"])
        self.assertEqual(len(m["findings"]["specials"]), 2)
        self.assertEqual(m["question"]["choices"], ["Poulet entier", "Citrons"])
        self.assertIn("web_search", client.sent[0]["tools"])  # the archivist has Internet
        self.assertIn("TU ES EN MISSION", client.sent[0]["messages"][0]["content"])
        self.assertGreater(m["cost"], 0)
        with database.session(self.db) as conn:
            missions.answer(conn, mid, ["Poulet entier"])
        self.assertEqual(self.run_until_pause(client, mid), "draft")
        self.assertIn("Poulet entier", json.dumps(client.sent[-1]["messages"], ensure_ascii=False))
        m = self.get(mid)
        self.assertEqual(m["draft"]["place"], "Cuisine")
        self.assertNotIn("messages", m)
        with database.session(self.db) as conn:
            before = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
            missions.approve(conn, mid)
            saved = missions.get(conn, mid)
            self.assertEqual(saved["status"], "saved")
            ids = saved["result"]["note_ids"]
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0], before + 2)
            recipe = brain.get_note(conn, ids[0])
            self.assertIn("Source: https://example.org/poulet", recipe["body"])
            self.assertIn("#recette", recipe["body"])
            plan_note = ids[1]
            link = conn.execute("SELECT 1 FROM links WHERE from_note = ? AND to_note = ?", (plan_note, ids[0])).fetchone()
            self.assertIsNotNone(link)  # the plan links to its recipe
            space = conn.execute("SELECT name FROM spaces WHERE id = ?", (recipe["space_id"],)).fetchone()[0]
            self.assertEqual(space, "Cuisine")
            # one undo removes every item of the mission
            core.undo(conn, saved["result"]["action_id"])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0], before)

    def test_nothing_enters_the_brain_before_approval(self):
        client = Scripted(TURNS)
        mid = self.start()
        with database.session(self.db) as conn:
            before = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        self.run_until_pause(client, mid)
        with database.session(self.db) as conn:
            missions.answer(conn, mid, "Poulet")
        self.run_until_pause(client, mid)
        with database.session(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0], before)

    def test_a_mission_resumes_from_the_database(self):
        mid = self.start()
        missions.step(self.db, Scripted(TURNS[:1]), mid)
        # a new client (engine restarted): the plan written before is still there and the work goes on
        client = Scripted(TURNS[1:])
        self.assertEqual(self.run_until_pause(client, mid), "waiting")
        sent = json.dumps(client.sent[0]["messages"], ensure_ascii=False)
        self.assertIn("set_plan", sent)
        self.assertEqual(len(self.get(mid)["plan"]), 4)

    def test_the_ceiling_stops_cleanly_and_keeps_findings(self):
        mid = self.start(max_cost=0.006)  # two rounds (0.004 each with gpt-6-sol prices)
        client = Scripted(TURNS)
        st = self.run_until_pause(client, mid)
        self.assertEqual(st, "stopped")
        m = self.get(mid)
        self.assertIn("ceiling", m["reason"])
        self.assertTrue(m["plan"])  # what was done is kept

    def test_wrap_up_is_asked_near_the_ceiling(self):
        mid = self.start(max_cost=0.0045)  # one round (0.004) is 89 % of it
        client = Scripted([[call("set_plan", steps=["a", "b"])], []])
        missions.step(self.db, client, mid)
        missions.step(self.db, client, mid)
        self.assertIn(missions.WRAP_UP, json.dumps(client.sent[-1]["messages"], ensure_ascii=False))

    def test_text_without_tools_is_sent_back_to_work(self):
        mid = self.start()
        client = Scripted([[]])
        self.assertEqual(missions.step(self.db, client, mid), "running")
        with database.session(self.db) as conn:
            msgs = missions._row(conn, mid)["messages"]
        self.assertIn("Continue la mission", msgs[-1]["content"])

    def test_stop_and_give_up(self):
        mid = self.start()
        with database.session(self.db) as conn:
            missions.stop(conn, mid)
        self.assertEqual(missions.step(self.db, Scripted(TURNS), mid), "stopped")
        mid2 = self.start()
        self.assertEqual(missions.step(self.db, Scripted([[call("give_up", reason="aucune circulaire lisible")]]), mid2), "failed")
        self.assertEqual(self.get(mid2)["reason"], "aucune circulaire lisible")

    def test_old_tool_results_are_shortened(self):
        msgs = []
        for i in range(4):
            msgs.append({"role": "assistant", "content": None, "tool_calls": [call("read_page", url=f"u{i}")]})
            msgs.append({"role": "tool", "tool_call_id": "x", "content": "x" * 5000})
        missions._shorten_old(msgs)
        self.assertLess(len(msgs[1]["content"]), 2000)
        self.assertEqual(len(msgs[-1]["content"]), 5000)

    def test_tools_follow_the_agents_capabilities(self):
        with database.session(self.db) as conn:
            names = [t["function"]["name"] for t in missions.tools_for(conn, "builder")]
        self.assertIn("propose_draft", names)
        self.assertNotIn("web_search", names)  # the Agent Builder has no Internet by default

    def test_chat_tools_start_answer_and_approval_needs_a_yes(self):
        with database.session(self.db) as conn:
            core._CONTEXT["agent"] = "archivist"
            core._CONTEXT["user_text"] = "fais-moi le menu"
            out = core.run_tool(conn, "start_mission", {"goal": "Le menu de la semaine"}, [])
            self.assertTrue(out["started"])
            self.assertIn({"action": "mission", "id": out["mission_id"]}, core._UI["actions"])
            mid = out["mission_id"]
        client = Scripted(TURNS)
        self.run_until_pause(client, mid)
        with database.session(self.db) as conn:
            st = core.run_tool(conn, "mission_status", {}, [])
            self.assertEqual(st["missions"][0]["status"], "waiting")
            core.run_tool(conn, "answer_mission", {"answer": "le poulet"}, [])
        self.run_until_pause(client, mid)
        with database.session(self.db) as conn:
            core._CONTEXT["user_text"] = "attends, pas encore"
            self.assertIn("refused", core.run_tool(conn, "approve_mission", {}, []))
            core._CONTEXT["user_text"] = "oui, enregistre-le"
            self.assertEqual(core.run_tool(conn, "approve_mission", {}, [])["changed"], 2)

    def test_missions_capability_gives_the_chat_tools(self):
        with database.session(self.db) as conn:
            names = [t["function"]["name"] for t in agents.tools(conn, "archivist", agents.all_tools(core.TOOLS))]
            self.assertIn("start_mission", names)
            names = [t["function"]["name"] for t in agents.tools(conn, "sparring", agents.all_tools(core.TOOLS))]
            self.assertNotIn("start_mission", names)

    def test_the_worker_runs_missions_in_the_background(self):
        import time
        from types import SimpleNamespace

        client = Scripted(TURNS)
        w = missions.Worker(SimpleNamespace(database=self.db), lambda: client, idle_s=0.1)
        w.start()
        try:
            mid = self.start()
            end = time.time() + 10
            while self.get(mid)["status"] == "running" and time.time() < end:
                time.sleep(0.05)
            self.assertEqual(self.get(mid)["status"], "waiting")
        finally:
            w.stop()
            w.join(5)


if __name__ == "__main__":
    unittest.main()
