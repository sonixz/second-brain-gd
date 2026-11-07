"""MCP routes (Loop MCP-A): POST /mcp for MCP clients (their own token, localhost only); /mcp/status and
/mcp/clients for the app (the app's token)."""
from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from engine import database
from engine.assistant.llm import make_client
from engine.mcp import server
from engine.paths import Layout
from engine.voice import secrets

LOCAL = ("127.0.0.1", "::1", "localhost", "testclient")


class ClientIn(BaseModel):
    name: str = Field(default="Claude Code", max_length=60)
    level: str = Field(default="read", max_length=20)


class LevelIn(BaseModel):
    level: str = Field(max_length=20)
    direct: bool | None = None


def make_router(layout: Layout, auth: Callable[..., None]) -> APIRouter:
    r = APIRouter()

    def backups_after_commit() -> None:
        """A client's new writing session: a full backup, once its first changes are committed (in the background)."""
        from engine.brain import timeline
        if timeline.take_pending_backups():
            import threading

            from engine import backups

            def go() -> None:
                try:
                    backups.backup(layout, "auto")
                except Exception:
                    pass
            threading.Thread(target=go, daemon=True).start()

    def llm_or_none():
        key, _ = secrets.get(layout, "openai")
        try:
            return make_client(key)
        except PermissionError:
            return None

    @r.post("/mcp")
    async def post_mcp(request: Request) -> Response:
        host = request.client.host if request.client else ""
        if host not in LOCAL:
            raise HTTPException(status_code=403, detail="the Brain answers this computer only")
        scheme, _, given = request.headers.get("authorization", "").partition(" ")
        try:
            body = json.loads((await request.body()) or b"null")
        except ValueError:
            return Response(json.dumps(server._error(None, -32700, "parse error")), media_type="application/json", status_code=400)
        with database.session(layout.database) as conn:
            client = server.client_for_token(conn, given) if scheme.lower() == "bearer" else None
            if client is None:
                return Response(json.dumps({"error": "unknown or revoked token: connect this tool again from the app"}),
                                media_type="application/json", status_code=401)
            server.ACTIVITY.touch(client["name"])
            llm = llm_or_none()
            msgs = body if isinstance(body, list) else [body]
            out = [x for x in (server.handle(conn, client, m, llm) for m in msgs) if x is not None]
        backups_after_commit()
        headers = {}
        if any(isinstance(m, dict) and m.get("method") == "initialize" for m in msgs):
            headers["Mcp-Session-Id"] = uuid.uuid4().hex
        if not out:
            return Response(status_code=202, headers=headers)
        payload = out if isinstance(body, list) else out[0]
        return Response(json.dumps(payload, ensure_ascii=False), media_type="application/json", headers=headers)

    @r.get("/mcp")
    def get_mcp() -> Response:  # no server-sent stream: plain request / response only
        return Response(status_code=405, headers={"Allow": "POST"})

    @r.delete("/mcp")
    def delete_mcp() -> Response:
        return Response(status_code=204)

    @r.get("/mcp/status", dependencies=[Depends(auth)])
    def get_status() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            clients = server.list_clients(conn)
            pending = conn.execute("SELECT COUNT(*) FROM mcp_proposals WHERE status = 'pending'").fetchone()[0]
        return {**server.ACTIVITY.status(), "clients": clients, "pending": pending}

    @r.get("/mcp/clients", dependencies=[Depends(auth)])
    def get_clients() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            return {"clients": server.list_clients(conn)}

    @r.post("/mcp/clients", dependencies=[Depends(auth)])
    def post_client(body: ClientIn) -> dict[str, Any]:
        """A new client: its token is in this answer only (only its hash is kept); the commands to plug it in."""
        with database.session(layout.database) as conn:
            c = server.create_client(conn, body.name, body.level)
        token_file = layout.root / "mcp" / f"{c['id']}.token"
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(c["token"], encoding="utf-8")  # for the relay (WSL); the user's own folder
        return {**c, "token_file": str(token_file)}

    @r.post("/mcp/clients/{cid}/level", dependencies=[Depends(auth)])
    def post_level(cid: str, body: LevelIn) -> dict[str, Any]:
        """The client's level (read, propose items, propose changes) and whether its proposals wait for approval."""
        with database.session(layout.database) as conn:
            try:
                if body.direct is not None:
                    conn.execute("UPDATE mcp_clients SET direct = ? WHERE id = ?", (1 if body.direct else 0, cid))
                return server.set_level(conn, cid, body.level)
            except server.McpError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.get("/mcp/proposals", dependencies=[Depends(auth)])
    def get_proposals(status: str = "pending") -> dict[str, Any]:
        from engine.mcp import proposals
        with database.session(layout.database) as conn:
            rows = proposals.listing(conn, status if status != "all" else "")
        return {"proposals": [{**p, "summary": proposals.summary(p)} for p in rows]}

    @r.post("/mcp/proposals/{pid}/{choice}", dependencies=[Depends(auth)])
    def post_proposal(pid: str, choice: str) -> dict[str, Any]:
        """approve / reject one proposal; pid « all » approves (or rejects) every pending one."""
        from engine.mcp import proposals
        if choice not in ("approve", "reject"):
            raise HTTPException(status_code=422, detail="approve or reject")
        llm = llm_or_none()
        with database.session(layout.database) as conn:
            ids = [p["id"] for p in proposals.listing(conn, "pending", None, 500)] if pid == "all" else [pid]
            try:
                out = [proposals.apply(conn, i, llm) if choice == "approve" else proposals.reject(conn, i) for i in ids]
            except proposals.Refused as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        backups_after_commit()
        return {"results": out}

    @r.delete("/mcp/clients/{cid}", dependencies=[Depends(auth)])
    def delete_client(cid: str) -> dict[str, Any]:
        with database.session(layout.database) as conn:
            server.revoke(conn, cid)
        (layout.root / "mcp" / f"{cid}.token").unlink(missing_ok=True)
        return {"revoked": cid}

    return r
