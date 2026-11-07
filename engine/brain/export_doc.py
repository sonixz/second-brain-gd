"""Export to paper (Loop 37D): items as a clean Letter (8½ × 11) HTML page, and a PDF printed by Microsoft Edge
headless (already on Windows; a temporary profile, no window). A recipe has its own layout (picture, times,
ingredients beside the steps), a grocery list prints as boxes to tick by aisle, anything else as its text.
Nothing leaves the computer: pictures are the ones the Brain kept, embedded in the page.
"""
from __future__ import annotations

import base64
import html
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from engine import brain
from engine.brain import types

EDGE_PATHS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]

CSS = """
@page { size: letter; margin: 0.6in 0.65in; }
* { box-sizing: border-box; }
body { font-family: "Segoe UI", system-ui, -apple-system, sans-serif; color: #1d2430; font-size: 11pt; line-height: 1.45;
       margin: 0; background: #fff; }
.page { max-width: 7.2in; margin: 0 auto; }
.page + .page { break-before: page; page-break-before: always; }
h1 { font-size: 22pt; line-height: 1.15; margin: 0 0 4pt; color: #14202e; }
h2 { font-size: 13pt; margin: 14pt 0 6pt; color: #2c5b4b; border-bottom: 1px solid #d5ddd8; padding-bottom: 2pt; }
h3 { font-size: 11.5pt; margin: 10pt 0 4pt; color: #2c5b4b; }
.meta { color: #5a6573; font-size: 10pt; margin-bottom: 10pt; }
.facts { display: flex; flex-wrap: wrap; gap: 6pt 14pt; margin: 6pt 0 10pt; font-size: 10.5pt; }
.facts b { color: #2c5b4b; font-weight: 600; }
.hero { width: 100%; max-height: 3.3in; object-fit: cover; border-radius: 6pt; margin: 4pt 0 10pt; }
.cols { display: grid; grid-template-columns: 2.5in 1fr; gap: 18pt; }
ul.ing { list-style: none; padding: 0; margin: 0; }
ul.ing li { padding: 3pt 0; border-bottom: 1px dotted #d5ddd8; break-inside: avoid; }
ol.steps { padding-left: 16pt; margin: 0; }
ol.steps li { margin-bottom: 6pt; break-inside: avoid; }
ul.check { list-style: none; padding: 0; margin: 0 0 6pt; columns: 2; column-gap: 22pt; }
ul.check li { padding: 2.5pt 0 2.5pt 18pt; position: relative; break-inside: avoid; }
ul.check li::before { content: ""; position: absolute; left: 0; top: 4.5pt; width: 9pt; height: 9pt; border: 1.2px solid #44505e;
                      border-radius: 2pt; }
ul.check li.done::before { background: #44505e; }
.from { color: #7a8593; font-size: 9pt; }
.notes { margin-top: 12pt; padding: 8pt 10pt; background: #f3f6f4; border-radius: 6pt; }
.foot { margin-top: 18pt; color: #8b95a1; font-size: 8.5pt; border-top: 1px solid #e3e8e5; padding-top: 4pt; }
p { margin: 0 0 6pt; }
a { color: #2c5b4b; }
"""


class ExportError(ValueError):
    pass


def _e(s: Any) -> str:
    return html.escape(str(s or ""), quote=True)


def _inline(s: str) -> str:
    """Escaped text with **bold**, [[links]] as plain words and [text](url) as links."""
    out = _e(s)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", lambda m: m.group(2) or m.group(1), out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', out)
    return out


