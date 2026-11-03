"""Voice routes: key management (BYOK) and the streaming WebSocket."""
from __future__ import annotations

import asyncio
import json
import secrets as pysecrets
import urllib.error
import urllib.request
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from engine import database
from engine.events import utc_now
from engine.paths import Layout
from engine.voice import secrets
from engine.voice.realtime import PRICE_PER_MINUTE_USD, Meter, make_relay

DEFAULTS = {"voice_model": "gpt-realtime-whisper", "voice_languages": ["fr", "en"], "voice_delay": "low",
            "voice_prompt": ""}
MODELS_URL = "https://api.openai.com/v1/models/"


class KeyIn(BaseModel):
    api_key: str = Field(min_length=20, max_length=400)


class VoiceSettingsIn(BaseModel):
    model: str | None = Field(default=None, max_length=80)
    languages: list[str] | None = None
    delay: str | None = Field(default=None, max_length=16)
    prompt: str | None = Field(default=None, max_length=1000)


def verify_key(api_key: str, model: str) -> dict[str, Any]:
    """Free check: can this key see this model? (GET /v1/models/{model})"""
    req = urllib.request.Request(MODELS_URL + model, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return {"ok": True, "status": resp.status, "message": f"Key accepted, {model} available."}
    except urllib.error.HTTPError as exc:
        messages = {401: "OpenAI rejected this key (401). Check that it was copied entirely.",
                    403: "This key has no access to the API (403). Check the project's permissions.",
                    404: f"The key works, but the model {model} is not available to this account (404).",
                    429: "OpenAI says the quota or rate limit is exceeded (429). Check billing."}
        return {"ok": False, "status": exc.code, "message": messages.get(exc.code, f"OpenAI answered HTTP {exc.code}.")}
    except OSError as exc:
        return {"ok": False, "status": 0, "message": f"Cannot reach OpenAI: {exc.__class__.__name__}. Check the connection."}


def make_router(layout: Layout, auth: Callable[..., None], token: str) -> APIRouter:
    r = APIRouter(prefix="/voice")

    def settings() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            return {k: database.get_setting(conn, k, v) for k, v in DEFAULTS.items()}

    def record(stage: str, status: str, message: str, **details: Any) -> None:
        with database.session(layout.database) as conn:
            database.record_event(conn, {"timestamp": utc_now(), "component": "voice", "stage": stage,
                                         "status": status, "message": message, "details": details or None})

    def status_payload() -> dict[str, Any]:
        info = secrets.info(layout, "openai")
        s = settings()
        return {"configured": info.configured, "source": info.source, "backend": info.backend, "hint": info.hint,
                "model": s["voice_model"], "languages": s["voice_languages"], "delay": s["voice_delay"],
                "price_per_minute_usd": PRICE_PER_MINUTE_USD, "provider": "openai"}

    @r.get("/status", dependencies=[Depends(auth)])
    def get_status() -> dict[str, Any]:
        return status_payload()

    @r.put("/key", dependencies=[Depends(auth)])
    def put_key(body: KeyIn) -> dict[str, Any]:
        key = body.api_key.strip()
        check = verify_key(key, settings()["voice_model"])
        if not check["ok"] and check["status"] in (401, 403):
            record("key", "error", "OpenAI key rejected", http_status=check["status"])
            raise HTTPException(status_code=422, detail=check["message"])
        where = secrets.store(layout, "openai", key)
        record("key", "ok" if check["ok"] else "warning",
               f"OpenAI key saved ({where})" + ("" if check["ok"] else f"; check: {check['message']}"))
        return {**status_payload(), "check": check}

    @r.post("/key/test", dependencies=[Depends(auth)])
    def test_key() -> dict[str, Any]:
        key, _ = secrets.get(layout, "openai")
        if not key:
            raise HTTPException(status_code=404, detail="No OpenAI key configured.")
        return verify_key(key, settings()["voice_model"])

    @r.delete("/key", dependencies=[Depends(auth)])
    def delete_key() -> dict[str, Any]:
        secrets.delete(layout, "openai")
        record("key", "ok", "OpenAI key removed")
        return status_payload()

    @r.patch("/settings", dependencies=[Depends(auth)])
    def patch_settings(body: VoiceSettingsIn) -> dict[str, Any]:
        with database.session(layout.database) as conn:
            for field, key in (("model", "voice_model"), ("languages", "voice_languages"),
                               ("delay", "voice_delay"), ("prompt", "voice_prompt")):
                value = getattr(body, field)
                if value is not None:
                    database.set_setting(conn, key, value)
        return status_payload()

    @r.websocket("/stream")
    async def stream(ws: WebSocket) -> None:
        header = ws.headers.get("authorization", "")
        scheme, _, given = header.partition(" ")
        if scheme.lower() != "bearer" or not pysecrets.compare_digest(given.strip(), token):
            await ws.close(code=4401)
            return
        await ws.accept()
        s = settings()
        key, source = secrets.get(layout, "openai")
        lock = asyncio.Lock()

        async def send(msg: dict[str, Any]) -> None:
            async with lock:
                try:
                    await ws.send_text(json.dumps(msg))
                except Exception:
                    pass

        try:
            relay = make_relay(key, s["voice_model"], s["voice_languages"], s["voice_delay"], s["voice_prompt"])
            await relay.open(send)
        except PermissionError:
            await send({"type": "error", "message": "No OpenAI key configured. Add yours in Voice settings."})
            await ws.close(code=4403)
            return
        except Exception as exc:
            await send({"type": "error", "message": f"Cannot open the transcription session: {exc}"})
            record("session", "error", f"Voice session failed to open: {exc.__class__.__name__}")
            await ws.close(code=1011)
            return
        meter = Meter()
        record("session", "started", f"Voice session opened ({relay.provider}, {relay.model})")
        await send({"type": "ready", "model": relay.model, "provider": relay.provider})
        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("bytes"):
                    meter.audio_bytes += len(msg["bytes"])
                    await relay.append(msg["bytes"])
                elif msg.get("text"):
                    cmd = json.loads(msg["text"]).get("type")
                    if cmd == "commit":
                        await relay.commit()
                    elif cmd == "stop":
                        break
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            await asyncio.sleep(0.05)
            await relay.close()
            record("session", "ok", f"Voice session closed: {meter.audio_seconds:.1f} s of audio, "
                   f"≈ ${meter.cost_usd:.4f} ({relay.provider})", audio_seconds=round(meter.audio_seconds, 2),
                   estimated_cost_usd=meter.cost_usd)

    return r
