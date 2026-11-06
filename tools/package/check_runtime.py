"""Checks a built runtime for real (Loop 28): run with any Python, pointing at the app's own interpreter.

  python3 tools/package/check_runtime.py dist/runtime-linux/python/bin/python3
  python3 tools/package/check_runtime.py dist/runtime-windows/python/python.exe     (on Windows, or from WSL)

1. SQLite inside it has FTS5 (passages search) and WAL (the engine writes while the app reads).
2. The whole setup runs with it in a throwaway data folder: no virtual environment, no download, every
   migration, the engine starts and answers /health; then it is stopped and the folder removed.
Exit code 0 only when everything passed. The agent room is left off (it is on demand anyway).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQLITE_CHECK = (
    "import sqlite3,json,sys;c=sqlite3.connect(sys.argv[1]);"
    "c.execute('PRAGMA journal_mode=WAL');"
    "c.execute('CREATE VIRTUAL TABLE t USING fts5(x)');c.execute(\"INSERT INTO t VALUES ('heat pump quote')\");"
    "n=c.execute(\"SELECT count(*) FROM t WHERE t MATCH 'pump'\").fetchone()[0];"
    "print(json.dumps({'sqlite':sqlite3.sqlite_version,'wal':c.execute('PRAGMA journal_mode').fetchone()[0],'fts5':n==1}))"
)


def win(path: Path) -> str:
    """A path the interpreter understands (a Windows python.exe run from WSL needs C:\\ paths)."""
    if str(PY).endswith(".exe") and sys.platform != "win32":
        return subprocess.run(["wslpath", "-w", str(path)], capture_output=True, text=True).stdout.strip()
    return str(path)


def main() -> int:
    ok = True
    with tempfile.TemporaryDirectory(prefix="sbgd-check-", dir=os.environ.get("SBGD_CHECK_TMP")) as tmp:
        home = Path(tmp) / "home"
        out = subprocess.run([str(PY), "-c", SQLITE_CHECK, win(Path(tmp) / "probe.sqlite3")], capture_output=True, text=True)
        sq = json.loads(out.stdout.strip() or "{}") if out.returncode == 0 else {}
        print("sqlite:", sq or out.stderr[-400:])
        ok &= bool(sq.get("fts5")) and sq.get("wal") == "wal"
        events = Path(tmp) / "events.jsonl"
        env = dict(os.environ, SBGD_AGENTS="off", SBGD_KEYRING_SERVICE="SecondBrainGD-check")
        env.pop("OPENAI_API_KEY", None)
        if str(PY).endswith(".exe") and sys.platform != "win32":
            env["WSLENV"] = "SBGD_AGENTS:SBGD_KEYRING_SERVICE"
        started = time.monotonic()
        res = subprocess.run([str(PY), win(ROOT / "engine" / "bootstrap.py"), "setup", "--quiet", "--data-dir", win(home),
                              "--events", win(events)], capture_output=True, text=True, env=env, timeout=600)
        lines = [json.loads(l) for l in events.read_text(encoding="utf-8").splitlines()] if events.exists() else []
        for e in lines:
            if e.get("stage") in ("check", "done", "create", "verify", "migrate") or e.get("status") in ("error", "ok"):
                print(f"  {e['component']:<12} {e['status']:<8} {e['message'][:110]}")
        final = lines[-1] if lines else {}
        venv = (home / ".venv").exists()
        print(f"setup: exit {res.returncode}, {time.monotonic() - started:.1f} s, final {final.get('status')}, venv created: {venv}")
        ok &= res.returncode == 0 and final.get("status") == "ok" and not venv
        health = [e for e in lines if e["component"] == "health" and e["status"] == "ok"]
        ok &= bool(health)
        subprocess.run([str(PY), win(ROOT / "engine" / "bootstrap.py"), "stop", "--data-dir", win(home)],
                       capture_output=True, text=True, env=env, timeout=60)
        time.sleep(1.0)
    print("RUNTIME OK" if ok else "RUNTIME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    PY = Path(sys.argv[1]).resolve()
    sys.exit(main())
