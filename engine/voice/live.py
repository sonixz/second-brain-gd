"""Live conversation (Loop 7b): speech to speech with OpenAI Realtime, relayed by the engine.

Godot never sees the API key. It opens ws://127.0.0.1/voice/live and exchanges:

Godot -> engine:  binary frames = microphone PCM16 LE mono 24 kHz
                  {"type": "interrupt", "audio_end_ms": N}  the user cut the assistant off
                  {"type": "stop"}                           end the conversation
engine -> Godot:  binary frames = the assistant's voice, PCM16 LE mono 24 kHz
                  {"type": "ready", "model", "voice"}
                  {"type": "speech_started"}                 the user started talking: stop playback
                  {"type": "user_text", "text"}               what the user said (transcribed)
                  {"type": "assistant_delta", "text"} / {"type": "assistant_text", "text"}
                  {"type": "audio_start", "item_id"} / {"type": "audio_done"}
                  {"type": "tool", "name"}                    the assistant is using a tool
                  {"type": "ui_actions", "actions"}           same interface actions as the text chat
                  {"type": "cost", "usd", "minutes"}          this conversation so far (shown, not stored)
                  {"type": "ended", "reason"} / {"type": "error", "message"}

The assistant uses the text assistant's persona and tools (notes, tasks, interface), so
everything it does is the same, visible and undoable. Transcripts are saved in today's
conversation, like typed messages. Costs come back from OpenAI in every `response.done`;
the engine shows the running total of this conversation and keeps nothing else.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import os
import sqlite3
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable

from engine import database

REALTIME_WS = "wss://api.openai.com/v1/realtime?model="
SAMPLE_RATE = 24000
DEFAULTS = {"live_model": "gpt-realtime-2.1-mini", "live_transcribe_model": "gpt-realtime-whisper",
            "live_max_minutes": 20, "live_session_cap_usd": 1.0, "live_idle_minutes": 3}
LIVE_MODELS = ["gpt-realtime-2.1-mini", "gpt-realtime-2.1"]
# USD per 1M tokens (text in, text cached, text out, audio in, audio cached, audio out), OpenAI list prices
# 2026-11-03. Only used for the running total shown during a conversation; OpenAI's bill is the reference.
PRICES = {
    "gpt-realtime-2.1-mini": (0.60, 0.06, 2.40, 10.00, 0.30, 20.00),
    "gpt-realtime-2.1": (4.00, 0.40, 24.00, 32.00, 0.40, 64.00),
}
LIVE_RULES = """
Tu es maintenant en CONVERSATION VOCALE en temps réel. Parle naturellement, comme au téléphone: phrases courtes,
une idée à la fois, pas de listes ni de crochets lus à voix haute (dis simplement le titre de la note).
Si l'utilisateur t'interrompt, arrête-toi et écoute. Si tu n'es pas sûre d'avoir compris, demande.
« On travaille sur <projet> » = focus_project (id via get_structure), puis parle de ce projet.
« Merci, c'est tout », « bye », « on arrête » = end_conversation après une courte salutation."""
LIVE_TOOLS = [
    {"type": "function", "name": "focus_project",
     "description": "Work on one project for the rest of the conversation: loads its context and opens its card.",
     "parameters": {"type": "object", "properties": {"space_id": {"type": "string"}}, "required": ["space_id"]}},
    {"type": "function", "name": "end_conversation", "description": "End the live conversation (the user said goodbye).",
     "parameters": {"type": "object", "properties": {}}},
]

SendJson = Callable[[dict[str, Any]], Awaitable[None]]
SendAudio = Callable[[bytes], Awaitable[None]]


