"""Assistant HTTP routes (all behind the local token)."""
from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from engine import brain, database
from engine.assistant import core
from engine.assistant.llm import LLMError, make_client
from engine.paths import Layout
from engine.voice import secrets


class ChatIn(BaseModel):
    text: str = Field(min_length=1, max_length=8000)
    space_id: str | None = None
    spoken: bool = False  # the message came by voice: the reply is read aloud, so it must be short
    open_note: str | None = Field(default=None, max_length=64)  # the item open on screen, for « garde ce lien »


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    theme: str = Field(default="morning", max_length=16)


class SettingsIn(BaseModel):
    chat_model: str | None = Field(default=None, max_length=60)
    classify_model: str | None = Field(default=None, max_length=60)
    review_model: str | None = Field(default=None, max_length=60)
    review_effort: Literal["", "low", "medium", "high", "xhigh"] | None = None
    voice: str | None = Field(default=None, max_length=30)
    auto_classify: bool | None = None


def make_router(layout: Layout, auth: Callable[..., None]) -> APIRouter:
    r = APIRouter(prefix="/assistant", dependencies=[Depends(auth)])

    def run(fn: Callable[..., Any], *args: Any, needs_client: bool = True) -> Any:
        try:
            with database.session(layout.database) as conn:
                if needs_client:
                    key, _ = secrets.get(layout, "openai")
                    return fn(conn, make_client(key), *args)
                return fn(conn, *args)
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail="The assistant needs your OpenAI key (Voice settings).") from exc
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except brain.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @r.get("/status")
    def status() -> dict[str, Any]:
        info = secrets.info(layout, "openai")
        with database.session(layout.database) as conn:
            s = core.settings(conn)
        import os
        fake = os.environ.get("SBGD_ASSISTANT_PROVIDER") == "fake"
        return {"configured": info.configured or fake, "provider": "fake" if fake else "openai", **s}

    @r.patch("/settings")
    def patch_settings(body: SettingsIn) -> dict[str, Any]:
        with database.session(layout.database) as conn:
            for field, key in (("chat_model", "assistant_chat_model"), ("classify_model", "assistant_classify_model"),
                               ("review_model", "assistant_review_model"), ("review_effort", "assistant_review_effort"),
                               ("voice", "assistant_voice"), ("auto_classify", "assistant_auto_classify")):
                v = getattr(body, field)
                if v is not None:
                    database.set_setting(conn, key, v)
            return core.settings(conn)

    @r.get("/history")
    def get_history(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
        return {"conversation": core.today_conversation(),
                "messages": run(core.history, core.today_conversation(), limit, needs_client=False)}

    @r.post("/chat")
    def post_chat(body: ChatIn) -> dict[str, Any]:
        return run(core.chat, body.text, body.space_id, body.spoken, body.open_note)

    @r.post("/briefing")
    def post_briefing(force: bool = False) -> dict[str, Any]:
        return run(core.briefing, force)

    @r.post("/review")
    def post_review() -> dict[str, Any]:
        return run(core.weekly_review)

    @r.post("/classify/{note_id}")
    def post_classify(note_id: str) -> dict[str, Any]:
        from engine.brain import archivist

        def go(conn, client, nid):
            core._CLIENT["c"] = client
            return archivist.file_item(conn, client, nid, float(core.settings(conn)["assistant_min_confidence"]))
        return run(go, note_id)

    @r.post("/speak")
    def post_speak(body: SpeakIn) -> Response:
        audio, cached = run(core.speak, body.text, body.theme, layout.runtime / "tts")
        return Response(content=audio, media_type="audio/mpeg", headers={"X-Cache": "hit" if cached else "miss"})

    @r.post("/actions/{action_id}/undo")
    def post_undo(action_id: int) -> dict[str, Any]:
        return run(core.undo, action_id, needs_client=False)

    @r.get("/actions")
    def get_actions(limit: int = Query(30, ge=1, le=200)) -> dict[str, Any]:
        with database.session(layout.database) as conn:
            rows = conn.execute("SELECT id, kind, note_id, reason, created_at, undone_at FROM assistant_actions"
                                " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return {"actions": [dict(x) for x in rows]}

    return r
