"""The Responses API translation (for reasoning models with tools) and model fallback, offline."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine import database
from engine.assistant import core, llm
from engine.assistant.llm import FakeChat, LLMError, OpenAIChat
from engine.brain.seed import seed_if_empty


class ResponsesTranslationTests(unittest.TestCase):
    def test_routes_astra_through_responses_only(self):
        self.assertTrue(llm.uses_responses("gpt-6-astra"))
        self.assertFalse(llm.uses_responses("gpt-6-sol"))
        self.assertFalse(llm.uses_responses("gpt-4o"))
        self.assertEqual(llm.MIN_REASONING_EFFORT["gpt-6-astra"], "low")

    def test_messages_to_input_and_back(self):
        out = {"output": [{"type": "reasoning", "id": "rs_1", "encrypted_content": "xyz", "summary": []},
                          {"type": "function_call", "call_id": "call_1", "name": "add_task",
                           "arguments": "{\"title\": \"Facture\"}"}],
               "usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                         "output_tokens_details": {"reasoning_tokens": 3}}}
        msg, usage = llm.from_responses_output(out)
        self.assertIsNone(msg["content"])
        self.assertEqual(msg["tool_calls"][0]["function"]["name"], "add_task")
        self.assertEqual(usage["prompt_tokens"], 10)
        self.assertEqual(usage["reasoning_tokens"], 3)
        history = [{"role": "system", "content": "S"}, {"role": "user", "content": "U"},
                   {"role": "assistant", "content": None, "tool_calls": msg["tool_calls"], "_items": msg["_items"]},
                   {"role": "tool", "tool_call_id": "call_1", "content": "{\"ok\": true}"}]
        items = llm.to_responses_input(history)
        self.assertEqual(items[0], {"role": "system", "content": "S"})
        self.assertEqual(items[2]["type"], "reasoning")  # reasoning goes back verbatim
        self.assertEqual(items[3]["type"], "function_call")
        self.assertEqual(items[4], {"type": "function_call_output", "call_id": "call_1", "output": "{\"ok\": true}"})

    def test_plain_tool_calls_without_items_are_rebuilt(self):
        items = llm.to_responses_input([{"role": "assistant", "content": "Je regarde.", "tool_calls": [
            {"id": "c9", "type": "function", "function": {"name": "get_today", "arguments": "{}"}}]}])
        self.assertEqual([i.get("type", i.get("role")) for i in items], ["assistant", "function_call"])
        self.assertEqual(items[1]["call_id"], "c9")

    def test_final_text_message(self):
        msg, _ = llm.from_responses_output({"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "Bon"}, {"type": "output_text", "text": "jour"}]}]})
        self.assertEqual(msg["content"], "Bonjour")
        self.assertNotIn("tool_calls", msg)

    def test_payloads_sent_to_each_api(self):
        sent = []

        def fake_post(path, key, payload, timeout=60.0):
            sent.append((path, payload))
            if path == "/responses":
                return json.dumps({"output": [{"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
                                   "usage": {}}).encode()
            return json.dumps({"choices": [{"message": {"role": "assistant", "content": "ok"}}], "usage": {}}).encode()

        tools = [{"type": "function", "function": {"name": "get_today", "description": "d",
                                                   "parameters": {"type": "object", "properties": {}}}}]
        with mock.patch.object(llm, "_post", side_effect=fake_post):
            c = OpenAIChat("sk-test")
            c.complete("gpt-6-astra", [{"role": "user", "content": "hi"}], tools=tools, effort="medium")
            c.complete("gpt-6-sol", [{"role": "user", "content": "hi", "_private": 1}], tools=tools)
        path, p = sent[0]
        self.assertEqual(path, "/responses")
        self.assertEqual(p["reasoning"], {"effort": "medium"})
        self.assertFalse(p["store"])
        self.assertEqual(p["tools"][0]["name"], "get_today")
        path, p = sent[1]
        self.assertEqual(path, "/chat/completions")
        self.assertEqual(p["reasoning_effort"], "none")
        self.assertNotIn("_private", p["messages"][0])


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "f.sqlite3"
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_if_empty(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_review_falls_back_when_model_is_missing(self):
        real = FakeChat.complete
        used = []

        def picky(self, model, messages, **kw):
            used.append(model)
            if model == "gpt-6-astra":
                raise LLMError("OpenAI HTTP 404: The model `gpt-6-astra` does not exist or you do not have access to it.")
            return real(self, model, messages, **kw)

        with mock.patch.object(FakeChat, "complete", picky):
            out = core.weekly_review(self.conn, FakeChat())
            core.weekly_review(self.conn, FakeChat())
        self.assertTrue(out["text"])
        self.assertEqual(used[:2], ["gpt-6-astra", "gpt-4o"])
        warnings = self.conn.execute("SELECT COUNT(*) FROM system_events WHERE stage = 'model_fallback'").fetchone()[0]
        self.assertEqual(warnings, 1)  # said once, not at every call

    def test_other_errors_are_not_hidden(self):
        with mock.patch.object(FakeChat, "complete", side_effect=LLMError("OpenAI HTTP 500: boom")):
            with self.assertRaises(LLMError):
                core.weekly_review(self.conn, FakeChat())


if __name__ == "__main__":
    unittest.main()
