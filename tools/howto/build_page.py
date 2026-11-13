"""Builds public/howto.html from tools/howto/guides.py and the captured screenshots.

Screenshots (docs/screenshots/howto/<guide>/NN.png) become WebP in public/assets/howto/<guide>/ (through Godot,
tools/web_images.gd), only when the PNG is newer. A guide whose screenshots are missing is left out of the page.
  python3 tools/howto/build_page.py
"""
from __future__ import annotations

import html
import importlib.util
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "docs" / "screenshots" / "howto"
ASSETS = ROOT / "public" / "assets" / "howto"
PAGE = ROOT / "public" / "howto.html"

spec = importlib.util.spec_from_file_location("guides", ROOT / "tools" / "howto" / "guides.py")
guides = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guides)  # type: ignore[union-attr]


def convert(ready: list[dict]) -> None:
    pairs = []
    for g in ready:
        for png in sorted((SHOTS / g["id"]).glob("*.png")):
            webp = ASSETS / g["id"] / (png.stem + ".webp")
            if not webp.exists() or webp.stat().st_mtime < png.stat().st_mtime:
                pairs.append(f"{png}={webp}@1280")
    if pairs:
        subprocess.run([os.environ.get("GODOT", "godot"), "--headless", "--path", str(ROOT), "--script",
                        "res://tools/web_images.gd", "--", *pairs], check=True, capture_output=True)


def esc(s: str) -> str:
    return html.escape(s, quote=True)


BADGE = {"real": ('<span class="badge badge-real" title="Recorded from the real model, then replayed for the '
                  'screenshots">Real answers</span>'),
         "scripted": ('<span class="badge badge-scripted" title="No model answer matters in this guide">'
                      'App only</span>')}


def section(g: dict) -> str:
    n = len(g["steps"])
    needs = "".join(f"<li>{x}</li>" for x in g["needs"])
    steps = []
    for i, (do, see) in enumerate(g["steps"], start=1):
        img = f"assets/howto/{g['id']}/{i:02d}.webp"
        steps.append(f'''          <li class="guide-step">
            <div class="guide-step-text"><p class="guide-do">{do}</p><p class="guide-see">{see}</p></div>
            <figure class="shot"><img src="{img}" alt="{esc(g['title'])}, step {i} of {n}: {esc(html.unescape(_plain(do)))}" loading="lazy" width="1280" height="800"></figure>
          </li>''')
    trouble = "".join(f"<li><b>{q}</b> {a}</li>" for q, a in g["trouble"])
    docs = " · ".join(f'<a href="{href}">{label}</a>' for label, href in g["docs"])
    return f'''      <section class="doc guide" id="{g['id']}">
        <p class="kicker">{esc(g['group'])} · {g['minutes']} min · {n} steps</p>
        <h2>{esc(g['title'])} {BADGE[g['kind']]}</h2>
        <p class="guide-goal">{g['goal']}</p>
        {f'<div class="callout"><p><b>You need</b></p><ul>{needs}</ul></div>' if needs else ''}
        <ol class="guide-steps">
{chr(10).join(steps)}
        </ol>
        {f'<h3>If it does not work</h3><ul class="guide-trouble">{trouble}</ul>' if trouble else ''}
        {f'<p class="guide-next">More: {docs}</p>' if docs else ''}
      </section>'''


def _plain(s: str) -> str:
    import re

    return re.sub(r"<[^>]+>", "", s)


GROUP_INTROS = {
    "MCP: your AI tools": '''      <section class="doc guide-group-intro" id="mcp">
        <p class="kicker">MCP</p>
        <h2>MCP: your AI tools</h2>
        <p>MCP is the open standard AI tools use to share context. Your Brain speaks it both ways: the first guide
          lets an AI tool read your Brain, the second gives your agents the tools of MCP servers.</p>
        <div class="flow" role="img" aria-label="Your AI tools (Claude Code, Codex, GitHub Copilot, Cursor, any MCP tool) read your Brain and propose; the Archivist agent decides; your agents use MCP servers (docs, code, web search, your apps).">
          <div class="flow-group"><span class="chip">Claude Code</span><span class="chip">Codex</span><span class="chip">GitHub Copilot</span><span class="chip">Cursor</span><span class="chip any">any MCP tool</span></div>
          <div class="flow-arrow both">read · propose</div>
          <div class="flow-core"><b>Your Brain</b><span>The Archivist agent decides</span><small>you approve · Go back anytime</small></div>
          <div class="flow-arrow both">search · fetch</div>
          <div class="flow-group"><span class="chip">Docs</span><span class="chip">Code</span><span class="chip">Web search</span><span class="chip">Your apps</span><span class="chip any">any MCP server</span></div>
        </div>
        <p class="flow-note">⇠ in: your AI tools read your Brain · ⇢ out: your agents use MCP servers. On 127.0.0.1 only.</p>
      </section>''',
}


