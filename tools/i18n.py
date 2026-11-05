"""The app's two languages (Loop 26). English is the product's language; French is its translation.

Every text the interface shows goes through I18n.t("English text") (scripts/core/i18n.gd); i18n/fr.json maps each
English text to its French. This tool keeps the two in step:
  python3 tools/i18n.py --check     every I18n.t text has a French entry (and none is left unused): the tests run it
  python3 tools/i18n.py --scan      texts that look like interface text but are not wrapped in I18n.t (to review)
  python3 tools/i18n.py --missing   the I18n.t texts with no French yet, as JSON (to translate)
  python3 tools/i18n.py --merge     folds i18n/parts/*.json into i18n/fr.json (a conflict is reported, the first kept)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRS = [ROOT / "scenes", ROOT / "scripts"]
FR = ROOT / "i18n" / "fr.json"
STR = r'"((?:[^"\\\n]|\\.)*)"'
T_CALL = re.compile(r'I18n\.t\(\s*' + STR)
LITERAL = re.compile(STR)


def sources() -> list[Path]:
    return sorted(p for d in DIRS for p in d.rglob("*.gd"))


def unescape(s: str) -> str:
    return s.encode("utf-8").decode("unicode_escape").encode("latin-1").decode("utf-8")


def wrapped() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p in sources():
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in T_CALL.finditer(line):
                out.setdefault(unescape(m.group(1)), []).append(f"{p.relative_to(ROOT)}:{n}")
    return out


NOT_UI = re.compile(r"^(res|user|http|https)://|^/|^#[0-9a-fA-F]{3,8}$|^[a-z0-9_./:-]*$|^[A-Z0-9_]+$|^\[/?\w+[^\]]*\]$|"
                    r"^%[sdf]$|^\W*$|\.(gd|tscn|png|ogg|wav|json|svg|cfg)$|^[A-Z][a-zA-Z]+(Button|Label|Panel|Container)$")
SKIP_LINE = re.compile(r"^\s*#|push_error|push_warning|print\(|printerr|call_api\(|\.get\(|has_method|emit_signal|"
                       r"theme_type_variation|add_theme_|get_node|find_child|\bmatch\b|SbSettings\.|OS\.get_environment|"
                       r"\bcall\(|\bset\(|\bget\(|load\(|preload\(|\.connect\(|is_action|metadata")


def candidates() -> list[tuple[str, int, str]]:
    found = []
    for p in sources():
        if "/tests/" in str(p):
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if SKIP_LINE.search(line):
                continue
            code = line.split(" #")[0]
            for m in LITERAL.finditer(code):
                s = m.group(1)
                before = code[:m.start()]
                if before.rstrip().endswith("I18n.t("):
                    continue
                if NOT_UI.search(s) or len(re.findall(r"[A-Za-zÀ-ÿ]", s)) < 3:
                    continue
                if " " not in s and not s[:1].isupper():
                    continue
                found.append((str(p.relative_to(ROOT)), n, s))
    return found


def check() -> int:
    fr = json.loads(FR.read_text(encoding="utf-8")) if FR.exists() else {}
    keys = wrapped()
    missing = [k for k in keys if not fr.get(k)]
    unused = [k for k in fr if k not in keys]
    for k in missing:
        print(f"no French for {k!r} ({keys[k][0]})", file=sys.stderr)
    for k in unused:
        print(f"unused French entry {k!r}", file=sys.stderr)
    bad = [k for k in keys if fr.get(k) and k.count("%") != fr[k].count("%")]
    for k in bad:
        print(f"placeholders differ: {k!r} -> {fr[k]!r}", file=sys.stderr)
    print(f"{len(keys)} texts, {len(keys) - len(missing)} translated, {len(unused)} unused, {len(bad)} placeholder mismatches")
    return 1 if missing or unused or bad else 0


if __name__ == "__main__":
    arg = sys.argv[1:2]
    if arg == ["--check"]:
        sys.exit(check())
    elif arg == ["--scan"]:
        c = candidates()
        for f, n, s in c:
            print(f"{f}:{n}: {s}")
        print(f"{len(c)} candidates", file=sys.stderr)
    elif arg == ["--merge"]:
        fr = json.loads(FR.read_text(encoding="utf-8")) if FR.exists() else {}
        for part in sorted((ROOT / "i18n" / "parts").glob("*.json")):
            for k, v in json.loads(part.read_text(encoding="utf-8")).items():
                if k in fr and fr[k] != v:
                    print(f"conflict {k!r}: {fr[k]!r} kept, {v!r} from {part.name}", file=sys.stderr)
                    continue
                fr[k] = v
        FR.write_text(json.dumps(dict(sorted(fr.items(), key=lambda kv: kv[0].lower())), ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
        print(f"{len(fr)} entries in {FR.relative_to(ROOT)}")
    elif arg == ["--missing"]:
        fr = json.loads(FR.read_text(encoding="utf-8")) if FR.exists() else {}
        print(json.dumps({k: "" for k in wrapped() if not fr.get(k)}, ensure_ascii=False, indent=1))
    else:
        print(__doc__)
