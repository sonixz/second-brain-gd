"""Recorded answers replayed for the How-to guides (engine/assistant/recording.py)."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.assistant import recording


class ReplayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "guide.json"
        recording._STATE.update(path=None, data=None, next={}, ids={})

    def _write(self, calls, web=()):
        self.path.write_text(json.dumps({"calls": calls, "web": list(web)}), encoding="utf-8")

    def test_answers_come_back_in_order_with_todays_ids(self):
        old, new = "a1b2c3d4e5f60718", "ffffeeeeddddcccc"
        sys_msg = {"role": "system", "content": "Tu es l'archiviste"}
        seen_then = [{"role": "user", "content": "move the quote"},
                     {"role": "tool", "content": json.dumps({"results": [{"id": old, "title": "Quote"}]})}]
        self._write([
            {"kind": recording._kind([sys_msg], False), "seen": seen_then[:1], "model": "gpt-6-sol",
             "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "find_items", "arguments": "{\"query\": \"quote\"}"}}]}},
            {"kind": recording._kind([sys_msg], False), "seen": seen_then, "model": "gpt-6-sol",
             "message": {"role": "assistant", "content": None, "tool_calls": [{"id": "c2", "type": "function",
                         "function": {"name": "move_items", "arguments": json.dumps({"ids": [old], "place": "Home"})}}]}},
        ])
        with mock.patch.dict(os.environ, {"SBGD_RECORDING": str(self.path), "SBGD_ASSISTANT_PROVIDER": "replay"}):
            chat = recording.ReplayChat()
            first = chat.complete("m", [sys_msg, {"role": "user", "content": "move the quote"}])
            self.assertEqual(first["message"]["tool_calls"][0]["function"]["name"], "find_items")
            now = [sys_msg, {"role": "user", "content": "move the quote"},
                   {"role": "tool", "content": json.dumps({"results": [{"id": new, "title": "Quote"}]})}]
            second = chat.complete("m", now)
            args = json.loads(second["message"]["tool_calls"][0]["function"]["arguments"])
            self.assertEqual(args["ids"], [new])  # the recorded id became today's
            with self.assertRaises(Exception):
                chat.complete("m", now)  # nothing left: the guide must be recorded again

    def test_a_missions_calls_keep_their_own_order(self):
        """A mission runs on its own thread while the agent chats: its calls replay in their own line."""
        persona = {"role": "system", "content": "Tu es l'archiviste"}
        mission = {"role": "system", "content": "Tu es l'archiviste\nTU ES EN MISSION. Objectif: le menu"}
        self.assertTrue(recording._kind([mission], False).startswith("mission:"))
        self.assertNotEqual(recording._kind([persona], False), recording._kind([mission], False))
        say = lambda text: {"role": "assistant", "content": text}
        self._write([{"kind": recording._kind([mission], False), "seen": [], "message": say("plan")},
                     {"kind": recording._kind([persona], False), "seen": [], "message": say("hello")}])
        with mock.patch.dict(os.environ, {"SBGD_RECORDING": str(self.path), "SBGD_ASSISTANT_PROVIDER": "replay"}):
            chat = recording.ReplayChat()
            self.assertEqual(chat.complete("m", [persona])["message"]["content"], "hello")  # chat first, this time
            self.assertEqual(chat.complete("m", [mission])["message"]["content"], "plan")

    def test_web_searches_replay_and_embeddings_stay_local(self):
        self._write([], [{"query": "q", "result": {"text": "answer", "sources": []}}])
        with mock.patch.dict(os.environ, {"SBGD_RECORDING": str(self.path), "SBGD_ASSISTANT_PROVIDER": "replay"}):
            chat = recording.ReplayChat()
            self.assertEqual(chat.web_search("m", "anything")["text"], "answer")
            self.assertEqual(len(chat.embed("m", ["kitchen quote"])[0]), 2048)


if __name__ == "__main__":
    unittest.main()
