"""Real answers, recorded once and replayed (the How-to guides, tools/howto.sh).

SBGD_ASSISTANT_PROVIDER=record  the real model answers (key from the environment, through dotenvx); every answer is
                                appended to SBGD_RECORDING (a JSON file) with the messages the model saw.
SBGD_ASSISTANT_PROVIDER=replay  no network, no key: the recorded answers come back in the same order, so the guide's
                                screenshots show what the real model said, at no cost.

Embeddings stay local in both modes (the showcase's hashed vectors): the demo Brain is seeded with them, and a
query must be compared with vectors of the same kind.

Items get new ids on every run. Replaying, the messages the app sends now are walked side by side with the ones
recorded: where an id differs, the recorded id is mapped to the new one, and the recorded answer (tool calls
included) is rewritten with the new ids.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from engine.assistant.llm import LLMError, OpenAIChat

ID_RE = re.compile(r"^[0-9a-f]{12,32}$")
_LOCK = threading.Lock()
_STATE: dict[str, Any] = {"path": None, "data": None, "next": {}, "ids": {}}


def _path() -> Path:
    p = os.environ.get("SBGD_RECORDING", "")
    if not p:
        raise LLMError("SBGD_RECORDING is not set")
    return Path(p)


def _load() -> dict[str, Any]:
    p = _path()
    if _STATE["path"] != str(p):
        data: dict[str, Any] = {"calls": [], "web": [], "fetch": []}
        if p.exists() and os.environ.get("SBGD_ASSISTANT_PROVIDER") == "replay":
            data = json.loads(p.read_text(encoding="utf-8"))
        _STATE.update(path=str(p), data=data, next={}, ids={})
    return _STATE["data"]


def _save() -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(_STATE["data"], ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def _kind(messages: list[dict[str, Any]], json_mode: bool) -> str:
    """Calls are replayed in order within their kind: the same agent (system prompt) and the same mode."""
    system = str(messages[0].get("content", "")) if messages and messages[0].get("role") == "system" else ""
    return ("json:" if json_mode else "chat:") + re.sub(r"\s+", " ", system[:80])


def _slim(value: Any) -> Any:
    """Pictures sent to the vision model are not needed to replay (only ids are matched): kept as a marker."""
    if isinstance(value, str):
        return "<image>" if value.startswith("data:") or len(value) > 50_000 else value
    if isinstance(value, list):
        return [_slim(v) for v in value]
    if isinstance(value, dict):
        return {k: _slim(v) for k, v in value.items()}
    return value


def _seen(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [_slim(m) for m in messages if m.get("role") != "system"]


def _walk(old: Any, new: Any, ids: dict[str, str]) -> None:
    if isinstance(old, str) and isinstance(new, str):
        if old == new:
            return
        if ID_RE.match(old) and ID_RE.match(new):
            ids.setdefault(old, new)
            return
        try:
            a, b = json.loads(old), json.loads(new)
        except (ValueError, TypeError):
            return
        if isinstance(a, (dict, list)):
            _walk(a, b, ids)
    elif isinstance(old, dict) and isinstance(new, dict):
        for k in old.keys() & new.keys():
            _walk(old[k], new[k], ids)
    elif isinstance(old, list) and isinstance(new, list):
        for a, b in zip(old, new):
            _walk(a, b, ids)


def _remap(value: Any, ids: dict[str, str]) -> Any:
    text = json.dumps(value, ensure_ascii=False)
    for old, new in ids.items():
        text = text.replace(old, new)
    return json.loads(text)


class RecordingChat(OpenAIChat):
    """The real model; every answer is kept for the replay."""

    provider = "record"

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        from engine.brain.showcase import _embed

        return [_embed(t) for t in texts]

    def complete(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                 json_mode: bool = False, temperature: float = 0.4, effort: str | None = None) -> dict[str, Any]:
        res = super().complete(model, messages, tools, json_mode, temperature, effort)
        with _LOCK:
            _load()["calls"].append({"kind": _kind(messages, json_mode), "model": res.get("model", model),
                                     "seen": _seen(messages), "message": res["message"], "usage": res.get("usage", {})})
            _save()
        return res

    def web_search(self, model: str, query: str) -> dict[str, Any]:
        res = super().web_search(model, query)
        with _LOCK:
            _load()["web"].append({"query": query, "result": res})
            _save()
        return res

    def speak(self, text: str, voice: str, instructions: str, model: str = "gpt-4o-mini-tts") -> bytes:
        return b""  # guides are silent


class ReplayChat:
    """The recorded answers, in order, with today's ids."""

    provider = "replay"

    def __init__(self, *_: Any):
        pass

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        from engine.brain.showcase import _embed

        return [_embed(t) for t in texts]

    def complete(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                 json_mode: bool = False, temperature: float = 0.4, effort: str | None = None) -> dict[str, Any]:
        kind = _kind(messages, json_mode)
        with _LOCK:
            data = _load()
            calls = [c for c in data["calls"] if c["kind"] == kind]
            i = _STATE["next"].get(kind, 0)
            if i >= len(calls):
                raise LLMError(f"replay: no recorded answer left for {kind[:40]}… (record this guide again)")
            _STATE["next"][kind] = i + 1
            rec = calls[i]
            _walk(rec["seen"], _seen(messages), _STATE["ids"])
            message = _remap(rec["message"], _STATE["ids"])
        return {"message": message, "usage": rec.get("usage", {}), "model": rec.get("model", model)}

    def web_search(self, model: str, query: str) -> dict[str, Any]:
        with _LOCK:
            data = _load()
            i = _STATE["next"].get("web", 0)
            if i >= len(data["web"]):
                raise LLMError("replay: no recorded web search left")
            _STATE["next"]["web"] = i + 1
            return data["web"][i]["result"]

    def speak(self, text: str, voice: str, instructions: str, model: str = "") -> bytes:
        return b""


def fetch(url: str, download: Any) -> tuple[str, bytes, str]:
    """A web page the guide downloads: kept while recording, served from the recording when replaying (no network)."""
    import base64
    import gzip

    if os.environ.get("SBGD_ASSISTANT_PROVIDER") == "replay":
        with _LOCK:
            data = _load()
            used = _STATE["next"].setdefault("fetch_used", set())
            for i, f in enumerate(data.get("fetch", [])):
                if f["url"] == url and i not in used:
                    used.add(i)
                    if f.get("error"):
                        raise OSError(f["error"])
                    raw = base64.b64decode(f["data"])
                    return f["mime"], (gzip.decompress(raw) if f.get("gzip") else raw), f["charset"]
        raise OSError("replay: this page was not downloaded when the guide was recorded")
    try:
        mime, raw, charset = download()
    except Exception as exc:
        with _LOCK:
            _load().setdefault("fetch", []).append({"url": url, "error": str(exc)})
            _save()
        raise
    with _LOCK:
        _load().setdefault("fetch", []).append({"url": url, "mime": mime, "charset": charset, "gzip": True,
                                                "data": base64.b64encode(gzip.compress(raw)).decode("ascii")})
        _save()
    return mime, raw, charset
