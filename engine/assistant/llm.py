"""Minimal OpenAI clients (stdlib only): chat with tools, embeddings and speech.

The assistant speaks one dialect, Chat Completions messages. Models that need
reasoning with tools (gpt-6-astra) go through the Responses API instead; the
translation happens here, so the assistant code does not change.
"""
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


# Per-model behaviour, measured on the owner's project (2026-11-02/03):
# - gpt-6-sol / gpt-6-luna: Chat Completions accepts tools only with reasoning_effort "none".
# - gpt-6-astra: cannot turn reasoning off (lowest "low"), and refuses function tools with
#   reasoning in Chat Completions, so it goes through the Responses API.
MODEL_CAPS: dict[str, dict[str, str]] = {
    "gpt-6-astra": {"api": "responses", "effort": "low"},
}
# Kept for callers and tests that read the minimum effort directly.
MIN_REASONING_EFFORT: dict[str, str] = {m: c["effort"] for m, c in MODEL_CAPS.items() if c.get("effort", "none") != "none"}


def uses_responses(model: str) -> bool:
    return MODEL_CAPS.get(model, {}).get("api") == "responses"


def to_responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chat Completions messages to Responses API input items."""
    items: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "tool":
            items.append({"type": "function_call_output", "call_id": m["tool_call_id"], "output": str(m.get("content") or "")})
        elif role == "assistant" and m.get("_items"):
            items.extend(m["_items"])  # the model's own output, reasoning included, passed back verbatim
        elif role == "assistant" and m.get("tool_calls"):
            if m.get("content"):
                items.append({"role": "assistant", "content": str(m["content"])})
            for c in m["tool_calls"]:
                items.append({"type": "function_call", "call_id": c["id"], "name": c["function"]["name"],
                              "arguments": c["function"].get("arguments") or "{}"})
        else:
            items.append({"role": role, "content": str(m.get("content") or "")})
    return items


def from_responses_output(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Responses API output to one Chat Completions assistant message, plus usage in the same shape."""
    out = data.get("output") or []
    text = "".join(part.get("text", "") for o in out if o.get("type") == "message"
                   for part in (o.get("content") or []) if part.get("type") == "output_text")
    calls = [{"id": o["call_id"], "type": "function", "function": {"name": o["name"], "arguments": o.get("arguments") or "{}"}}
             for o in out if o.get("type") == "function_call"]
    msg: dict[str, Any] = {"role": "assistant", "content": text or None}
    if calls:
        msg["tool_calls"] = calls
        msg["_items"] = out
    u = data.get("usage") or {}
    usage = {"prompt_tokens": u.get("input_tokens", 0), "completion_tokens": u.get("output_tokens", 0),
             "total_tokens": u.get("total_tokens", 0),
             "reasoning_tokens": (u.get("output_tokens_details") or {}).get("reasoning_tokens", 0)}
    return msg, usage


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
                 json_mode: bool = False, temperature: float = 0.4, effort: str | None = None) -> dict[str, Any]:
        if uses_responses(model):
            return self._complete_responses(model, messages, tools, json_mode, effort)
        messages = [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            payload["tools"] = tools
        if model.startswith("gpt-6"):
            # Reasoning models refuse function tools and custom temperatures in Chat Completions
            # unless reasoning is off (measured 2026-11-02). Some (gpt-6-astra) cannot turn
            # reasoning off at all: they get their lowest effort and the default temperature.
            effort = MODEL_CAPS.get(model, {}).get("effort", "none")
            payload["reasoning_effort"] = effort
            if effort != "none":
                payload.pop("temperature", None)
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        data = json.loads(_post("/chat/completions", self.key, payload))
        return {"message": data["choices"][0]["message"], "usage": data.get("usage", {}), "model": model}

    def _complete_responses(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None,
                            json_mode: bool, effort: str | None) -> dict[str, Any]:
        # store=False: nothing kept on OpenAI's side; reasoning travels back encrypted with the items.
        payload: dict[str, Any] = {"model": model, "input": to_responses_input(messages), "store": False,
                                   "reasoning": {"effort": effort or MODEL_CAPS.get(model, {}).get("effort", "low")},
                                   "include": ["reasoning.encrypted_content"]}
        if tools:
            payload["tools"] = [{"type": "function", "name": t["function"]["name"],
                                 "description": t["function"].get("description", ""),
                                 "parameters": t["function"].get("parameters", {"type": "object", "properties": {}})}
                                for t in tools]
        if json_mode:
            payload["text"] = {"format": {"type": "json_object"}}
        data = json.loads(_post("/responses", self.key, payload, timeout=120.0))
        msg, usage = from_responses_output(data)
        return {"message": msg, "usage": usage, "model": model}

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        data = json.loads(_post("/embeddings", self.key, {"model": model, "input": texts}))
        return [d["embedding"] for d in sorted(data["data"], key=lambda d: d["index"])]

    def speak(self, text: str, voice: str, instructions: str, model: str = "gpt-4o-mini-tts") -> bytes:
        return _post("/audio/speech", self.key, {"model": model, "voice": voice, "input": text,
                                                  "instructions": instructions, "response_format": "mp3"}, 90.0)


class FakeChat:
    """Deterministic stand-in, enabled only with SBGD_ASSISTANT_PROVIDER=fake (tests)."""

    provider = "fake"

    def __init__(self, *_: Any):
        pass

    last_messages: list[dict[str, Any]] = []

    def complete(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                 json_mode: bool = False, temperature: float = 0.4, effort: str | None = None) -> dict[str, Any]:
        FakeChat.last_messages = messages
        last = messages[-1]
        usage = {"prompt_tokens": 100, "completion_tokens": 20}
        if json_mode and "fiche de référence" in str(messages[0].get("content", "")):
            src = json.loads(last["content"])
            out = {"title": src.get("title") or "Document", "summary": "Résumé de test.", "key_points": ["Point A"],
                   "tags": ["test-source"]}
            return {"message": {"role": "assistant", "content": json.dumps(out)}, "usage": usage, "model": model}
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
            if "shown_to_user" in found or "undone" in found:
                return {"message": {"role": "assistant", "content": "C'est fait." if found.get("done") or found.get("undone")
                                    else "Rien à annuler."}, "usage": usage, "model": model}
            titles = [f"[[{r['title']}]]" for r in found.get("results", [])[:3]]
            return {"message": {"role": "assistant", "content": "J'ai trouvé: " + ", ".join(titles)},
                    "usage": usage, "model": model}
        text = str(last.get("content", ""))
        low = text.lower()
        views = {"aujourd": "today", "today": "today", "projet": "projects", "agent": "agents", "graph": "graph"}
        if low.startswith(("ouvre", "montre", "open", "show")) and tools:
            view = next((v for k, v in views.items() if k in low), "graph")
            call = {"id": "call_ui", "type": "function",
                    "function": {"name": "ui_open_view", "arguments": json.dumps({"view": view})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("annule", "undo")) and tools:
            call = {"id": "call_undo", "type": "function", "function": {"name": "undo_last_action", "arguments": "{}"}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
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

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        """Deterministic bag-of-words vectors: same words, same direction (tests only)."""
        import hashlib
        out = []
        for t in texts:
            v = [0.0] * 64
            for w in t.lower().split():
                v[int(hashlib.md5(w.strip(".,;:!?").encode()).hexdigest(), 16) % 64] += 1.0
            out.append(v)
        return out

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
