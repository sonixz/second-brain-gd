"""Source routes: add files and links, list, delete, search (all behind the local token)."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from engine import brain, database
from engine.assistant.llm import LLMError, make_client
from engine.paths import Layout
from engine.sources import core, extract
from engine.sources.core import embeddings_model, search_any, should_try_embeddings
from engine.voice import secrets


class FileIn(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    space_id: str | None = None


class UrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    space_id: str | None = None


def make_router(layout: Layout, auth: Callable[..., None]) -> APIRouter:
    r = APIRouter(prefix="/sources", dependencies=[Depends(auth)])

    def client_or_none():
        key, _ = secrets.get(layout, "openai")
        try:
            return make_client(key)
        except PermissionError:
            return None

    def add(fn: Callable[..., Any], *args: Any) -> dict[str, Any]:
        client = client_or_none()
        try:
            with database.session(layout.database) as conn:
                src = fn(conn, client, *args)
            if client is not None and not src.get("duplicate"):
                with database.session(layout.database) as conn:
                    if should_try_embeddings(conn):
                        src["embeddings"] = core.embed_pending(conn, client, embeddings_model(conn))
        except extract.ExtractError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except brain.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return src

    @r.post("/file", status_code=201)
    def post_file(body: FileIn) -> dict[str, Any]:
        return add(core.ingest_file, body.path, body.space_id)

    @r.post("/url", status_code=201)
    def post_url(body: UrlIn) -> dict[str, Any]:
        return add(core.ingest_url, body.url, body.space_id)

    @r.get("")
    def get_sources() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            return {"sources": core.list_sources(conn),
                    "embeddings": database.get_setting(conn, "embeddings_status") or {"available": None},
                    "supported": sorted(extract.SUPPORTED)}

    @r.delete("/{source_id}", status_code=204, response_class=Response)
    def del_source(source_id: str) -> Response:
        with database.session(layout.database) as conn:
            try:
                core.delete_source(conn, source_id)
            except brain.NotFound as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @r.get("/search")
    def search(q: str = Query(min_length=1, max_length=300), limit: int = Query(8, ge=1, le=30)) -> dict[str, Any]:
        with database.session(layout.database) as conn:
            return {"results": search_any(conn, client_or_none(), q, limit)}

    @r.post("/embeddings/retry")
    def retry_embeddings() -> dict[str, Any]:
        client = client_or_none()
        if client is None:
            raise HTTPException(status_code=409, detail="No OpenAI key configured.")
        with database.session(layout.database) as conn:
            database.set_setting(conn, "embeddings_status", {"available": True, "checked_at": ""})
            return core.embed_pending(conn, client, embeddings_model(conn), batch=256)

    return r
