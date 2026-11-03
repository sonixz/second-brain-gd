"""Relay between Godot (local WebSocket) and the OpenAI Realtime transcription API.

Godot -> engine:  binary frames = PCM16 little-endian, mono, 24 kHz
                  text {"type": "commit"} = end of an utterance (push-to-talk release)
                  text {"type": "stop"}   = close the session
engine -> Godot:  {"type": "ready", "model": ...}
                  {"type": "delta", "item_id": ..., "text": ...}
                  {"type": "final", "item_id": ..., "text": ...}
                  {"type": "error", "message": ...}
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from typing import Any, Awaitable, Callable

REALTIME_URL = "wss://api.openai.com/v1/realtime?intent=transcription"
SAMPLE_RATE = 24000
BYTES_PER_SECOND = SAMPLE_RATE * 2
PRICE_PER_MINUTE_USD = 0.017  # gpt-realtime-whisper list price, used for the estimate only

Send = Callable[[dict[str, Any]], Awaitable[None]]


def session_update(model: str, languages: list[str], delay: str | None, prompt: str | None) -> dict[str, Any]:
    """`languages` with one entry is sent as `language` (gpt-realtime-whisper refuses the
    plural form, measured 2026-11-02); several entries use `languages`; none = auto-detect."""
    transcription: dict[str, Any] = {"model": model}
    if len(languages) == 1:
        transcription["language"] = languages[0]
    elif languages:
        transcription["languages"] = languages
    if delay:
        transcription["delay"] = delay
    if prompt:
        transcription["prompt"] = prompt
    return {"type": "session.update", "session": {"type": "transcription", "audio": {"input": {
        "format": {"type": "audio/pcm", "rate": SAMPLE_RATE},
        "transcription": transcription,
        "turn_detection": None,
    }}}}


class OpenAIRelay:
    """One transcription session against OpenAI."""

    provider = "openai"

    def __init__(self, api_key: str, model: str, languages: list[str], delay: str | None, prompt: str | None):
        self.api_key = api_key
        self.model = model
        self.languages = languages
        self.delay = delay
        self.prompt = prompt
        self._ws: Any = None
        self._reader: asyncio.Task | None = None

    async def open(self, send: Send) -> None:
        import websockets

        self._ws = await websockets.connect(
            REALTIME_URL, additional_headers={"Authorization": f"Bearer {self.api_key}"},
            open_timeout=10, ping_interval=20, max_size=2**22)
        await self._ws.send(json.dumps(session_update(self.model, self.languages, self.delay, self.prompt)))
        self._reader = asyncio.create_task(self._read(send))

    async def _read(self, send: Send) -> None:
        try:
            async for raw in self._ws:
                ev = json.loads(raw)
                kind = ev.get("type", "")
                if kind == "conversation.item.input_audio_transcription.delta":
                    await send({"type": "delta", "item_id": ev.get("item_id"), "text": ev.get("delta", "")})
                elif kind == "conversation.item.input_audio_transcription.completed":
                    await send({"type": "final", "item_id": ev.get("item_id"), "text": ev.get("transcript", "")})
                elif kind == "conversation.item.input_audio_transcription.failed":
                    err = ev.get("error") or {}
                    await send({"type": "error", "message": err.get("message", "transcription failed")})
                elif kind == "error":
                    err = ev.get("error") or {}
                    await send({"type": "error", "message": err.get("message", "OpenAI error")})
                elif kind in ("session.updated", "transcription_session.updated", "session.created"):
                    await send({"type": "session", "event": kind})
        except Exception as exc:  # connection closed or broken
            await send({"type": "error", "message": f"OpenAI connection closed: {exc.__class__.__name__}"})

    async def append(self, pcm: bytes) -> None:
        await self._ws.send(json.dumps({"type": "input_audio_buffer.append",
                                        "audio": base64.b64encode(pcm).decode("ascii")}))

    async def commit(self) -> None:
        await self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
        if self._reader is not None:
            self._reader.cancel()


class FakeRelay:
    """Test double, enabled only with SBGD_VOICE_PROVIDER=fake. Never used otherwise."""

    provider = "fake"

    def __init__(self, *_args: Any) -> None:
        self.model = "fake"
        self._bytes = 0
        self._send: Send | None = None
        self._turn = 0

    async def open(self, send: Send) -> None:
        self._send = send

    async def append(self, pcm: bytes) -> None:
        before = self._bytes // (BYTES_PER_SECOND // 2)
        self._bytes += len(pcm)
        if self._bytes // (BYTES_PER_SECOND // 2) > before and self._send:
            await self._send({"type": "delta", "item_id": f"fake{self._turn}", "text": "… "})

    async def commit(self) -> None:
        if self._send:
            secs = self._bytes / BYTES_PER_SECOND
            await self._send({"type": "final", "item_id": f"fake{self._turn}",
                              "text": f"[fake transcript of {secs:.1f} s of audio]"})
        self._turn += 1
        self._bytes = 0

    async def close(self) -> None:
        pass


def make_relay(api_key: str | None, model: str, languages: list[str], delay: str | None,
               prompt: str | None) -> OpenAIRelay | FakeRelay:
    if os.environ.get("SBGD_VOICE_PROVIDER") == "fake":
        return FakeRelay()
    if not api_key:
        raise PermissionError("no OpenAI key configured")
    return OpenAIRelay(api_key, model, languages, delay, prompt)


class Meter:
    def __init__(self) -> None:
        self.started = time.monotonic()
        self.audio_bytes = 0

    @property
    def audio_seconds(self) -> float:
        return self.audio_bytes / BYTES_PER_SECOND

    @property
    def cost_usd(self) -> float:
        return round(self.audio_seconds / 60.0 * PRICE_PER_MINUTE_USD, 5)
