"""« Envoyer au Brain » from the web browser (Loop 9).

A bookmarklet opens http://127.0.0.1:<port>/capture?key=…&url=…&title=…[&text=…] in a small
window. It is a top-level navigation, not a fetch, so browsers allow it toward the local
engine (they often block page scripts from calling 127.0.0.1). The page carries a dedicated
capture key (not the session token, not an API key): it can only add one page or one
selection to the Brain. The archivist files it and the window shows the receipt.
"""
from __future__ import annotations

import html
import secrets as pysecrets
from typing import Any, Callable

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse

from engine import brain, database
from engine.assistant.llm import make_client
from engine.paths import Layout
from engine.voice import secrets

PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8"><title>Second Brain</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>
body{{margin:0;font:15px/1.45 system-ui,sans-serif;background:#2b3c54;color:#f1f6fc;display:flex;min-height:100vh;
align-items:center;justify-content:center}}main{{max-width:400px;padding:22px}}h1{{font-size:18px;margin:0 0 8px;color:{color}}}
p{{margin:6px 0;color:#d9e4f0}}small{{color:#b5c6da}}button{{margin-top:14px;background:#a9d4ff;color:#13233a;border:0;
border-radius:8px;padding:8px 14px;font-weight:600;cursor:pointer}}</style></head><body><main>
<h1>{headline}</h1><p>{receipt}</p><small>{detail}</small><br><button onclick="window.close()">Fermer</button>
</main><script>setTimeout(function(){{window.close()}},{close_ms});</script></body></html>"""


def get_key(conn) -> str:
    key = database.get_setting(conn, "capture_key")
    if not key:
        key = pysecrets.token_urlsafe(18)
        database.set_setting(conn, "capture_key", key)
    return key


def bookmarklet(port: int, key: str) -> str:
    return ("javascript:(()=>{const s=String(getSelection()).slice(0,6000);window.open('http://127.0.0.1:%d/capture?key=%s"
            "&url='+encodeURIComponent(location.href)+'&title='+encodeURIComponent(document.title)+(s?'&text='"
            "+encodeURIComponent(s):''),'sbgd','width=480,height=340')})()" % (port, key))


def _page(ok: bool, headline: str, receipt: str, detail: str = "") -> HTMLResponse:
    return HTMLResponse(PAGE.format(color="#a9f0c7" if ok else "#ffd27a", headline=html.escape(headline),
                                    receipt=html.escape(receipt), detail=html.escape(detail),
                                    close_ms=4000 if ok else 20000), status_code=200 if ok else 400)


def make_router(layout: Layout, auth: Callable[..., None], port: int) -> APIRouter:
    r = APIRouter()

    @r.get("/brain/capture-link", dependencies=[Depends(auth)])
    def capture_link() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            key = get_key(conn)
        return {"port": port, "bookmarklet": bookmarklet(port, key)}

    @r.post("/brain/capture-link/rotate", dependencies=[Depends(auth)])
    def rotate() -> dict[str, Any]:
        with database.session(layout.database) as conn:
            database.set_setting(conn, "capture_key", None)
            key = get_key(conn)
        return {"port": port, "bookmarklet": bookmarklet(port, key)}

    @r.get("/capture", response_class=HTMLResponse)
    def capture(key: str = Query(max_length=100), url: str = Query(min_length=8, max_length=2000),
                title: str = Query("", max_length=400), text: str = Query("", max_length=8000)) -> HTMLResponse:
        from engine.assistant import core
        from engine.brain import archivist
        from engine.sources import core as sources
        from engine.sources.extract import ExtractError

        with database.session(layout.database) as conn:
            if not pysecrets.compare_digest(key, get_key(conn)):
                return _page(False, "Lien de capture invalide", "Recopie le favori « Envoyer au Brain » depuis l'app "
                             "(Captures → Send from browser).")
        if not url.startswith(("http://", "https://")):
            return _page(False, "Adresse non prise en charge", url[:120])
        api_key, _ = secrets.get(layout, "openai")
        try:
            client = make_client(api_key)
        except PermissionError:
            client = None
        try:
            with database.session(layout.database) as conn:
                if text.strip():  # a selection: keep exactly what was highlighted, with its page
                    note = brain.create_note(conn, (title or text)[:72].strip() or "Extrait", text.strip()
                                             + f"\n\nSource: {url}", None, kind="reference", source="import")
                    archivist.save_meta(conn, note["id"], origin="url", origin_uri=url, item_type="quote")
                    note_id = note["id"]
                else:
                    src = sources.ingest_url(conn, client, url)
                    note_id = src.get("note_id")
                    if src.get("duplicate"):
                        return _page(True, "Déjà dans ton Brain", f"« {src.get('title', '')} »")
            if client is None or not note_id:
                return _page(True, "Ajouté à l'Inbox", f"« {title or url} »", "Ajoute ta clé OpenAI pour le classement automatique.")
            with database.session(layout.database) as conn:
                core._CLIENT["c"] = client
                out = archivist.file_item(conn, client, note_id, float(core.settings(conn)["assistant_min_confidence"]))
            return _page(True, "Ajouté à ton Brain ✓", out.get("receipt") or "Classé.")
        except ExtractError as exc:
            return _page(False, "Page illisible", str(exc)[:200])
        except Exception as exc:
            return _page(False, "Impossible d'ajouter cette page", f"{exc.__class__.__name__}: {str(exc)[:160]}")

    return r
