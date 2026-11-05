"""Browser extension routes.

App side (local API token): start pairing, see status, revoke.
Extension side (its own browser token): pair with the code, keep a WebSocket for commands, send pages.
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets as pysecrets
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from engine import brain, database
from engine.assistant.llm import make_client
from engine.browser import pairing
from engine.browser.hub import HUB
from engine.events import utc_now
from engine.paths import Layout
from engine.voice import secrets

PING_S = 20.0  # keeps the extension's service worker awake and detects a dead link


class PairIn(BaseModel):
    code: str = Field(min_length=4, max_length=20)
    browser: str = Field(default="", max_length=120)


class PictureIn(BaseModel):
    """One of the few pictures the extension chose on the page, with its bytes (base64), as the browser had it."""
    url: str = Field(default="", max_length=4000)
    alt: str = Field(default="", max_length=400)
    caption: str = Field(default="", max_length=600)
    data: str = Field(default="", max_length=11_200_000)  # 8 MB once decoded


class ImageIn(BaseModel):
    """A picture the user chose (right-click → Send this image to the Brain)."""
    page_url: str = Field(min_length=8, max_length=4000)
    page_title: str = Field(default="", max_length=400)
    image_url: str = Field(default="", max_length=4000)
    alt: str = Field(default="", max_length=400)
    data: str = Field(default="", max_length=11_200_000)  # empty: the engine downloads image_url itself
    place: str = Field(default="", max_length=120)
    lang: str = Field(default="", max_length=20)


class PageIn(BaseModel):
    url: str = Field(min_length=8, max_length=4000)
    title: str = Field(default="", max_length=400)
    html: str = Field(default="", max_length=3_000_000)
    text: str = Field(default="", max_length=1_000_000)
    selection: str = Field(default="", max_length=20_000)
    selection_only: bool = False
    place: str = Field(default="", max_length=120)
    images: list[PictureIn] = Field(default_factory=list, max_length=8)
    lang: str = Field(default="", max_length=20)  # the page's <html lang>: pictures are described in it


def _bytes(b64: str) -> bytes:
    import base64
    import binascii

    try:
        return base64.b64decode(b64.split(",", 1)[-1] if b64.startswith("data:") else b64, validate=False)
    except (binascii.Error, ValueError):
        return b""


def _pictures(given: list[PictureIn]) -> list[dict[str, Any]]:
    """The page's chosen pictures with their bytes; the ones the extension could not read are downloaded here."""
    from engine.sources import images

    out = []
    for p in given[:images.MAX_PER_PAGE]:
        data = _bytes(p.data) if p.data else b""
        if not data and p.url.startswith(("http://", "https://")):
            try:
                data = images.download(p.url)
            except Exception:
                continue
        if data:
            out.append({"url": p.url, "alt": p.alt, "caption": p.caption, "data": data})
    return out


def needs_download(page: PageIn) -> bool:
    """Nothing readable came from the tab (a PDF in the browser's viewer, a protected page): the engine downloads it.
    A PDF tab still has a little html (the viewer's <embed>) but no text, in its html or its innerText."""
    if page.text.strip():
        return False
    visible = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>|<[^>]+>", " ", page.html)
    return len(visible.split()) < 20