def page(ready: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for g in ready:
        groups.setdefault(g["group"], []).append(g)
    nav = "\n".join(f"        <h4>{esc(name)}</h4>\n        <ul>\n" + "\n".join(
        f'          <li><a href="#{g["id"]}">{esc(g["title"])}</a></li>' for g in gs) + "\n        </ul>"
        for name, gs in groups.items())
    cards = "\n".join(
        f'''          <a class="guide-card" href="#{g['id']}"><img src="assets/howto/{g['id']}/{len(g['steps']):02d}.webp" alt="" loading="lazy" width="1280" height="800">
            <span class="guide-card-body"><b>{esc(g['title'])}</b><span>{_plain(g['goal'])}</span>
            <span class="guide-card-meta">{g['minutes']} min · {len(g['steps'])} steps · {"Real answers" if g['kind'] == 'real' else "App only"}</span></span></a>'''
        for g in ready)
    body, seen = [], set()
    for g in ready:  # a group may open with a short intro (a diagram), before its first guide
        if g["group"] in GROUP_INTROS and g["group"] not in seen:
            body.append(GROUP_INTROS[g["group"]])
        seen.add(g["group"])
        body.append(section(g))
    body = "\n\n".join(body)
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Second Brain GD How-to</title>
  <meta name="description" content="Second Brain GD how-to guides: step-by-step tutorials captured from the real app, from your first five minutes to your own agents.">
  <meta name="theme-color" content="#2b3c54">
  <link rel="icon" href="assets/logo.svg" type="image/svg+xml">
  <link rel="stylesheet" href="css/style.css?v=2026-11-07b">
</head>
<body>
  <!-- Generated by tools/howto/build_page.py from tools/howto/guides.py: edit those, not this file. -->
  <a class="skip" href="#docs-main">Skip to content</a>
  <header class="site-header">
    <nav class="nav" aria-label="Main">
      <a class="brand" href="index.html" aria-label="Second Brain GD home">
        <img src="assets/logo.svg" alt="" width="32" height="32">
        <span>SECOND BRAIN <b>GD</b></span>
      </a>
      <button class="nav-toggle" type="button" aria-expanded="false" aria-controls="nav-links">
        <span class="sr-only">Menu</span><span aria-hidden="true">☰</span>
      </button>
      <ul id="nav-links" class="nav-links">
        <li><a href="index.html#features">Features</a></li>
        <li><a href="howto.html" aria-current="page">How-to</a></li>
        <li><a href="docs.html">Docs</a></li>
        <li><a href="index.html#loops">Loops</a></li>
        <li><a href="https://github.com/sonixz/second-brain-gd" class="nav-cta" rel="noopener">GitHub</a></li>
      </ul>
    </nav>
  </header>

  <div class="docs-layout">
    <aside class="docs-nav" aria-label="Guides">
      <button class="btn docs-toc-toggle" type="button" aria-expanded="false">Guides</button>
      <input class="docs-search" type="search" placeholder="Filter the guides…" aria-label="Filter the guides">
      <nav>
{nav}
      </nav>
    </aside>

    <main id="docs-main" class="docs-main">
      <header>
        <p class="overline">How-to</p>
        <h1>Learn it by doing</h1>
        <p class="muted">Short guides, one goal each, step by step. Every screenshot is the real application,
          captured automatically from a scripted run on a demo Brain: clicks, typing and voice are simulated, the
          rest is real. Guides marked <b>Real answers</b> show what the real model said, recorded once and
          replayed. For how things work underneath, see the <a href="docs.html">Docs</a>.</p>
        <div class="guide-cards">
{cards}
        </div>
      </header>

{body}
    </main>
  </div>

  <dialog class="lightbox" id="lightbox" aria-label="Screenshot">
    <form method="dialog"><button class="reader-close" aria-label="Close">✕</button></form>
    <img alt=""><p></p>
  </dialog>

  <footer class="footer">
    <p class="container muted guide-credits">Some screenshots show web pages as browsed in the guides: the Wikipedia
      article “Heat pump” (CC BY-SA 4.0, Wikipedia contributors) and Government of Canada pages.</p>
    <div class="container footer-inner">
      <span><img src="assets/logo.svg" alt="" width="20" height="20"> Second Brain GD</span>
      <span class="muted"><a href="index.html">Home</a> · <a href="docs.html">Docs</a> · <a href="https://github.com/sonixz/second-brain-gd" rel="noopener">GitHub</a> · Local-first knowledge system · Godot + Python</span>
    </div>
  </footer>
  <script src="js/main.js?v=2026-11-07b"></script>
</body>
</html>
'''


if __name__ == "__main__":
    def captured(g: dict) -> bool:  # this run's PNGs, or the WebP already on the site (a fresh clone has no PNGs)
        n = len(g["steps"])
        return len(list((SHOTS / g["id"]).glob("*.png"))) == n or len(list((ASSETS / g["id"]).glob("*.webp"))) == n

    ready = [g for g in guides.GUIDES if captured(g) and all(d for d, _ in g["steps"])]
    convert(ready)
    PAGE.write_text(page(ready), encoding="utf-8")
    print(f"page: {len(ready)} of {len(guides.GUIDES)} guides in public/howto.html")
