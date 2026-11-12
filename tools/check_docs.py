"""Checks that the website and the repository's documents hold together (documentation is part of the work: see
AGENTS.md, owner 2026-11-11).

  - every internal link and picture of public/*.html points to a file of the repository, and to an anchor that
    exists on the page it names;
  - every relative link of the Markdown documents points to a file of the repository (the plans of past loops,
    docs/plans/plan-*.md, are left as they were written);
  - every How-to guide of tools/howto/guides.py is on public/howto.html (a guide left out was never captured);
  - the home page's « Show all N loops » button says how many loop cards there are.

It cannot tell whether a sentence is still true: that part stays with whoever makes the change.

  python3 tools/check_docs.py        prints what is broken; exit code 1 when something is (the tests run it)
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
OUTSIDE = re.compile(r"^(https?:|mailto:|data:|javascript:|//)")


def repository_files() -> set[str] | None:
    """The files git knows or would add: an ignored file on this disk does not exist for a visitor."""
    try:
        res = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return {p for p in res.stdout.decode("utf-8", "replace").split("\0") if p}


def exists(path: Path, known: set[str] | None) -> bool:
    if not path.exists():
        return False
    if known is None or path.is_dir():
        return True
    try:
        return path.resolve().relative_to(ROOT).as_posix() in known
    except ValueError:
        return False


def check_site(known: set[str] | None) -> list[str]:
    pages = sorted(PUBLIC.glob("*.html"))
    text = {p.name: p.read_text(encoding="utf-8") for p in pages}
    anchors = {name: set(re.findall(r'\bid="([^"]+)"', t)) for name, t in text.items()}
    bad = set()
    for name, t in text.items():
        for url in re.findall(r'\b(?:href|src)="([^"]+)"', t):
            if OUTSIDE.match(url):
                continue
            path, _, anchor = url.partition("#")
            path = path.split("?")[0]
            target = name if path == "" else path
            if not exists(PUBLIC / target, known):
                bad.add(f"public/{name}: {url} (no such file)")
            elif anchor and target in anchors and anchor not in anchors[target]:
                bad.add(f"public/{name}: {url} (no such anchor)")
    return sorted(bad)


def check_markdown(known: set[str] | None) -> list[str]:
    files = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")]
    bad = set()
    for f in sorted(files):
        rel = f.relative_to(ROOT).as_posix()
        if (known is not None and rel not in known) or re.match(r"docs/plans/plan-.*\.md$", rel):
            continue
        for url in re.findall(r"\]\(([^)\s]+)\)", f.read_text(encoding="utf-8")):
            path = url.split("#")[0].split("?")[0]
            if OUTSIDE.match(url) or not path:
                continue
            if not exists(f.parent / path, known):
                bad.add(f"{rel}: {url} (no such file)")
    return sorted(bad)


def check_guides() -> list[str]:
    spec = importlib.util.spec_from_file_location("guides", ROOT / "tools" / "howto" / "guides.py")
    guides = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guides)  # type: ignore[union-attr]
    page = (PUBLIC / "howto.html").read_text(encoding="utf-8")
    on_page = set(re.findall(r'<section class="doc guide" id="([^"]+)"', page))
    return [f"How-to: the guide « {g['id']} » is in tools/howto/guides.py and not on public/howto.html "
            f"(capture it: tools/howto.sh {g['id']})" for g in guides.GUIDES if g["id"] not in on_page]


def check_home() -> list[str]:
    page = (PUBLIC / "index.html").read_text(encoding="utf-8")
    cards = len(re.findall(r'<article class="loop-card\b', page))
    said = re.search(r'class="btn loops-more">Show all (\d+) loops<', page)
    if said is None:
        return ["public/index.html: the « Show all N loops » button was not found"]
    if int(said.group(1)) != cards:
        return [f"public/index.html: the button says {said.group(1)} loops, the page has {cards} loop cards"]
    return []


def main() -> int:
    known = repository_files()
    bad = check_site(known) + check_markdown(known) + check_guides() + check_home()
    for line in bad:
        print(line)
    print(f"{len(bad)} problem(s)" if bad else "links, pictures, guides and counts hold together")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
