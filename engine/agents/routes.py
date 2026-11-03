"""Agent room routes (behind the local token)."""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from engine import database
from engine.agents import install
from engine.agents.session import AgentError, AgentManager
from engine.paths import Layout
from engine.voice import secrets

DEFAULTS = {
    "agents_folders": [],
    # Measured with tools in Chat Completions: gpt-6-sol is accurate and fast on the owner's project.
    "agents_model": "gpt-6-sol",
    # Conservative start agreed with the owner: the agent reads freely inside the chosen folder, and
    # anything that writes or runs a non-trusted command waits for approval in the UI.
    "agents_approval_policy": "untrusted",
    "agents_sandbox": "read-only",
}


class FolderIn(BaseModel):
    path: str = Field(min_length=1, max_length=1000)


class SessionIn(BaseModel):
    cwd: str = Field(min_length=1, max_length=1000)
    model: str | None = Field(default=None, max_length=60)


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=20000)


class DecisionIn(BaseModel):
    decision: Literal["accept", "acceptForSession", "decline", "cancel"]


class SettingsIn(BaseModel):
    model: str | None = Field(default=None, max_length=60)
    approval_policy: Literal["untrusted", "on-request", "on-failure", "never"] | None = None
    sandbox: Literal["read-only", "workspace-write"] | None = None


def make_router(layout: Layout, auth: Callable[..., None], manager: AgentManager) -> APIRouter:
    r = APIRouter(prefix="/agents", dependencies=[Depends(auth)])
    job: dict[str, Any] = {"running": False, "stage": None, "fraction": 0.0, "message": "", "error": None}

    def settings() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            return {k: database.get_setting(conn, k, v) for k, v in DEFAULTS.items()}

    def save(key: str, value: Any) -> None:
        with database.session(layout.database) as conn:
            database.set_setting(conn, key, value)

    def api_key() -> str:
        key, _ = secrets.get(layout, "openai")
        if not key and os.environ.get("SBGD_ASSISTANT_PROVIDER") == "fake":
            key = "sk-fake-test-key"  # tests: the fake agent accepts any sk- key
        if not key:
            raise HTTPException(status_code=409, detail="Agents need your OpenAI key (Voice settings).")
        return key

    def inside_allowed(path: Path, folders: list[str]) -> bool:
        for f in folders:
            try:
                path.relative_to(Path(f))
                return True
            except ValueError:
                continue
        return False

    def session_or_404(sid: str):
        try:
            return manager.get(sid)
        except KeyError:
            raise HTTPException(status_code=404, detail="No such agent session.") from None

    @r.get("/status")
    def status() -> dict[str, Any]:
        info = install.installed_info(layout)
        manifest, _ = install.load_manifest()
        return {"installed": info is not None, "version": manifest.get("version"), "platform": install.platform_key(),
                "binary": info.get("binary") if info else None, "install": dict(job), **settings(),
                "sessions": [{k: v for k, v in s.snapshot(10**9).items() if k != "events"}
                             for s in manager.sessions.values()]}

    @r.post("/install", status_code=202)
    def post_install() -> dict[str, Any]:
        if job["running"]:
            return dict(job)
        job.update(running=True, error=None, stage="download", fraction=0.0, message="Starting…")

        def work() -> None:
            try:
                install.install(layout, lambda st, fr, msg: job.update(stage=st, fraction=fr, message=msg))
            except Exception as exc:
                job["error"] = str(exc)[:300]
            finally:
                job["running"] = False

        threading.Thread(target=work, name="agents-install", daemon=True).start()
        return dict(job)

    @r.patch("/settings")
    def patch_settings(body: SettingsIn) -> dict[str, Any]:
        for field, key in (("model", "agents_model"), ("approval_policy", "agents_approval_policy"),
                           ("sandbox", "agents_sandbox")):
            v = getattr(body, field)
            if v is not None:
                save(key, v)
        return settings()

    @r.post("/folders")
    def add_folder(body: FolderIn) -> dict[str, Any]:
        p = Path(body.path).expanduser()
        if not p.is_absolute() or not p.is_dir():
            raise HTTPException(status_code=422, detail="Choose an existing folder.")
        p = p.resolve()
        if p == Path(p.anchor) or p == Path.home().resolve():
            raise HTTPException(status_code=422, detail="Choose a project folder, not a whole drive or your home folder.")
        if p == layout.root.resolve() or inside_allowed(p, [str(layout.root.resolve())]):
            raise HTTPException(status_code=422, detail="The app's own data folder cannot be given to agents.")
        folders = [f for f in settings()["agents_folders"] if f != str(p)] + [str(p)]
        save("agents_folders", folders)
        return {"folders": folders}

    @r.delete("/folders")
    def del_folder(path: str = Query(min_length=1, max_length=1000)) -> dict[str, Any]:
        folders = [f for f in settings()["agents_folders"] if f != path]
        save("agents_folders", folders)
        return {"folders": folders}

    @r.post("/sessions", status_code=201)
    def post_session(body: SessionIn) -> dict[str, Any]:
        info = install.installed_info(layout)
        if info is None:
            raise HTTPException(status_code=409, detail="Agents are not installed yet (Install in the agent room).")
        s = settings()
        cwd = Path(body.cwd).expanduser()
        if not cwd.is_dir():
            raise HTTPException(status_code=422, detail="That folder does not exist.")
        cwd = cwd.resolve()
        if not inside_allowed(cwd, s["agents_folders"]):
            raise HTTPException(status_code=403, detail="Agents only work in folders you added to the agent room.")
        try:
            sess = manager.create(info["binary"], cwd, body.model or s["agents_model"], api_key(),
                                  s["agents_approval_policy"], s["agents_sandbox"])
        except AgentError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return sess.snapshot()

    @r.get("/sessions/{sid}")
    def get_session(sid: str, after: int = Query(0, ge=0)) -> dict[str, Any]:
        return session_or_404(sid).snapshot(after)

    @r.post("/sessions/{sid}/messages", status_code=202)
    def post_message(sid: str, body: MessageIn) -> dict[str, Any]:
        s = session_or_404(sid)
        try:
            return {"turn": s.send(body.text)}
        except AgentError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @r.post("/sessions/{sid}/approvals/{request_id}")
    def post_decision(sid: str, request_id: int, body: DecisionIn) -> dict[str, Any]:
        s = session_or_404(sid)
        try:
            s.decide(request_id, body.decision)
        except AgentError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True}

    @r.post("/sessions/{sid}/interrupt")
    def post_interrupt(sid: str) -> dict[str, Any]:
        try:
            session_or_404(sid).interrupt()
        except AgentError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"ok": True}

    @r.delete("/sessions/{sid}", status_code=204, response_class=Response)
    def del_session(sid: str) -> Response:
        session_or_404(sid)
        manager.remove(sid)
        return Response(status_code=204)

    return r