def realtime_tools(chat_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Chat Completions tool definitions to Realtime ones (flat), plus the live-only tools."""
    out = [{"type": "function", "name": t["function"]["name"], "description": t["function"].get("description", ""),
            "parameters": t["function"].get("parameters") or {"type": "object", "properties": {}}} for t in chat_tools]
    return out + LIVE_TOOLS


def cost_of(model: str, usage: dict[str, Any] | None) -> float | None:
    p = PRICES.get(model)
    if p is None or not usage:
        return None if p is None else 0.0
    i = usage.get("input_token_details") or {}
    o = usage.get("output_token_details") or {}
    cached = i.get("cached_tokens_details") or {}
    t_in, a_in = int(i.get("text_tokens", 0)), int(i.get("audio_tokens", 0))
    t_c, a_c = int(cached.get("text_tokens", 0)), int(cached.get("audio_tokens", 0))
    return ((t_in - t_c) * p[0] + t_c * p[1] + int(o.get("text_tokens", 0)) * p[2]
            + (a_in - a_c) * p[3] + a_c * p[4] + int(o.get("audio_tokens", 0)) * p[5]) / 1e6


def session_update(instructions: str, voice: str, transcribe_model: str, tools: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "session.update", "session": {
        "type": "realtime", "output_modalities": ["audio"], "instructions": instructions,
        "audio": {
            "input": {"format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
                      "transcription": {"model": transcribe_model, "language": "fr"},
                      "noise_reduction": {"type": "near_field"},
                      "turn_detection": {"type": "semantic_vad", "eagerness": "auto", "create_response": True,
                                         "interrupt_response": True}},
            "output": {"format": {"type": "audio/pcm", "rate": SAMPLE_RATE}, "voice": voice}},
        "tools": tools, "tool_choice": "auto"}}


# ---------------------------------------------------------------- upstreams
class OpenAIUpstream:
    provider = "openai"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model
        self._ws: Any = None

    async def connect(self) -> None:
        import websockets

        self._ws = await websockets.connect(REALTIME_WS + self.model,
                                            additional_headers={"Authorization": f"Bearer {self.api_key}"},
                                            open_timeout=15, ping_interval=20, max_size=2**23)

    async def send(self, event: dict[str, Any]) -> None:
        await self._ws.send(json.dumps(event))

    async def events(self):
        async for raw in self._ws:
            yield json.loads(raw)

    def close_reason(self) -> str:
        try:
            return str(self._ws.close_reason or "")
        except Exception:
            return ""

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()


def _tone(seconds: float, freq: float = 440.0) -> bytes:
    n = int(SAMPLE_RATE * seconds)
    return b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))) for i in range(n))


class FakeUpstream:
    """A scripted Realtime server (SBGD_VOICE_PROVIDER=fake): same events, no network, no cost.

    After each second of microphone audio it behaves like one user turn: « montre-moi ma journée »
    -> a ui_open_view(today) call -> after the tool result, a short spoken answer. A turn whose
    transcript would be the 3rd says goodbye and calls end_conversation.
    """

    provider = "fake"

    def __init__(self, model: str = "gpt-realtime-2.1-mini", *_: Any):
        self.model = model  # priced like the real model, so the running total is exercised
        self._q: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._audio = 0
        self._turns = 0
        self._n = 0
        self._speaking = False

    def _id(self, p: str) -> str:
        self._n += 1
        return f"{p}_{self._n}"

    async def connect(self) -> None:
        pass

    async def _usage(self, audio_out: int) -> dict[str, Any]:
        return {"total_tokens": 300, "input_tokens": 250, "output_tokens": 50 + audio_out,
                "input_token_details": {"text_tokens": 200, "audio_tokens": 50,
                                        "cached_tokens_details": {"text_tokens": 100, "audio_tokens": 0}},
                "output_token_details": {"text_tokens": 20, "audio_tokens": audio_out}}

    async def send(self, ev: dict[str, Any]) -> None:
        t = ev.get("type")
        if t == "session.update":
            await self._q.put({"type": "session.updated", "session": ev["session"]})
        elif t == "input_audio_buffer.append":
            self._audio += len(base64.b64decode(ev.get("audio", "")))
            if self._audio >= SAMPLE_RATE * 2:  # one second of speech = one turn
                self._audio = 0
                self._turns += 1
                await self._user_turn()
        elif t == "conversation.item.create" and (ev.get("item") or {}).get("type") == "function_call_output":
            self._pending_output = True
        elif t == "response.create":
            await self._answer("C'est ouvert, voici ta journée.")
        elif t == "response.cancel":
            await self._q.put({"type": "response.done", "response": {"status": "cancelled", "output": [],
                                                                     "usage": await self._usage(0)}})

    async def _user_turn(self) -> None:
        item = self._id("item")
        await self._q.put({"type": "input_audio_buffer.speech_started", "item_id": item})
        await self._q.put({"type": "input_audio_buffer.speech_stopped", "item_id": item})
        await self._q.put({"type": "input_audio_buffer.committed", "item_id": item})
        bye = self._turns >= 3
        text = "Merci, c'est tout." if bye else "Montre-moi ma journée."
        await self._q.put({"type": "conversation.item.input_audio_transcription.completed", "item_id": item,
                           "transcript": text})
        if bye:
            call = {"type": "function_call", "name": "end_conversation", "call_id": self._id("call"), "arguments": "{}"}
            await self._answer("Bonne journée!", extra=[call])
            return
        call = {"type": "function_call", "name": "ui_open_view", "call_id": self._id("call"),
                "arguments": json.dumps({"view": "today"})}
        await self._q.put({"type": "response.function_call_arguments.done", "name": call["name"],
                           "call_id": call["call_id"], "arguments": call["arguments"]})
        await self._q.put({"type": "response.done", "response": {"status": "completed", "output": [call],
                                                                 "usage": await self._usage(0)}})

    async def _answer(self, text: str, extra: list[dict[str, Any]] | None = None) -> None:
        item = self._id("msg")
        pcm = _tone(0.4)
        await self._q.put({"type": "response.output_item.added", "item": {"id": item, "type": "message"}})
        for w in text.split(" "):
            await self._q.put({"type": "response.output_audio_transcript.delta", "item_id": item, "delta": w + " "})
        for i in range(0, len(pcm), 9600):
            await self._q.put({"type": "response.output_audio.delta", "item_id": item,
                               "delta": base64.b64encode(pcm[i:i + 9600]).decode()})
        await self._q.put({"type": "response.output_audio.done", "item_id": item})
        await self._q.put({"type": "response.output_audio_transcript.done", "item_id": item, "transcript": text})
        out = [{"type": "message", "id": item}] + (extra or [])
        await self._q.put({"type": "response.done", "response": {"status": "completed", "output": out,
                                                                 "usage": await self._usage(len(pcm) // 40)}})

    async def events(self):
        while True:
            ev = await self._q.get()
            if ev is None:
                return
            yield ev

    def close_reason(self) -> str:
        return ""

    async def close(self) -> None:
        await self._q.put(None)


def make_upstream(api_key: str | None, model: str) -> OpenAIUpstream | FakeUpstream:
    if os.environ.get("SBGD_VOICE_PROVIDER") == "fake":
        return FakeUpstream(model)
    if not api_key:
        raise PermissionError("no OpenAI key configured")
    return OpenAIUpstream(api_key, model)


# ---------------------------------------------------------------- the conversation
class LiveSession:
    def __init__(self, db_path: Path, upstream: Any, settings: dict[str, Any], voice: str,
                 send_json: SendJson, send_audio: SendAudio, text_client: Any = None):
        self.db_path = db_path
        self.up = upstream
        self.s = settings
        self.voice = voice
        self.send_json = send_json
        self.send_audio = send_audio
        self.text_client = text_client
        self.started = time.monotonic()
        self.last_speech = time.monotonic()
        self.cost = 0.0
        self.cost_known = True
        self.focus = ""
        self.audio_item: str | None = None
        self.responding = False
        self.ended: str | None = None
        self.mic_bytes = 0

    # -- helpers
    def _db(self) -> sqlite3.Connection:
        return database.connect(self.db_path)

    def instructions(self) -> str:
        from engine.assistant import core

        now = datetime.now().strftime("%A %Y-%m-%d %H:%M")
        return core.PERSONA + LIVE_RULES + f"\nNous sommes le {now}." + self.focus

    def tools(self) -> list[dict[str, Any]]:
        from engine.assistant import core

        return realtime_tools(core.TOOLS)

    async def start(self) -> None:
        await self.up.connect()
        await self.up.send(session_update(self.instructions(), self.voice, self.s["live_transcribe_model"], self.tools()))

    async def mic(self, pcm: bytes) -> None:
        self.mic_bytes += len(pcm)
        await self.up.send({"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm).decode("ascii")})

    async def interrupt(self, audio_end_ms: int) -> None:
        if self.responding:
            await self.up.send({"type": "response.cancel"})
        if self.audio_item:
            await self.up.send({"type": "conversation.item.truncate", "item_id": self.audio_item, "content_index": 0,
                                "audio_end_ms": max(0, int(audio_end_ms))})
            self.audio_item = None

    def _save(self, role: str, text: str, meta: dict[str, Any] | None = None) -> None:
        from engine.assistant import core

        conn = self._db()
        try:
            core._save(conn, core.today_conversation(), role, text, {"live": True, **(meta or {})})
            conn.commit()
        finally:
            conn.close()

    def _run_tool(self, name: str, args: dict[str, Any]) -> tuple[Any, list[dict[str, Any]]]:
        from engine.assistant import core

        conn = self._db()
        try:
            core._CLIENT["c"] = self.text_client
            core._UI["actions"] = []
            if name == "focus_project":
                sid = str(args.get("space_id", ""))
                try:
                    self.focus = core.project_context(conn, sid)
                except Exception:
                    return {"error": "unknown space_id: call get_structure first"}, []
                result = core._ui_tool(conn, "ui_open_project", {"space_id": sid})
            elif name == "end_conversation":
                self.ended = "goodbye"
                result = {"done": True}
            else:
                result = core.run_tool(conn, name, args, [])
            conn.commit()
            return result, list(core._UI["actions"])
        finally:
            conn.close()

    async def _tool_calls(self, calls: list[dict[str, Any]]) -> None:
        refocus = False
        for c in calls:
            name = str(c.get("name", ""))
            try:
                args = json.loads(c.get("arguments") or "{}")
            except ValueError:
                args = {}
            await self.send_json({"type": "tool", "name": name})
            result, ui = await asyncio.to_thread(self._run_tool, name, args)
            if ui:
                await self.send_json({"type": "ui_actions", "actions": ui})
            refocus = refocus or name == "focus_project"
            await self.up.send({"type": "conversation.item.create", "item": {
                "type": "function_call_output", "call_id": c.get("call_id"),
                "output": json.dumps(result, ensure_ascii=False, default=str)[:12000]}})
        if self.ended:
            return
        if refocus:
            await self.up.send(session_update(self.instructions(), self.voice, self.s["live_transcribe_model"],
                                              self.tools()))
        await self.up.send({"type": "response.create"})

    async def _limits(self) -> str | None:
        minutes = (time.monotonic() - self.started) / 60.0
        if minutes >= float(self.s["live_max_minutes"]):
            return "max_minutes"
        cap = float(self.s["live_session_cap_usd"])
        if cap > 0 and self.cost >= cap:
            return "cap"
        return None

    async def pump(self) -> None:
        """Reads OpenAI's events until the conversation ends."""
        async for ev in self.up.events():
            t = ev.get("type", "")
            if t == "response.output_audio.delta":
                item = ev.get("item_id")
                if item != self.audio_item:
                    self.audio_item = item
                    await self.send_json({"type": "audio_start", "item_id": item})
                await self.send_audio(base64.b64decode(ev.get("delta", "")))
            elif t == "response.output_audio.done":
                await self.send_json({"type": "audio_done"})
            elif t == "response.output_audio_transcript.delta":
                await self.send_json({"type": "assistant_delta", "text": ev.get("delta", "")})
            elif t == "response.output_audio_transcript.done":
                text = str(ev.get("transcript") or "").strip()
                if text:
                    await self.send_json({"type": "assistant_text", "text": text})
                    await asyncio.to_thread(self._save, "assistant", text)
            elif t == "response.created":
                self.responding = True
            elif t == "input_audio_buffer.speech_started":
                self.last_speech = time.monotonic()
                await self.send_json({"type": "speech_started"})
            elif t == "conversation.item.input_audio_transcription.completed":
                text = str(ev.get("transcript") or "").strip()
                if text:
                    await self.send_json({"type": "user_text", "text": text})
                    await asyncio.to_thread(self._save, "user", text)
            elif t == "response.done":
                self.responding = False
                r = ev.get("response") or {}
                c = cost_of(self.up.model, r.get("usage"))
                if c is None:
                    self.cost_known = False
                else:
                    self.cost += c
                await self.send_json({"type": "cost", "usd": round(self.cost, 5) if self.cost_known else None,
                                      "minutes": round((time.monotonic() - self.started) / 60.0, 2)})
                calls = [o for o in (r.get("output") or []) if o.get("type") == "function_call"]
                if calls and r.get("status") == "completed":
                    await self._tool_calls(calls)
                if self.ended:
                    await self.send_json({"type": "ended", "reason": self.ended})
                    return
                reason = await self._limits()
                if reason:
                    self.ended = reason
                    await self.send_json({"type": "ended", "reason": reason})
                    return
            elif t == "error":
                err = ev.get("error") or {}
                if err.get("code") == "response_cancel_not_active":
                    continue  # harmless: the response had already finished
                await self.send_json({"type": "error", "message": str(err.get("message") or "OpenAI error")[:300]})

    async def idle_watch(self) -> None:
        while self.ended is None:
            await asyncio.sleep(5)
            if time.monotonic() - self.last_speech > 60 * float(self.s["live_idle_minutes"]) and not self.responding:
                self.ended = "idle"
                await self.send_json({"type": "ended", "reason": "idle"})
                return
            reason = await self._limits()
            if reason and not self.responding:
                self.ended = reason
                await self.send_json({"type": "ended", "reason": reason})
                return

    async def close(self) -> None:
        await self.up.close()


def friendly_error(exc: BaseException, reason: str, model: str) -> str:
    text = f"{reason} {exc}"
    if "model_not_found" in text or "does not exist" in text:
        return (f"Your OpenAI project cannot use {model} yet. Enable it on platform.openai.com "
                "(your project → Limits → model access), then try again.")
    if "invalid_api_key" in text or "401" in text:
        return "OpenAI rejected the key (401)."
    if "insufficient_quota" in text or "429" in text:
        return "OpenAI says the quota is exceeded (429). Check billing."
    return f"Cannot open the live conversation: {exc.__class__.__name__}."
