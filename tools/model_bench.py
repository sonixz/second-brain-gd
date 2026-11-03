"""Compares chat models on the assistant's real jobs, with the real API.

    dotenvx run -- python3 tools/model_bench.py [--classify a,b] [--chat a,b]

Builds a throwaway demo brain (areas, projects, groceries), then measures
filing accuracy on 10 French captures with known answers, and a tool-using
chat turn ("add a task with a date"). Prints accuracy, latency and tokens.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import brain, database  # noqa: E402
from engine.assistant import core  # noqa: E402
from engine.assistant.llm import make_client  # noqa: E402
from engine.brain import structure  # noqa: E402
from engine.brain.seed import seed_all  # noqa: E402

CAPTURES = [
    ("faut que je rappelle le fournisseur d'Atlas pour la migration", "Client Atlas"),
    ("acheter du papier de toilette pis du savon", "checklist:Épicerie"),
    ("idée: un mode focus avec des sons de pluie dans l'app", "Second Brain GD"),
    ("prendre rendez-vous chez le dentiste", "Santé"),
    ("Léa veut un gâteau au chocolat pour sa fête", "Fête de Léa"),
    ("réflexion: on devrait mesurer la satisfaction client chaque trimestre", "Vision au travail"),
    ("dormir plus tôt cette semaine, j'suis brûlé", "Santé"),
    ("réparer la poignée de la porte d'en arrière", "Maison"),
    ("le client Atlas veut repousser la démo à jeudi", "Client Atlas"),
    ("lire Thinking in Systems pour mieux penser la stratégie", "Vision au travail"),
]


def demo(db: Path) -> None:
    database.migrate(db)
    with database.session(db) as conn:
        seed_all(conn)
        areas = {a["name"]: a["id"] for a in structure.structure(conn)["areas"]}
        structure.create_project(conn, "Client Atlas", areas["Vision au travail"], "Signer le mandat Q1")
        structure.create_project(conn, "Second Brain GD", areas["Vision au travail"], "Assistant quotidien utile")
        structure.create_project(conn, "Fête de Léa", areas["Famille"], "Une fête simple et joyeuse")


def bench_classify(key: str, models: list[str]) -> None:
    print("\nFILING (10 French captures)")
    print(f"{'model':<14} {'correct':>8} {'avg s':>6} {'tokens':>8}  misses")
    for model in models:
        db = Path(tempfile.mkdtemp()) / "b.db"
        demo(db)
        ok, secs, toks, misses = 0, 0.0, 0, []
        with database.session(db) as conn:
            core.database.set_setting(conn, "assistant_classify_model", model)
            client = make_client(key)
            for text, expected in CAPTURES:
                n = brain.create_note(conn, text)
                conn.commit()
                t0 = time.monotonic()
                try:
                    r = core.classify(conn, client, n["id"])
                except Exception as exc:  # report and keep going
                    misses.append(f"{text[:25]}… ERROR {exc}")
                    continue
                secs += time.monotonic() - t0
                conn.commit()
                p = r.get("proposal", {})
                got = f"checklist:{p.get('checklist_name')}" if p.get("target") == "checklist" else p.get("space_name")
                if not r.get("applied"):
                    got = f"(left in inbox; guessed {got})"
                if got == expected:
                    ok += 1
                else:
                    misses.append(f"« {text[:28]}… » → {got} (expected {expected})")
            row = conn.execute("SELECT details FROM system_events WHERE component='assistant' AND stage='classify'").fetchall()
            toks = sum(json.loads(r["details"])["usage"].get("total_tokens", 0) for r in row)
        print(f"{model:<14} {ok:>5}/10 {secs / 10:>6.2f} {toks:>8}  " + ("; ".join(misses) or "—"))


def bench_chat(key: str, models: list[str]) -> None:
    print("\nCHAT WITH TOOLS (« Ajoute une tâche: envoyer la facture Atlas avant vendredi le 13 novembre 2026 »)")
    for model in models:
        db = Path(tempfile.mkdtemp()) / "c.db"
        demo(db)
        with database.session(db) as conn:
            core.database.set_setting(conn, "assistant_chat_model", model)
            client = make_client(key)
            t0 = time.monotonic()
            try:
                out = core.chat(conn, client, "Ajoute une tâche: envoyer la facture Atlas avant vendredi le 13 novembre 2026.")
            except Exception as exc:
                print(f"  {model}: ERROR {exc}")
                continue
            dt = time.monotonic() - t0
            conn.commit()
            tasks = [(t["title"], t["space_name"], t["due_date"]) for t in structure.tasks(conn)]
            right = any(s == "Client Atlas" and d == "2026-11-13" for _, s, d in tasks)
            print(f"  {model:<14} {dt:5.1f}s  correct={right}  tasks={tasks}\n                 « {out['reply'][:160]} »")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--classify", default="gpt-4o-mini,gpt-4o,gpt-6-luna,gpt-6-sol")
    ap.add_argument("--chat", default="gpt-4o,gpt-6-luna,gpt-6-sol")
    a = ap.parse_args()
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        sys.exit("OPENAI_API_KEY missing (run through dotenvx)")
    bench_classify(key, [m for m in a.classify.split(",") if m])
    bench_chat(key, [m for m in a.chat.split(",") if m])
