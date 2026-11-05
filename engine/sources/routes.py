"""Source routes: add files and links, list, delete, search (all behind the local token)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from engine import brain, database
from engine.assistant.llm import LLMError, make_client
from engine.paths import Layout
from engine.sources import core, extract, images
from engine.sources.core import embeddings_model, search_any, should_try_embeddings
from engine.voice import secrets


class FileIn(BaseModel):
    path: str = Field(min_length=1, max_length=2000)
    space_id: str | None = None
    job: str | None = Field(default=None, max_length=64)  # poll GET /sources/progress/{job} meanwhile


class UrlIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    space_id: str | None = None
    job: str | None = Field(default=None, max_length=64)


def make_router(layout: Layout, auth: Callable[..., None]) -> APIRouter:
    r = APIRouter(prefix="/sources", dependencies=[Depends(auth)])

    def client_or_none():
        key, _ = secrets.get(layout, "openai")
        try:
            return make_client(key)
        except PermissionError:
            return None

    def add(fn: Callable[..., Any], *args: Any, job: str | None = None) -> dict[str, Any]:
        from engine.sources import progress

        token = progress.start(job)
        try:
            return _add(fn, *args)
        finally:
            progress.finish(token)

    def _add(fn: Callable[..., Any], *args: Any) -> dict[str, Any]:
        from engine.sources import progress

        client = client_or_none()
        try:
            with database.session(layout.database) as conn:
                src = fn(conn, client, *args)
            if client is not None and not src.get("duplicate"):
                with database.session(layout.database) as conn:
                    if should_try_embeddings(conn):
                        progress.report("indexing")
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
        return add(core.ingest_file, body.path, body.space_id, job=body.job)

    @r.post("/url", status_code=201)
    def post_url(body: UrlIn) -> dict[str, Any]:
        return add(core.ingest_url, body.url, body.space_id, job=body.job)

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

    def document(source_id: str) -> dict[str, Any]:
        from engine.sources import originals

        with database.session(layout.database) as conn:
            try:
                src = core.get_source(conn, source_id)
            except brain.NotFound as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        path = originals.resolve(layout.root, src.get("original"))
        mime = str(src.get("mime") or "")
        kind = "pdf" if mime == "application/pdf" else ("image" if mime.startswith("image/") else
                                                         ("html" if "html" in mime else "text"))
        with database.session(layout.database) as conn:
            pictures = images.list_for_source(conn, source_id)
        return {"id": source_id, "note_id": src.get("note_id"), "title": src.get("title"), "uri": src.get("uri"),
                "images": pictures,  # a web page's kept pictures (its main image first), see /image/{idx}
                "mime": mime, "kind": kind, "pages": src.get("pages") or (1 if kind == "image" else 0),
                "original_path": str(path) if path else None, "original_bytes": src.get("original_bytes"),
                # pdf/image: rendered pages; html/docx/text: the full text, read inside the app
                "mode": "pages" if kind in ("pdf", "image") else "text",
                "text_engine": src.get("text_engine"),
                "viewable": bool(path) or (kind not in ("pdf", "image") and bool(src.get("chunks")))}

    @r.get("/{source_id}/document")
    def get_document(source_id: str) -> dict[str, Any]:
        return document(source_id)

    @r.get("/progress/{job}")
    def get_progress(job: str) -> dict[str, Any]:
        from engine.sources import progress

        state = progress.get(job)
        if state is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return state

    @r.post("/{source_id}/reread")
    def post_reread(source_id: str, job: str | None = Query(None, max_length=64)) -> dict[str, Any]:
        """« Relire avec l'IA »: a scanned PDF read again by the vision model (needs the OpenAI key)."""
        if client_or_none() is None:
            raise HTTPException(status_code=409, detail="Re-reading with AI needs your OpenAI key.")
        return add(core.reread_with_ai, source_id, job=job)

    @r.get("/ocr")
    def get_ocr() -> dict[str, Any]:
        """Which local OCR this machine has, and the current mode."""
        from engine.sources import ocr

        with database.session(layout.database) as conn:
            return {"local": ocr.engine_name(), "mode": core.ocr_mode(conn)}

    @r.get("/{source_id}/text")
    def get_text(source_id: str) -> dict[str, Any]:
        """The document's full text as the Brain read it (HTML without its markup, .docx paragraphs, plain text)."""
        doc = document(source_id)
        text = ""
        if doc["original_path"] and doc["mode"] == "text":
            try:
                text = extract.from_file(Path(doc["original_path"]))[1]
            except extract.ExtractError:
                text = ""
        if not text:  # no original kept (older item): the indexed passages, in order
            with database.session(layout.database) as conn:
                rows = conn.execute("SELECT text FROM source_chunks WHERE source_id = ? ORDER BY idx", (source_id,)).fetchall()
            text = "\n\n".join(r["text"] for r in rows)
        if not text:
            raise HTTPException(status_code=404, detail="No text for this source.")
        return {"id": source_id, "title": doc["title"], "kind": doc["kind"], "text": text[:400_000],
                "truncated": len(text) > 400_000}

    @r.get("/{source_id}/page/{page}")
    def get_page(source_id: str, page: int, width: int = Query(1024, ge=64, le=4096)) -> Response:
        from engine.sources import render

        doc = document(source_id)
        if doc["kind"] == "html" and doc["images"] and page == 1:  # a web page's card shows its main image
            return get_image(source_id, 0)
        if not doc["viewable"] or doc["mode"] != "pages":
            raise HTTPException(status_code=404, detail="No page images for this source.")
        path = Path(doc["original_path"])
        if doc["kind"] == "image":
            return Response(content=path.read_bytes(), media_type=doc["mime"])
        try:
            data = render.render_page(path, page, width, layout.runtime / "pages")
        except render.RenderError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return Response(content=data, media_type="image/png", headers={"Cache-Control": "max-age=3600"})

    @r.get("/{source_id}/image/{idx}")
    def get_image(source_id: str, idx: int) -> Response:
        """One of a web page's kept pictures, as it was received."""
        with database.session(layout.database) as conn:
            found = images.path_of(conn, source_id, idx)
        if found is None:
            raise HTTPException(status_code=404, detail="No such picture for this source.")
        return Response(content=found[0].read_bytes(), media_type=found[1], headers={"Cache-Control": "max-age=3600"})

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
