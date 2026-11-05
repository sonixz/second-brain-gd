"""Minimal OpenAI clients (stdlib only): chat with tools, embeddings and speech.

The assistant speaks one dialect, Chat Completions messages. Models that need
reasoning with tools (gpt-6-astra) go through the Responses API instead; the
translation happens here, so the assistant code does not change.
"""
from __future__ import annotations

import json
import re
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

    def web_search(self, model: str, query: str) -> dict[str, Any]:
        """OpenAI's hosted web search (Responses API): a short answer and the pages it cites."""
        data = json.loads(_post("/responses", self.key, {"model": model, "tools": [{"type": "web_search"}], "store": False,
                                                         "input": query}, timeout=120.0))
        return parse_web_search(data, model)


def clean_url(url: str) -> str:
    return re.sub(r"[?&]utm_source=openai$", "", re.sub(r"utm_source=openai&", "", url or ""))


def parse_web_search(data: dict[str, Any], model: str) -> dict[str, Any]:
    texts: list[str] = []
    sources: list[dict[str, str]] = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            texts.append(c.get("text", ""))
            for a in c.get("annotations", []):
                if a.get("type") == "url_citation" and a.get("url"):
                    url = clean_url(a["url"])
                    if url not in [s["url"] for s in sources]:
                        sources.append({"title": str(a.get("title") or url)[:200], "url": url})
    u = data.get("usage") or {}
    usage = {"prompt_tokens": u.get("input_tokens", 0), "completion_tokens": u.get("output_tokens", 0)}
    text = re.sub(r"\s*\(\[[^\]]*\]\([^)]*\)\)", "", " ".join(texts)).strip()  # citations go to sources, not the text
    return {"text": text, "sources": sources, "usage": usage, "model": data.get("model", model)}