def capture(layout: Layout, page: PageIn) -> dict[str, Any]:
    """Adds a page (or the selected passage) sent by the browser, then lets the archivist file it."""
    from engine.assistant.actions import resolve_place
    from engine.brain import archivist
    from engine.sources import core as sources

    key, _ = secrets.get(layout, "openai")
    try:
        client = make_client(key)
    except PermissionError:
        client = None
    with database.session(layout.database) as conn:
        space_id = None
        kept_images = 0
        if page.place:
            p = resolve_place(conn, page.place)
            space_id = p["id"] if p else None
        if page.selection_only and page.selection.strip():
            note = brain.create_note(conn, (page.title or page.selection)[:72].strip() or "Extrait",
                                     page.selection.strip() + f"\n\nSource: {page.url}", space_id, kind="reference", source="import")
            archivist.save_meta(conn, note["id"], origin="url", origin_uri=page.url, item_type="quote")
            note_id, duplicate, title = note["id"], False, note["title"]
        elif needs_download(page):  # a PDF or a protected tab: download it instead
            src = sources.ingest_url(conn, client, page.url, space_id)
            note_id, duplicate, title = src.get("note_id"), bool(src.get("duplicate")), src.get("title", "")
            kept_images = int((src.get("images") or {}).get("kept", 0))
        else:
            pictures = _pictures(page.images)
            src = sources.ingest_page(conn, client, page.url, page.title, page.html, page.text, space_id, pictures, page.lang)
            note_id, duplicate, title = src.get("note_id"), bool(src.get("duplicate")), src.get("title", "")
            kept_images = int((src.get("images") or {}).get("kept", 0))
    return _finish(layout, client, note_id, duplicate, title, space_id, page.url, kept_images)


def capture_image(layout: Layout, pic: ImageIn) -> dict[str, Any]:
    """A picture the user chose on a page: an item of its own, filed by the archivist like anything else."""
    from engine.assistant.actions import resolve_place
    from engine.sources import core as sources
    from engine.sources import images

    key, _ = secrets.get(layout, "openai")
    try:
        client = make_client(key)
    except PermissionError:
        client = None
    data = _bytes(pic.data) if pic.data else b""
    if not data:  # the extension could not read it (no permission for that site): the engine downloads it
        try:
            data = images.download(pic.image_url)
        except OSError as exc:
            from engine.sources.extract import ExtractError

            raise ExtractError(f"cannot download this picture: {exc}") from exc
    with database.session(layout.database) as conn:
        space_id = None
        if pic.place:
            p = resolve_place(conn, pic.place)
            space_id = p["id"] if p else None
        src = sources.ingest_image(conn, client, data, pic.page_url, pic.page_title, pic.alt, pic.image_url, space_id, pic.lang)
    return _finish(layout, client, src.get("note_id"), bool(src.get("duplicate")), src.get("title", ""), space_id,
                   pic.image_url or pic.page_url)


def _finish(layout: Layout, client: Any, note_id: str | None, duplicate: bool, title: str, space_id: str | None,
            url: str, kept_images: int = 0) -> dict[str, Any]:
    from engine.assistant import core
    from engine.brain import archivist

    receipt = ""
    if note_id and not duplicate and client is not None and space_id is None:
        with database.session(layout.database) as conn:
            core._CLIENT["c"] = client
            receipt = archivist.file_item(conn, client, note_id, float(core.settings(conn)["assistant_min_confidence"])).get("receipt") or ""
    with database.session(layout.database) as conn:
        place = archivist.place_label(conn, conn.execute("SELECT space_id FROM notes WHERE id = ?", (note_id,)).fetchone()["space_id"],
                                      core.ui_language(conn)) if note_id else ""  # shown in the app and the popup
        fr = core.ui_language(conn) == "fr"
        database.record_event(conn, {"timestamp": utc_now(), "component": "browser", "stage": "capture", "status": "ok",
                                     "message": f"From the browser: {title}" + (" (already in the Brain)" if duplicate else ""),
                                     "details": {"url": url[:300]}})
    if fr:
        receipt = receipt or ("Déjà dans ton Brain." if duplicate else f"Ajouté à {place or 'l’Inbox'}.")
        if kept_images:
            receipt += f" {kept_images} image{'s' if kept_images > 1 else ''} de la page gardée{'s' if kept_images > 1 else ''} avec."
    else:
        receipt = receipt or ("Already in your Brain." if duplicate else f"Added to {place or 'the Inbox'}.")
        if kept_images:
            receipt += f" {kept_images} image{'s' if kept_images > 1 else ''} from the page kept with it."
    out = {"note_id": note_id, "title": title, "duplicate": duplicate, "place": place, "images": kept_images,
           "receipt": receipt}
    if not duplicate:
        HUB.note_added({"note_id": note_id, "title": title, "place": place})
    return out


