"""Loop 7b: live conversation relay, driven by the scripted fake Realtime server (no network, no cost)."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from engine import database
from engine.assistant import core
from engine.assistant.llm import FakeChat
from engine.brain.seed import seed_all
from engine.voice import live

SECOND = b"\x10\x00" * 24000


class Recorder:
    def __init__(self):
        self.msgs = []
        self.audio = 0

    async def json(self, m):
        self.msgs.append(m)

    async def audio_out(self, b):
        self.audio += len(b)

    def types(self):
        return [m["type"] for m in self.msgs]


class SpyUpstream(live.FakeUpstream):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def send(self, ev):
        self.sent.append(ev)
        await super().send(ev)


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "l.sqlite3"
        database.migrate(self.db)
        with database.session(self.db) as conn:
            seed_all(conn)
        self.rec = Recorder()
        self.up = SpyUpstream()
        self.sess = live.LiveSession(self.db, self.up, dict(live.DEFAULTS), "marin", self.rec.json, self.rec.audio_out,
                                     FakeChat())

    def tearDown(self):
        self.tmp.cleanup()

    def run_turns(self, seconds: int, extra=None):
        async def go():
            await self.sess.start()
            pump = asyncio.create_task(self.sess.pump())
            for _ in range(seconds):
                await self.sess.mic(SECOND)
                await asyncio.sleep(0.05)
            if extra:
                await extra()
            await asyncio.sleep(0.2)
            await self.sess.close()
            await asyncio.wait_for(pump, 5)
        asyncio.run(go())

    def test_session_is_configured_with_persona_tools_and_voice(self):
        self.run_turns(0)
        upd = self.up.sent[0]
        self.assertEqual(upd["type"], "session.update")
        s = upd["session"]
        self.assertEqual(s["type"], "realtime")
        self.assertEqual(s["audio"]["output"]["voice"], "marin")
        self.assertEqual(s["audio"]["input"]["format"], {"type": "audio/pcm", "rate": 24000})
        self.assertTrue(s["audio"]["input"]["turn_detection"]["interrupt_response"])
        self.assertIn("CONVERSATION VOCALE", s["instructions"])
        names = {t["name"] for t in s["tools"]}
        self.assertTrue({"search_notes", "ui_open_view", "add_task", "focus_project", "end_conversation"} <= names)
        self.assertTrue(all("function" not in t for t in s["tools"]))  # flat Realtime format

    def test_spoken_request_runs_the_same_tools_and_drives_the_interface(self):
        self.run_turns(1)
        t = self.rec.types()
        self.assertIn("speech_started", t)
        self.assertIn({"type": "user_text", "text": "Montre-moi ma journée."}, self.rec.msgs)
        ui = next(m for m in self.rec.msgs if m["type"] == "ui_actions")
        self.assertEqual(ui["actions"], [{"action": "open_view", "view": "today"}])
        out = next(e for e in self.up.sent if e["type"] == "conversation.item.create")
        self.assertEqual(out["item"]["type"], "function_call_output")
        self.assertTrue(json.loads(out["item"]["output"])["done"])
        self.assertEqual(self.up.sent[-1]["type"], "response.create")
        self.assertIn({"type": "assistant_text", "text": "C'est ouvert, voici ta journée."}, self.rec.msgs)
        self.assertGreater(self.rec.audio, 10000)  # the assistant's voice reached Godot
        self.assertLess(t.index("audio_start"), t.index("audio_done"))
        costs = [m for m in self.rec.msgs if m["type"] == "cost"]
        self.assertGreater(costs[-1]["usd"], 0)  # running total, from OpenAI's usage

    def test_transcripts_join_todays_conversation(self):
        self.run_turns(1)
        with database.session(self.db) as conn:
            h = core.history(conn, core.today_conversation(), 10)
        self.assertEqual([(m["role"], m["content"]) for m in h][-2:],
                         [("user", "Montre-moi ma journée."), ("assistant", "C'est ouvert, voici ta journée.")])
        self.assertTrue(h[-1]["meta"]["live"])

    def test_goodbye_ends_the_conversation(self):
        self.run_turns(3)
        self.assertIn({"type": "ended", "reason": "goodbye"}, self.rec.msgs)
        self.assertEqual(self.sess.ended, "goodbye")

    def test_interrupt_cancels_and_truncates_what_was_not_heard(self):
        async def cut():
            self.sess.audio_item = "msg_9"
            self.sess.responding = True
            await self.sess.interrupt(850)
        self.run_turns(0, cut)
        kinds = [e["type"] for e in self.up.sent]
        self.assertIn("response.cancel", kinds)
        tr = next(e for e in self.up.sent if e["type"] == "conversation.item.truncate")
        self.assertEqual((tr["item_id"], tr["content_index"], tr["audio_end_ms"]), ("msg_9", 0, 850))

    def test_session_cap_ends_politely(self):
        self.sess.s["live_session_cap_usd"] = 0.000001
        self.run_turns(1)
        self.assertIn("ended", self.rec.types())
        self.assertEqual(self.sess.ended, "cap")

    def test_focus_project_loads_its_context(self):
        from engine.brain import structure
        with database.session(self.db) as conn:
            sid = structure.create_project(conn, "Atlas", goal="Lancer la démo client")["id"]
        result, ui = self.sess._run_tool("focus_project", {"space_id": sid})
        self.assertTrue(result["done"])
        self.assertEqual(ui[0]["action"], "open_project")
        self.assertIn(self.sess.focus.strip()[:10], self.sess.instructions())
        bad, _ = self.sess._run_tool("focus_project", {"space_id": "nope"})
        self.assertIn("error", bad)

    def test_cost_math_and_messages(self):
        usage = {"input_token_details": {"text_tokens": 1_000_000, "audio_tokens": 1_000_000,
                                         "cached_tokens_details": {"text_tokens": 0, "audio_tokens": 0}},
                 "output_token_details": {"text_tokens": 0, "audio_tokens": 1_000_000}}
        self.assertAlmostEqual(live.cost_of("gpt-realtime-2.1-mini", usage), 0.60 + 10.00 + 20.00)
        self.assertIsNone(live.cost_of("unknown-model", usage))
        msg = live.friendly_error(RuntimeError("received 3003 invalid_request_error.model_not_found"), "",
                                  "gpt-realtime-2.1-mini")
        self.assertIn("Limits", msg)


if __name__ == "__main__":
    unittest.main()
