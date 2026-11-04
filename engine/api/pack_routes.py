"""Brain pack routes (Loop 11): preview and export a selection, import a pack as a layer, manage layers."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from engine import brain, database
from engine.brain import meaning, packs
from engine.paths import Layout


class SelectionIn(BaseModel):
    all: bool = False
    space_id: str | None = None
    place: str | None = Field(default=None, max_length=120)
    theme: str | None = Field(default=None, max_length=60)
    query: str | None = Field(default=None, max_length=300)
    note_ids: list[str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.model_dump().items() if v}


class ExportIn(BaseModel):
    selection: SelectionIn
    title: str = Field(min_length=1, max_length=120)
    author: str = Field(default="", max_length=120)
    licence: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=1000)


class ImportIn(BaseModel):
    path: str = Field(min_length=1, max_length=2000)


class LayerPatch(BaseModel):
    enabled: bool


def exports_dir(layout: Layout) -> Path:
    return layout.root / "exports"


def make_router(layout: Layout, auth: Callable[..., None], client_or_none: Callable[[], Any]) -> APIRouter:
    r = APIRouter(prefix="/packs", dependencies=[Depends(auth)])

    def guard(fn: Callable[..., Any], *args: Any) -> Any:
        try:
            return fn(*args)
        except packs.PackError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except brain.NotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.post("/preview")
    def preview(body: SelectionIn) -> dict[str, Any]:
        def go() -> dict[str, Any]:
            with database.session(layout.database) as conn:
                return packs.preview(conn, body.as_dict(), client_or_none())
        return guard(go)

    @r.post("/export", status_code=201)
    def export(body: ExportIn) -> dict[str, Any]:
        return guard(packs.export, layout.database, body.selection.as_dict(), exports_dir(layout), body.title,
                     body.author, body.licence, body.description, client_or_none())

    @r.get("/layers")
    def layers() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            return {"layers": packs.layers(conn), "exports_dir": str(exports_dir(layout))}

    @r.post("/import", status_code=201)
    def import_(body: ImportIn) -> dict[str, Any]:
        out = guard(packs.import_pack, layout.database, Path(body.path).expanduser())
        meaning.poke()  # items from another embedding model get their vectors within seconds
        return out

    @r.patch("/layers/{layer_id}")
    def patch(layer_id: str, body: LayerPatch) -> dict[str, Any]:
        def go() -> dict[str, Any]:
            with database.session(layout.database) as conn:
                return packs.set_enabled(conn, layer_id, body.enabled)
        return guard(go)

    @r.post("/layers/{layer_id}/merge")
    def merge(layer_id: str) -> dict[str, Any]:
        def go() -> dict[str, Any]:
            with database.session(layout.database) as conn:
                return packs.merge(conn, layer_id)
        return guard(go)

    @r.delete("/layers/{layer_id}")
    def remove(layer_id: str) -> dict[str, Any]:
        def go() -> dict[str, Any]:
            with database.session(layout.database) as conn:
                return packs.remove(conn, layer_id)
        return guard(go)

    return r