def make_router(layout: Layout, auth: Callable[..., None], port: int) -> APIRouter:
    r = APIRouter(prefix="/browser")

    def browser_auth(request: Request) -> dict[str, Any]:
        header = request.headers.get("authorization", "")
        scheme, _, given = header.partition(" ")
        with database.session(layout.database) as conn:
            t = pairing.verify(conn, given.strip()) if scheme.lower() == "bearer" else None
        if t is None:
            raise HTTPException(status_code=401, detail="this browser is not paired (or was unpaired): pair it again from the app")
        return t

    # ---- app side
    @r.post("/pair/start", dependencies=[Depends(auth)])
    def pair_start() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            return {**pairing.start(conn), "port": port}

    @r.get("/status", dependencies=[Depends(auth)])
    def status() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            browsers = pairing.paired(conn)
        return {"paired": browsers, "connected": HUB.connected(), "browser": HUB.info.get("browser", ""),
                "extension_version": HUB.info.get("version", ""), "can_read_tabs": bool(HUB.info.get("can_read_tabs")),
                "rev": HUB.rev, "last_added": HUB.last_added, "port": port}

    @r.delete("/pair", dependencies=[Depends(auth)])
    def unpair() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            n = pairing.revoke_all(conn)
        ws = HUB._ws
        if ws is not None and HUB._loop is not None:
            asyncio.run_coroutine_threadsafe(ws.close(code=4401), HUB._loop)
        return {"revoked": n}

    # ---- extension side
    @r.post("/pair")
    def pair(body: PairIn) -> dict[str, Any]:
        with database.session(layout.database) as conn:
            try:
                token = pairing.complete(conn, body.code, body.browser)
            except pairing.PairingError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
        return {"token": token}

    @r.post("/capture")
    def post_capture(body: PageIn, _t: dict = Depends(browser_auth)) -> dict[str, Any]:
        from engine.sources.extract import ExtractError

        try:
            return capture(layout, body)
        except ExtractError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.post("/image")
    def post_image(body: ImageIn, _t: dict = Depends(browser_auth)) -> dict[str, Any]:
        from engine.sources.extract import ExtractError

        try:
            return capture_image(layout, body)
        except ExtractError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @r.websocket("/ws")
    async def ws_link(ws: WebSocket) -> None:
        await ws.accept()
        try:
            hello = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=10))
        except Exception:
            await ws.close(code=4400)
            return
        with database.session(layout.database) as conn:
            t = pairing.verify(conn, str(hello.get("token") or "")) if hello.get("type") == "hello" else None
        if t is None:
            await ws.send_text(json.dumps({"type": "error", "error": "not paired"}))
            await ws.close(code=4401)
            return
        HUB.attach(ws, asyncio.get_running_loop(), {"browser": str(hello.get("browser") or t.get("browser") or "")[:80],
                                                     "version": str(hello.get("version") or "")[:20],
                                                     "can_read_tabs": bool(hello.get("can_read_tabs"))})
        await ws.send_text(json.dumps({"type": "welcome", "port": port}))

        async def pinger() -> None:
            while True:
                await asyncio.sleep(PING_S)
                await ws.send_text(json.dumps({"type": "ping"}))

        ping_task = asyncio.create_task(pinger())
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                kind = msg.get("type")
                if kind == "result":
                    HUB.resolve(str(msg.get("id")), bool(msg.get("ok")), msg.get("data") if msg.get("ok") else msg.get("error"))
                elif kind == "tabs":  # the tabs the Brain opened, kept in sync by the extension
                    HUB.opened = {str(k): v for k, v in (msg.get("opened") or {}).items()}
                elif kind == "permissions":
                    HUB.info["can_read_tabs"] = bool(msg.get("can_read_tabs"))
        except (WebSocketDisconnect, RuntimeError, ValueError):
            pass
        finally:
            ping_task.cancel()
            HUB.detach(ws)

    return r
