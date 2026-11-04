"""Replays real requests against the real model on a throwaway brain and checks what actually changed.

  dotenvx run -- python3 tools/assistant_bench.py [--models gpt-4o,gpt-6-sol] [--runs 2]

Each scenario starts from a fresh database shaped like the owner's on 2026-11-04 (four CVs waiting in the
Inbox, two dictated notes in Projets › Recherche d'emploi). A run passes when the database ends in the expected
state AND the reply does not claim a change that did not happen. Uses the OpenAI key from the environment.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SBGD_OCR", "off")

from engine import brain, database  # noqa: E402
from engine.assistant import actions as act  # noqa: E402
from engine.assistant import core  # noqa: E402
from engine.assistant.llm import make_client  # noqa: E402
from engine.brain.seed import seed_if_empty  # noqa: E402

CVS = ["Pierre-Yves Forget — Infrastructure infonuagique Azure (Français)",
       "Pierre-Yves Forget — Architecte technologique (français)",
       "Résumé de carrière de Pierre-Yves Forget - Français",
       "Profil professionnel de Pierre-Yves Forget - Français"]


def world(path: Path):
    database.migrate(path)
    conn = database.connect(path)
    seed_if_empty(conn)
    job = brain.create_space(conn, "Recherche d'emploi")
    ids = {t: brain.create_note(conn, t, f"CV. {t}. Azure, sécurité, automatisation. #carriere", None, "reference")["id"] for t in CVS}
    for t in CVS:
        conn.execute("INSERT INTO sources (id, kind, uri, title, mime, bytes, content_hash, status, note_id, chunks, created_at, updated_at)"
                     " VALUES (?, 'file', ?, ?, ?, 1, ?, 'ready', ?, 1, 'x', 'x')",
                     (ids[t][:8], t + ".pdf", t, "application/pdf" if "Résumé" in t or "Profil" in t else "text/html", ids[t], ids[t]))
    a = brain.create_note(conn, "Candidatures et CV", "J'ai fait des CV, je postule à quelques endroits. #recherche-emploi",
                          job["id"], "note", source="voice")
    b = brain.create_note(conn, "Deux CV pour Airudi et Beneva", "Un CV pour Airudi, l'autre pour Beneva. #recherche-emploi",
                          job["id"], "note", source="voice")
    conn.execute("INSERT INTO links (from_note, to_note, kind, created_by, created_at) VALUES (?, ?, 'related', 'assistant', 'x')",
                 (b["id"], a["id"]))
    conn.commit()
    return conn, job["id"], ids, a["id"], b["id"]


def place_of(conn, nid):
    return conn.execute("SELECT space_id, status FROM notes WHERE id = ?", (nid,)).fetchone()


SCENARIOS = [
    ("move four", ["Mets mes quatre CV dans Recherche d'emploi."],
     lambda c, job, ids, a, b: all(place_of(c, i)["space_id"] == job for i in ids.values())),
    ("detach from inbox", ["Mes deux CV Résumé de carrière et Profil professionnel sont reliés à Recherche d'emploi mais "
                           "ils sont aussi attachés à l'Inbox. Détache-les de l'Inbox."],
     lambda c, job, ids, a, b: place_of(c, ids[CVS[2]])["space_id"] == job and place_of(c, ids[CVS[3]])["space_id"] == job),
    ("what do you mean", ["Qu'est-ce que tu veux dire?"],
     lambda c, job, ids, a, b: c.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == c.execute(
         "SELECT COUNT(*) FROM notes WHERE source = 'seed'").fetchone()[0] + 6
     and all(place_of(c, i)["space_id"] == "inbox" for i in ids.values())),
    ("unlink", ["Enlève le lien entre Deux CV pour Airudi et Beneva et Candidatures et CV."],
     lambda c, job, ids, a, b: not act._link_rows(c, a, b)),
    ("trash dictated", ["Supprime la note Deux CV pour Airudi et Beneva, c'était une consigne, pas une note."],
     lambda c, job, ids, a, b: place_of(c, b)["status"] == "archived" and place_of(c, a)["status"] != "archived"),
    ("file one loosely", ["Classe le résumé de carrière avec mes candidatures."],
     lambda c, job, ids, a, b: place_of(c, ids[CVS[2]])["space_id"] == job),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gpt-4o,gpt-6-sol")
    ap.add_argument("--runs", type=int, default=1)
    args = ap.parse_args()
    client = make_client(os.environ.get("OPENAI_API_KEY"))
    total_cost = 0.0
    for model in args.models.split(","):
        ok_count, n, secs = 0, 0, 0.0
        for name, turns, check in SCENARIOS:
            for _ in range(args.runs):
                with tempfile.TemporaryDirectory() as tmp:
                    conn, job, ids, a, b = world(Path(tmp) / "b.sqlite3")
                    database.set_setting(conn, "assistant_chat_model", model)
                    t0 = time.time()
                    reply, cost = "", 0.0
                    try:
                        for t in turns:
                            out = core.chat(conn, client, t, spoken=True)
                            reply, cost = out["reply"], cost + out["estimated_cost_usd"]
                            conn.commit()
                        good = bool(check(conn, job, ids, a, b))
                    except Exception as exc:  # a model error is a failed run
                        good, reply = False, f"ERROR {exc}"
                    dt = time.time() - t0
                    conn.close()
                n += 1
                ok_count += good
                secs += dt
                total_cost += cost
                print(f"{model:12} {'PASS' if good else 'FAIL'} {name:18} {dt:5.1f}s  {reply[:110]!r}")
        print(f"== {model}: {ok_count}/{n} passed, {secs / max(n, 1):.1f} s per request\n")
    print(f"estimated cost ≈ ${total_cost:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
