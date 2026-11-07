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


class ServerIn(BaseModel):
    name: str = Field(default="", max_length=40)
    url: str = Field(min_length=8, max_length=500)
    key: str = Field(default="", max_length=2000)            # stored in the OS credential store, never echoed
    key_header: str = Field(default="Authorization", max_length=40)
    publisher: str = Field(default="", max_length=60)
    source: str = Field(default="", max_length=300)


class KeyIn(BaseModel):
    key: str = Field(default="", max_length=2000)
    header: str = Field(default="", max_length=40)


class OffIn(BaseModel):
    off: list[str] = Field(default_factory=list, max_length=200)


class LocalIn(BaseModel):
    name: str = Field(default="", max_length=40)
    command: str = Field(default="", max_length=1000)
    env_names: list[str] = Field(default_factory=list, max_length=20)
    publisher: str = Field(default="", max_length=60)
    source: str = Field(default="", max_length=300)
    package_type: str = Field(default="", max_length=10)
    package_id: str = Field(default="", max_length=200)
    package_version: str = Field(default="", max_length=60)


class EnvIn(BaseModel):
    name: str = Field(max_length=60)
    value: str = Field(default="", max_length=4000)


class SamplingIn(BaseModel):
    allow: bool = False
    cap: int = Field(default=20, ge=0, le=1000)


class AnswerIn(BaseModel):
    action: str = Field(default="accept", max_length=10)   # accept, decline, cancel
    content: dict[str, Any] = Field(default_factory=dict)


class CapIn(BaseModel):
    tokens: int = Field(default=0, ge=0, le=100_000_000)