def markdown(text: str) -> str:
    """The light Markdown the Brain writes: headings, lists, boxes, paragraphs. Hashtag lines are left out."""
    parts: list[str] = []
    lst: str | None = None
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        m_box = re.match(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$", line)
        m_ul = re.match(r"^\s*[-*•]\s+(.*)$", line)
        m_ol = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        kind = "check" if m_box else ("ul" if m_ul else ("ol" if m_ol else None))
        if lst and kind != lst:
            parts.append("</ul>" if lst in ("ul", "check") else "</ol>")
            lst = None
        if kind and not lst:
            parts.append('<ul class="check">' if kind == "check" else ("<ul>" if kind == "ul" else "<ol>"))
            lst = kind
        if m_box:
            parts.append(f'<li class="{"done" if m_box.group(1).lower() == "x" else ""}">{_inline(m_box.group(2))}</li>')
        elif m_ul:
            parts.append(f"<li>{_inline(m_ul.group(1))}</li>")
        elif m_ol:
            parts.append(f"<li>{_inline(m_ol.group(1))}</li>")
        elif re.match(r"^#{1,3}\s", line):
            level = min(3, len(line) - len(line.lstrip("#")) + 1)
            parts.append(f"<h{level}>{_inline(line.lstrip('#').strip())}</h{level}>")
        elif re.fullmatch(r"(#[\w/-]+\s*)+", line.strip()):
            continue
        elif line.strip().endswith(":") and len(line) < 60 and not line.strip().startswith("Source"):
            parts.append(f"<h3>{_inline(line.strip()[:-1].strip())}</h3>")
        elif line.strip():
            parts.append(f"<p>{_inline(line)}</p>")
    if lst:
        parts.append("</ul>" if lst in ("ul", "check") else "</ol>")
    return "\n".join(parts)


def _picture(conn: sqlite3.Connection, note_id: str) -> str:
    """The item's main kept picture, embedded (data URI): the PDF needs no network."""
    from engine.sources import originals

    row = conn.execute("SELECT i.original, i.mime FROM source_images i JOIN sources s ON s.id = i.source_id"
                       " WHERE s.note_id = ? ORDER BY i.idx LIMIT 1", (note_id,)).fetchone()
    if not row:
        return ""
    p = originals.resolve(originals.data_root(conn), row["original"])
    if p is None or not p.exists() or p.stat().st_size > 6_000_000:
        return ""
    return f"data:{row['mime']};base64," + base64.b64encode(p.read_bytes()).decode("ascii")


def _minutes(v: Any) -> str:
    m = int(float(v))
    return f"{m // 60} h {m % 60:02d}" if m >= 60 and m % 60 else (f"{m // 60} h" if m >= 60 else f"{m} min")


def _recipe_page(conn: sqlite3.Connection, n: dict[str, Any], props: dict[str, Any], lang: str, servings: Any) -> str:
    from engine.sources import recipe

    fr = lang == "fr"
    ings = props.get("ingredients") or []
    shown_servings = props.get("servings")
    scaled = False
    if servings and props.get("servings") and float(servings) != float(props["servings"]):
        ings = recipe.scale(ings, float(servings) / float(props["servings"]))
        shown_servings, scaled = servings, True
    facts = []
    if shown_servings:
        facts.append(f"<span><b>{'Portions' if fr else 'Servings'}</b> {recipe.fmt_qty(float(shown_servings))}</span>")
    for k, lf, le in (("prep_min", "Préparation", "Prep"), ("cook_min", "Cuisson", "Cooking"), ("total_min", "Total", "Total")):
        if props.get(k):
            facts.append(f"<span><b>{lf if fr else le}</b> {_minutes(props[k])}</span>")
    if props.get("rating"):
        facts.append(f"<span><b>★</b> {str(props['rating']).replace('.', ',') if fr else props['rating']}</span>")
    pic = _picture(conn, n["id"])
    lines = [f'<h1>{_e(n["title"])}</h1>']
    if props.get("category") or props.get("cuisine"):
        lines.append(f'<div class="meta">{_e(" · ".join(x for x in (props.get("category"), props.get("cuisine")) if x))}</div>')
    if facts:
        lines.append('<div class="facts">' + "".join(facts) + "</div>")
    if pic:
        lines.append(f'<img class="hero" src="{pic}" alt="">')
    if props.get("description"):
        lines.append(f"<p>{_e(props['description'])}</p>")
    ing_html = "".join(f"<li>{_e(types.ingredient_line(i, lang) if scaled else (i.get('raw') or types.ingredient_line(i, lang)))}</li>"
                       for i in ings)
    steps_html, section, n_step = [], None, 0
    for s in props.get("steps") or []:
        n_step += 1
        if s.get("section") and s["section"] != section and len({x.get("section") for x in props["steps"]}) > 1:
            if steps_html:
                steps_html.append("</ol>")
            steps_html.append(f"<h3>{_e(s['section'])}</h3><ol class=\"steps\" start=\"{n_step}\">")  # numbers run on
        elif not steps_html:
            steps_html.append('<ol class="steps">')
        section = s.get("section")
        steps_html.append(f"<li>{_e(s['text'])}</li>")
    if steps_html:
        steps_html.append("</ol>")
    lines.append('<div class="cols"><div><h2>' + ("Ingrédients" if fr else "Ingredients") + '</h2><ul class="ing">'
                 + ing_html + "</ul></div><div><h2>" + ("Préparation" if fr else "Method") + "</h2>"
                 + "".join(steps_html) + "</div></div>")
    notes = types._kept_tail(n["body"])
    if notes:
        lines.append('<div class="notes"><h3>' + ("Mes notes" if fr else "My notes") + "</h3>" + markdown(notes) + "</div>")
    if props.get("source"):
        lines.append(f'<div class="foot">Source : {_e(props["source"])}</div>')
    return "\n".join(lines)


def _note_page(conn: sqlite3.Connection, n: dict[str, Any], lang: str) -> str:
    from engine.brain.archivist import place_label

    fr = lang == "fr"
    when = n["created_at"][:10]
    meta = f'{_e(place_label(conn, n["space_id"], lang))} · {when}'
    body = markdown(n["body"])
    pic = _picture(conn, n["id"])
    return "\n".join([f"<h1>{_e(n['title'])}</h1>", f'<div class="meta">{meta}</div>',
                      f'<img class="hero" src="{pic}" alt="">' if pic else "", body or ("<p><i>(vide)</i></p>" if fr else "")])


def page_html(conn: sqlite3.Connection, note_ids: list[str], title: str = "", lang: str = "fr",
              servings: dict[str, Any] | None = None) -> tuple[str, str]:
    """(title, the whole HTML document): one page per item, Letter size."""
    pages = []
    first = ""
    for nid in note_ids[:60]:
        n = brain.get_note(conn, nid)
        first = first or n["title"]
        p = types.get_props(conn, nid)
        if p and p["type"] == "recipe" and (p["props"].get("ingredients") or p["props"].get("steps")):
            pages.append(_recipe_page(conn, n, p["props"], lang, (servings or {}).get(nid)))
        else:
            pages.append(_note_page(conn, n, lang))
    if not pages:
        raise ExportError("nothing to export")
    doc_title = title or (first if len(pages) == 1 else (f"{first} et {len(pages) - 1} autres" if lang == "fr"
                                                         else f"{first} and {len(pages) - 1} more"))
    stamp = datetime.now().strftime("%Y-%m-%d")
    foot = ("Exporté du Second Brain le " if lang == "fr" else "Exported from Second Brain on ") + stamp
    body = "\n".join(f'<section class="page">{p}<div class="foot">{_e(foot)}</div></section>' for p in pages)
    return doc_title, (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>{_e(doc_title)}</title>'
                       f"<style>{CSS}</style></head><body>{body}</body></html>")


def find_edge() -> str | None:
    override = os.environ.get("SBGD_EDGE")
    if override:
        return override if Path(override).exists() else None
    for p in EDGE_PATHS:
        if Path(p).exists():
            return p
    return shutil.which("msedge") or shutil.which("microsoft-edge")


def print_pdf(edge: str, html_path: Path, pdf_path: Path, timeout: float = 90.0) -> None:
    """Edge headless prints the page: a temporary profile (removed after), no window, no header or footer."""
    profile = Path(tempfile.mkdtemp(prefix="sbgd-print-"))
    try:
        cmd = [edge, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
               "--disable-extensions", "--no-pdf-header-footer", f"--user-data-dir={profile}",
               f"--print-to-pdf={pdf_path}", html_path.resolve().as_uri()]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(cmd, timeout=timeout, capture_output=True, creationflags=flags, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExportError(f"Edge could not print the page ({exc.__class__.__name__})") from exc
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    if not pdf_path.exists() or pdf_path.stat().st_size < 500:
        raise ExportError("Edge did not make the PDF")


def _slug(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "-", s)[:60] or "export"


def export(conn: sqlite3.Connection, note_ids: list[str], fmt: str = "pdf", title: str = "", lang: str = "fr",
           servings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Writes <data>/exports/<title>-<date>.html, and the PDF beside it when asked and Edge can print it."""
    from engine.sources import originals

    doc_title, doc = page_html(conn, note_ids, title, lang, servings)
    out_dir = originals.data_root(conn) / "exports"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / f"{_slug(doc_title)}-{datetime.now().strftime('%Y-%m-%d-%H%M%S')}"
    html_path = base.with_suffix(".html")
    html_path.write_text(doc, encoding="utf-8")
    out: dict[str, Any] = {"title": doc_title, "html": str(html_path), "pdf": None, "pages": len(note_ids[:60]), "why": ""}
    if fmt == "pdf":
        edge = find_edge()
        if edge is None:
            out["why"] = "Microsoft Edge was not found: the page opens instead (Ctrl+P → Save as PDF)"
        else:
            try:
                pdf = base.with_suffix(".pdf")
                print_pdf(edge, html_path, pdf)
                out["pdf"] = str(pdf)
            except ExportError as exc:
                out["why"] = str(exc) + ": the page opens instead (Ctrl+P → Save as PDF)"
    return out
