"""Second brain HTTP routes. All require the local token."""
from __future__ import annotations

from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from engine import brain, database
from engine.paths import Layout


class SpaceIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["project", "area", "resource", "archive"] = "project"
    color: str | None = Field(default=None, max_length=16)
    icon: str | None = Field(default=None, max_length=32)


class NoteIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(default="", max_length=200_000)
    space_id: str | None = None
    kind: Literal["note", "idea", "task", "journal", "reference"] = "note"
    source: Literal["typed", "voice", "import", "agent"] = "typed"


class NotePatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=200_000)
    space_id: str | None = None
    kind: Literal["note", "idea", "task", "journal", "reference"] | None = None
    status: Literal["active", "done", "archived"] | None = None
    pinned: bool | None = None


def make_router(layout: Layout, auth: Callable[..., None]) -> APIRouter:
    r = APIRouter(prefix="/brain", dependencies=[Depends(auth)])

    def run(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            with database.session(layout.database) as conn:
                return fn(conn, *args, **kwargs)
        except brain.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.get("/briefing")
    def get_briefing() -> dict[str, Any]:
        return run(brain.briefing)

    @r.get("/graph")
    def get_graph() -> dict[str, Any]:
        return run(brain.graph)

    @r.get("/spaces")
    def get_spaces() -> dict[str, Any]:
        return {"spaces": run(brain.list_spaces)}

    @r.post("/spaces", status_code=201)
    def post_space(body: SpaceIn) -> dict[str, Any]:
        return run(brain.create_space, body.name, body.kind, body.color, body.icon)

    @r.get("/notes")
    def get_notes(space_id: str | None = None, limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
        return {"notes": run(brain.list_notes, space_id, limit)}

    @r.post("/notes", status_code=201)
    def post_note(body: NoteIn) -> dict[str, Any]:
        return run(brain.create_note, body.title, body.body, body.space_id, body.kind, body.source)

    @r.get("/notes/{note_id}")
    def get_note(note_id: str) -> dict[str, Any]:
        return run(brain.get_note, note_id)

    @r.patch("/notes/{note_id}")
    def patch_note(note_id: str, body: NotePatch) -> dict[str, Any]:
        return run(brain.update_note, note_id, **body.model_dump(exclude_none=True))

    @r.delete("/notes/{note_id}", status_code=204, response_class=Response)
    def del_note(note_id: str) -> Response:
        run(brain.delete_note, note_id)
        return Response(status_code=204)

    @r.get("/search")
    def get_search(q: str = Query(min_length=1, max_length=200), limit: int = Query(30, ge=1, le=200)) -> dict[str, Any]:
        return {"results": run(brain.search, q, limit)}

    return r
