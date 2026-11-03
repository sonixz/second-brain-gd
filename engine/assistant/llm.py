"""Minimal OpenAI clients (stdlib only): chat completions with tools, and speech."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

API = "https://api.openai.com/v1"
# List prices in USD per 1M tokens, used for estimates shown to the user only.
PRICES = {"gpt-4o": (2.50, 10.00), "gpt-4o-mini": (0.15, 0.60)}
TTS_PRICE_PER_1M_CHARS = 15.0  # rough estimate for gpt-4o-mini-tts


class LLMError(RuntimeError):
    pass


def estimate_cost(model: str, usage: dict[str, Any] | None) -> float | None:
    """None when the model's price is unknown (never invent a number)."""
    if not usage:
        return 0.0
    if model not in PRICES:
        return None
    pin, pout = PRICES[model]
    return round((usage.get("prompt_tokens", 0) * pin + usage.get("completion_tokens", 0) * pout) / 1e6, 6)


def _post(path: str, key: str, payload: dict[str, Any], timeout: float = 60.0) -> bytes:
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode("utf-8"), method="POST",
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        try:
            msg = json.loads(exc.read()).get("error", {}).get("message", "")
        except Exception:
            msg = ""
        raise LLMError(f"OpenAI HTTP {exc.code}: {msg or exc.reason}") from exc
    except OSError as exc:
        raise LLMError(f"Cannot reach OpenAI: {exc.__class__.__name__}") from exc


class OpenAIChat:
    provider = "openai"

    def __init__(self, key: str):
        self.key = key

    def complete(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                 json_mode: bool = False, temperature: float = 0.4) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            payload["tools"] = tools
        if model.startswith("gpt-6"):
            # Reasoning models refuse function tools and custom temperatures in Chat Completions
            # unless reasoning is off (measured 2026-11-02).
            payload["reasoning_effort"] = "none"
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = json.loads(_post("/chat/completions", self.key, payload))
        return {"message": data["choices"][0]["message"], "usage": data.get("usage", {}), "model": model}

    def speak(self, text: str, voice: str, instructions: str, model: str = "gpt-4o-mini-tts") -> bytes:
        return _post("/audio/speech", self.key, {"model": model, "voice": voice, "input": text,
                                                  "instructions": instructions, "response_format": "mp3"}, 90.0)


class FakeChat:
    """Deterministic stand-in, enabled only with SBGD_ASSISTANT_PROVIDER=fake (tests)."""

    provider = "fake"

    def __init__(self, *_: Any):
        pass

    def complete(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                 json_mode: bool = False, temperature: float = 0.4) -> dict[str, Any]:
        last = messages[-1]
        usage = {"prompt_tokens": 100, "completion_tokens": 20}
        if json_mode:  # classification: pick the space whose name appears in the note
            ctx = json.loads(last["content"])
            text = (ctx["note"]["title"] + " " + ctx["note"]["body"]).lower()
            if text.startswith(("acheter ", "buy ")) and ctx.get("checklists"):
                out = {"target": "checklist", "checklist_id": ctx["checklists"][0]["id"],
                       "items": [w.strip() for w in text.split(" ", 1)[1].split(",")], "confidence": 0.9,
                       "reason": "fake list item"}
                return {"message": {"role": "assistant", "content": json.dumps(out)}, "usage": usage, "model": model}
            space = next((s for s in ctx["spaces"] if s["name"].lower() in text and s["id"] != "inbox"), None)
            out = {"space_id": space["id"] if space else "inbox", "title": ctx["note"]["title"], "kind": "note",
                   "tags": ["fake"], "link_ids": [c["id"] for c in ctx["candidates"][:1]],
                   "confidence": 0.9 if space else 0.3, "reason": "fake classifier"}
            return {"message": {"role": "assistant", "content": json.dumps(out)}, "usage": usage, "model": model}
        if last["role"] == "tool":
            found = json.loads(last["content"])
            titles = [f"[[{r['title']}]]" for r in found.get("results", [])[:3]]
            return {"message": {"role": "assistant", "content": "J'ai trouvé: " + ", ".join(titles)},
                    "usage": usage, "model": model}
        text = str(last.get("content", ""))
        if text.lower().startswith(("cherche", "search")) and tools:
            q = text.split(" ", 1)[1] if " " in text else text
            call = {"id": "call_fake", "type": "function",
                    "function": {"name": "search_notes", "arguments": json.dumps({"query": q})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if "REVUE HEBDOMADAIRE" in str(messages[0].get("content", "")) and len(messages) <= 2:
            return {"message": {"role": "assistant", "content": "Revue de test: une semaine tranquille."},
                    "usage": usage, "model": model}
        if "briefing" in str(messages[0].get("content", "")).lower() and len(messages) <= 2:
            return {"message": {"role": "assistant", "content": "Bon matin! Ceci est un briefing de test."},
                    "usage": usage, "model": model}
        return {"message": {"role": "assistant", "content": f"(test) Tu as dit: {text}"}, "usage": usage, "model": model}

    def speak(self, text: str, voice: str, instructions: str, model: str = "") -> bytes:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "..", "assets", "audio", "sfx", "confirm.mp3"), "rb") as fh:
            return fh.read()


def make_client(key: str | None) -> OpenAIChat | FakeChat:
    if os.environ.get("SBGD_ASSISTANT_PROVIDER") == "fake":
        return FakeChat()
    if not key:
        raise PermissionError("no OpenAI key configured")
    return OpenAIChat(key)