class FakeChat:
    """Deterministic stand-in, enabled only with SBGD_ASSISTANT_PROVIDER=fake (tests)."""

    provider = "fake"

    def __init__(self, *_: Any):
        pass

    last_messages: list[dict[str, Any]] = []

    def web_search(self, model: str, query: str) -> dict[str, Any]:
        return {"text": f"Deux résultats pour « {query} » : une offre chez Exemple Inc. et un article de fond.",
                "sources": [{"title": "Offre DevSecOps — Exemple Inc.", "url": "https://example.com/emplois/devsecops"},
                            {"title": "Guide DevSecOps", "url": "https://example.org/guide"}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 30}, "model": model}

    def complete(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                 json_mode: bool = False, temperature: float = 0.4, effort: str | None = None) -> dict[str, Any]:
        FakeChat.last_messages = messages
        last = messages[-1]
        usage = {"prompt_tokens": 100, "completion_tokens": 20}
        if isinstance(last.get("content"), list):  # an image to describe (vision)
            return {"message": {"role": "assistant", "content": "Image de test: un schéma avec trois boîtes reliées."},
                    "usage": usage, "model": model}
        if json_mode and "fiche de référence" in str(messages[0].get("content", "")):
            src = json.loads(last["content"])
            out = {"title": src.get("title") or "Document", "summary": "Résumé de test.", "key_points": ["Point A"],
                   "tags": ["test-source"]}
            return {"message": {"role": "assistant", "content": json.dumps(out)}, "usage": usage, "model": model}
        if json_mode and "ARCHIVISTE" in str(messages[0].get("content", "")):
            ctx = json.loads(last["content"])
            it = ctx["item"]
            text = (it["title"] + " " + it.get("content", "")).lower()
            words = [w.strip(".,;:!?()«»\"'") for w in it["title"].split()]
            long_words = [w for w in words if len(w) >= 5] or [w for w in words if w] or ["Divers"]
            place = next((p for p in ctx["places"] if p["kind"] != "inbox" and p["name"].lower() in text), None)
            if "???" in text:
                out = {"title": it["title"], "item_type": "note", "confidence": 0.2,
                       "question": "C'est pour quel projet?", "place": {}, "themes": [], "receipt": ""}
            else:
                if place:
                    target = {"space_id": place["id"]}
                elif ctx.get("working_context"):
                    target = {"space_id": ctx["working_context"]["id"]}
                else:
                    name = "Articles" if it.get("origin") in ("url", "file") else long_words[0].capitalize()
                    target = {"new_space": {"name": name, "kind": "resource"}}
                out = {"title": it["title"], "item_type": "article" if it.get("origin") == "url" else "note",
                       "language": "fr", "summary": "Résumé de test." if len(it.get("content", "")) > 400 else None,
                       "key_points": [], "entities": {"concepts": [long_words[0].lower()]},
                       "place": target, "themes": [long_words[0].lower()],
                       "link_ids": [c["id"] for c in ctx["candidates"][:1]], "confidence": 0.9, "question": None,
                       "receipt": ""}
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
        if last["role"] == "tool" and "answer_from_the_web" in str(last.get("content", "")):
            found = json.loads(last["content"])
            return {"message": {"role": "assistant", "content": "Sur le web: " + found["answer_from_the_web"]},
                    "usage": usage, "model": model}
        if last["role"] == "tool":
            found = json.loads(last["content"])
            if "context" in found and found.get("done"):
                ctx = found.get("context") or {}
                return {"message": {"role": "assistant", "content": f"Contexte: {ctx.get('name', 'aucun')}."},
                        "usage": usage, "model": model}
            if "explanation" in found:
                return {"message": {"role": "assistant", "content": found["explanation"]}, "usage": usage, "model": model}
            if found.get("mode") and found.get("agent"):
                return {"message": {"role": "assistant", "content": f"C'est fait: {found['name']} est prêt."}, "usage": usage, "model": model}
            if found.get("draft_ready") and found.get("mode"):
                return {"message": {"role": "assistant", "content": "Voici le brouillon de l'agent. Je le crée?"}, "usage": usage, "model": model}
            if found.get("draft_ready"):
                return {"message": {"role": "assistant", "content": "Voici la synthèse. Je l'enregistre dans le Brain?"}, "usage": usage, "model": model}
            if "saved" in found:
                return {"message": {"role": "assistant", "content": f"C'est dans ton Brain: [[{found['saved']}]]."}, "usage": usage, "model": model}
            if "opened" in found or "closed" in found or "added" in found or ("error" in found and "browser" in str(found["error"])):
                said = ("Ouvert." if "opened" in found else "Fermé." if "closed" in found
                        else f"Ajouté: [[{found['added']}]]." if "added" in found else "L'extension n'est pas connectée.")
                return {"message": {"role": "assistant", "content": said}, "usage": usage, "model": model}
            if found.get("file"):
                return {"message": {"role": "assistant", "content": f"Exporté: {found['file']} ({found['items']} éléments)."},
                        "usage": usage, "model": model}
            if "shown_to_user" in found or "undone" in found:
                return {"message": {"role": "assistant", "content": "C'est fait." if found.get("done") or found.get("undone")
                                    else "Rien à annuler."}, "usage": usage, "model": model}
            titles = [f"[[{r['title']}]]" for r in found.get("results", [])[:3]]
            return {"message": {"role": "assistant", "content": "J'ai trouvé: " + ", ".join(titles)},
                    "usage": usage, "model": model}
        text = str(last.get("content", ""))
        low = text.lower()
        views = {"projet": "projects", "capture": "captures", "graph": "graph"}
        if low.startswith("comment ") and " relié à " in low and tools:
            a, b = text[len("comment "):].split(" est relié à " if " est relié à " in text else " relié à ", 1)
            call = {"id": "call_path", "type": "function", "function": {"name": "find_path", "arguments": json.dumps(
                {"from": a.strip(" ?.!"), "to": b.strip(" ?.!")})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("garde le lien avec", "enlève l'idée liée")) and tools:
            other = text.split(" avec ", 1)[1].strip(" .!") if " avec " in text else ""
            call = {"id": "call_rel", "type": "function", "function": {"name": "related_idea", "arguments": json.dumps(
                {"action": "keep" if low.startswith("garde") else "dismiss", "other": other})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        names = [t["function"]["name"] for t in tools or []]
        if "draft_synthesis" in names and ("résume" in low or "synthétise" in low):
            call = {"id": "call_draft", "type": "function", "function": {"name": "draft_synthesis", "arguments": json.dumps(
                {"title": "Synthèse de test", "body": "## L'idée\nUne idée de test.\n## Décidé\nOn garde l'essentiel."})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if "draft_agent" in names and "entrevue" in low:
            ins = ("Tu es Coach entrevue. Rôle: préparer l'utilisateur à ses entrevues d'embauche. " * 3
                   + "Ton et format: direct, bienveillant, phrases courtes à l'oral. Comment tu travailles: une question à la fois. " * 2)
            call = {"id": "call_dagent", "type": "function", "function": {"name": "draft_agent", "arguments": json.dumps(
                {"name": "Coach entrevue", "instructions": ins, "capabilities": ["read_brain", "internet"],
                 "intro": "Prêt pour ta prochaine entrevue?"})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if "save_agent" in names and low.startswith("oui"):
            call = {"id": "call_sagent", "type": "function", "function": {"name": "save_agent", "arguments": "{}"}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if "draft_agent" in names and ("nouvel agent" in low or "crée-moi un agent" in low):
            return {"message": {"role": "assistant", "content": "Avec plaisir. À quoi doit-il servir, par exemple préparer tes entrevues?"},
                    "usage": usage, "model": model}
        if "ui_open_agent" in names and "draft_agent" not in names and ("crée-moi un agent" in low or "nouvel agent" in low):
            call = {"id": "call_oagent", "type": "function", "function": {"name": "ui_open_agent", "arguments": json.dumps({"agent": "builder"})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if "save_synthesis" in names and low.startswith("oui"):
            call = {"id": "call_save", "type": "function", "function": {"name": "save_synthesis", "arguments": "{}"}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith("ouvre la page http") and tools:
            call = {"id": "call_open", "type": "function", "function": {"name": "open_web_page",
                                                                         "arguments": json.dumps({"url": text.split()[3].strip(" .")})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("injecte-la", "ajoute cette page")) and tools:
            call = {"id": "call_cap", "type": "function", "function": {"name": "capture_browser_tab", "arguments": json.dumps(
                {"tab": "active" if "cette page" in low else "last_opened"})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("ferme-la", "ferme les onglets")) and tools:
            call = {"id": "call_close", "type": "function", "function": {"name": "close_browser_tabs", "arguments": json.dumps(
                {"which": "all" if "onglets" in low else "last"})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("cherche sur le web", "cherche sur internet")) and tools:
            q = text.split(" ", 4)[-1].strip(" .!?") if len(text.split()) > 4 else text
            call = {"id": "call_web", "type": "function", "function": {"name": "web_search", "arguments": json.dumps({"query": q})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith("cherche à l'écran") and tools:
            call = {"id": "call_srch", "type": "function", "function": {"name": "ui_search", "arguments": json.dumps(
                {"query": text.split("écran", 1)[1].strip(" .!")})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if ("chronologi" in low or "retour aux zones" in low) and tools:
            call = {"id": "call_layout", "type": "function", "function": {"name": "ui_layout", "arguments": json.dumps(
                {"mode": "zones" if "retour aux zones" in low else "timeline"})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith("montre seulement") and tools:
            args = {"types": ["article"] if "article" in low else [], "text": low.split(" sur ", 1)[1].strip(" .!") if " sur " in low else ""}
            call = {"id": "call_filter", "type": "function", "function": {"name": "ui_filter", "arguments": json.dumps(args)}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith("enlève les filtres") and tools:
            call = {"id": "call_clear", "type": "function", "function": {"name": "ui_filter", "arguments": json.dumps({"clear": True})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("replie ", "déplie ")) and tools:
            call = {"id": "call_fold", "type": "function", "function": {"name": "ui_fold", "arguments": json.dumps(
                {"place": text.split(" ", 1)[1].strip(" .!"), "fold": low.startswith("replie")})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("ouvre le document", "ouvre le pdf")) and tools:
            target = text.split(" ", 3)[3].strip(" .!") if len(text.split(" ", 3)) > 3 else ""
            call = {"id": "call_doc", "type": "function", "function": {"name": "ui_open_document", "arguments": json.dumps({"target": target})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith("page suivante") and tools:
            call = {"id": "call_page", "type": "function", "function": {"name": "ui_page", "arguments": json.dumps({"change": "next"})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith("ouvre l'original") and tools:
            call = {"id": "call_orig", "type": "function", "function": {"name": "ui_open_original", "arguments": "{}"}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("ouvre", "montre", "open", "show")) and tools:
            view = next((v for k, v in views.items() if k in low), "graph")
            call = {"id": "call_ui", "type": "function",
                    "function": {"name": "ui_open_view", "arguments": json.dumps({"view": view})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if "ajoute ça au brain" in low and tools:
            call = {"id": "call_clip", "type": "function", "function": {"name": "ui_capture_clipboard", "arguments": "{}"}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith("je veux structurer") and tools:
            name = text.split("structurer", 1)[1].replace("le projet", "").strip(" .!") or None
            call = {"id": "call_ctx", "type": "function",
                    "function": {"name": "set_working_context", "arguments": json.dumps({"name": name})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("relis", "répète", "repete")) and tools:
            call = {"id": "call_replay", "type": "function", "function": {"name": "ui_replay", "arguments": "{}"}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("zoome", "zoom")) and tools:
            target = text.split(" sur ", 1)[1].strip(" .!") if " sur " in text else ""
            call = {"id": "call_zoom", "type": "function",
                    "function": {"name": "ui_zoom", "arguments": json.dumps({"level": "read" if target else "closer", "target": target})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith("exporte") and tools:
            value = text.split(" ", 1)[1].replace("le projet", "").replace("la place", "").strip(" .!") if " " in text else ""
            args = {"scope": "all"} if value in ("", "tout") else {"scope": "place", "value": value}
            call = {"id": "call_export", "type": "function", "function": {"name": "export_pack", "arguments": json.dumps(args)}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("désactive le pack", "réactive le pack", "fusionne le pack", "retire le pack")) and tools:
            verb, title = low.split(" le pack ", 1)
            act = {"désactive": "off", "réactive": "on", "fusionne": "merge", "retire": "remove"}[verb.strip()]
            call = {"id": "call_pack", "type": "function",
                    "function": {"name": "manage_pack", "arguments": json.dumps({"action": act, "title": title.strip(" .!")})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if low.startswith(("vue d'ensemble", "recule")) and tools:
            call = {"id": "call_over", "type": "function",
                    "function": {"name": "ui_zoom", "arguments": json.dumps({"level": "overview"})}}
            return {"message": {"role": "assistant", "content": None, "tool_calls": [call]}, "usage": usage, "model": model}
        if "plus vite" in low and tools:
            call = {"id": "call_speed", "type": "function",
                    "function": {"name": "ui_set_voice_speed", "arguments": json.dumps({"change": "faster"})}}
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


def is_fake() -> bool:
    """A scripted provider, no network: "fake" (tests) or "showcase" (website screenshots)."""
    return os.environ.get("SBGD_ASSISTANT_PROVIDER") in ("fake", "showcase")


def make_client(key: str | None) -> OpenAIChat | FakeChat:
    if os.environ.get("SBGD_ASSISTANT_PROVIDER") == "showcase":
        from engine.brain.showcase import ShowcaseChat

        return ShowcaseChat()
    if os.environ.get("SBGD_ASSISTANT_PROVIDER") == "fake":
        return FakeChat()
    if not key:
        raise PermissionError("no OpenAI key configured")
    return OpenAIChat(key)