class AgentsIn(BaseModel):
    agents: list[str] = Field(default_factory=list, max_length=50)


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
            from engine.mcp import client as mcp
            out_servers = [{k: s.get(k) for k in ("id", "name", "status", "error")} | {"tools": len(s.get("tools") or [])}
                           for s in mcp.servers(conn)]
            waiting_out = conn.execute("SELECT COUNT(*) FROM mcp_confirms WHERE status = 'pending'").fetchone()[0]
            waiting_out += conn.execute("SELECT COUNT(*) FROM mcp_questions WHERE status = 'pending'").fetchone()[0]
        return {**server.ACTIVITY.status(), "clients": clients, "pending": pending + waiting_out,
                "out": {**mcp.OUT.status(), "servers": out_servers}}

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

    @r.get("/mcp/servers", dependencies=[Depends(auth)])
    def get_servers() -> dict[str, Any]:
        """MCP servers the agents may use (Loop MCP-C), and the ones suggested."""
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            items = mcp.servers(conn)
            use = mcp.usage(conn)
            risks = mcp.risks(conn)
            waiting = mcp.confirmations(conn)
            asked = mcp.questions(conn)
        have = {s.get("url") for s in items}
        for s in items:
            s["usage"] = use.get(s["id"], {"calls": 0, "tokens": 0, "agents": {}})
        return {"servers": items, "suggested": [s for s in mcp.SUGGESTED if s["url"] not in have], "risks": risks,
                "confirmations": waiting, "questions": asked}

    @r.get("/mcp/catalog", dependencies=[Depends(auth)])
    def get_catalog(q: str = "") -> dict[str, Any]:
        """Search the official MCP registry (nothing is connected here)."""
        from engine.mcp import catalog
        if not q.strip():
            return {"results": []}
        try:
            return {"results": catalog.search(q, 20)}
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @r.post("/mcp/servers/{sid}/key", dependencies=[Depends(auth)])
    def post_server_key(sid: str, body: KeyIn) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            try:
                mcp.set_key(conn, sid, body.key, body.header)
                return mcp.refresh(conn, sid)
            except mcp.McpClientError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @r.post("/mcp/servers/{sid}/off", dependencies=[Depends(auth)])
    def post_server_off(sid: str, body: OffIn) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            return mcp.set_off(conn, sid, body.off)

    @r.post("/mcp/servers/{sid}/cap", dependencies=[Depends(auth)])
    def post_server_cap(sid: str, body: CapIn) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            return mcp.set_cap(conn, sid, body.tokens)

    @r.post("/mcp/confirmations/{cid}/{choice}", dependencies=[Depends(auth)])
    def post_confirmation(cid: str, choice: str) -> dict[str, Any]:
        """The user confirms (or refuses) one call of a tool that writes outside."""
        from engine.mcp import client as mcp
        if choice not in ("approve", "refuse"):
            raise HTTPException(status_code=422, detail="approve or refuse")
        with database.session(layout.database) as conn:
            return mcp.decide(conn, cid, choice == "approve")

    @r.post("/mcp/servers/local", dependencies=[Depends(auth)])
    def post_local(body: LocalIn) -> dict[str, Any]:
        """A local server, waiting for the owner's approval of its exact command (nothing starts here)."""
        from engine.mcp import client as mcp
        package = {"type": body.package_type, "identifier": body.package_id, "version": body.package_version} if body.package_id else None
        with database.session(layout.database) as conn:
            try:
                return mcp.add_local(conn, body.name, body.command, body.env_names, body.publisher, body.source, package)
            except mcp.McpClientError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.post("/mcp/servers/{sid}/approve", dependencies=[Depends(auth)])
    def post_approve(sid: str) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            try:
                return mcp.approve_local(conn, sid)
            except mcp.McpClientError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.post("/mcp/servers/{sid}/env", dependencies=[Depends(auth)])
    def post_env(sid: str, body: EnvIn) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            try:
                mcp.set_env(conn, sid, body.name, body.value)
                return {"saved": body.name}
            except mcp.McpClientError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.post("/mcp/servers/{sid}/stop", dependencies=[Depends(auth)])
    def post_stop_local(sid: str) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            return mcp.stop_local(conn, sid)

    @r.get("/mcp/servers/{sid}/log", dependencies=[Depends(auth)])
    def get_local_log(sid: str) -> dict[str, Any]:
        from engine.mcp import client as mcp
        return {"log": mcp.local_log(sid)}

    @r.post("/mcp/servers/{sid}/signin", dependencies=[Depends(auth)])
    def post_signin(sid: str) -> dict[str, Any]:
        """Starts an account sign-in: the URL to open in the user's browser; the answer comes back to 127.0.0.1."""
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            try:
                return mcp.sign_in(conn, sid)
            except mcp.McpClientError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.get("/mcp/servers/{sid}/signin", dependencies=[Depends(auth)])
    def get_signin(sid: str) -> dict[str, Any]:
        from engine.mcp import oauth
        return oauth.flow_status(sid)

    @r.post("/mcp/servers/{sid}/signout", dependencies=[Depends(auth)])
    def post_signout(sid: str) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            return mcp.sign_out(conn, sid)

    @r.post("/mcp/servers/{sid}/sampling", dependencies=[Depends(auth)])
    def post_sampling(sid: str, body: SamplingIn) -> dict[str, Any]:
        """Whether this server may ask the Brain's model to write (off by default), and how many times a month."""
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            return mcp.set_sampling(conn, sid, body.allow, body.cap)

    @r.get("/mcp/questions", dependencies=[Depends(auth)])
    def get_questions() -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            return {"questions": mcp.questions(conn)}

    @r.post("/mcp/questions/{qid}", dependencies=[Depends(auth)])
    def post_question(qid: str, body: AnswerIn) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            return mcp.answer_question(conn, qid, body.action, body.content)

    @r.post("/mcp/out/stop", dependencies=[Depends(auth)])
    def post_out_stop() -> dict[str, Any]:
        """Stop: the MCP calls under way end at their next event."""
        from engine.mcp import client as mcp
        return {"stopping": mcp.OUT.cancel()}

    @r.post("/mcp/servers", dependencies=[Depends(auth)])
    def post_server(body: ServerIn) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            try:
                return mcp.add_server(conn, body.name, body.url, body.key, body.key_header, body.publisher, body.source)
            except mcp.McpClientError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.post("/mcp/servers/{sid}/refresh", dependencies=[Depends(auth)])
    def post_server_refresh(sid: str) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            try:
                mcp.get_server(conn, sid)
            except mcp.McpClientError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            return mcp.refresh(conn, sid)

    @r.post("/mcp/servers/{sid}/agents", dependencies=[Depends(auth)])
    def post_server_agents(sid: str, body: AgentsIn) -> dict[str, Any]:
        """Which agents may use this server: ["*"] for all of them."""
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            try:
                return mcp.set_agents(conn, sid, body.agents)
            except mcp.McpClientError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc

    @r.delete("/mcp/servers/{sid}", dependencies=[Depends(auth)])
    def delete_server(sid: str) -> dict[str, Any]:
        from engine.mcp import client as mcp
        with database.session(layout.database) as conn:
            mcp.remove_server(conn, sid)
        return {"removed": sid}

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
