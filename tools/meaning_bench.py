"""Measures note-to-note similarity with the real embeddings model, to set RELATED_SCORE.

    dotenvx run -- python3 tools/meaning_bench.py

Builds a throwaway brain with pairs of notes that should be related (same idea,
sometimes across French and English) and notes that should not, then prints the
scores so the floor can sit between the two groups.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine import brain, database  # noqa: E402
from engine.assistant.llm import make_client  # noqa: E402
from engine.brain import meaning  # noqa: E402

NOTES = {
    "dodo": ("Dormir plus tôt", "J'suis brûlé, faut que je me couche avant 23 h cette semaine."),
    "sleep": ("Sleep hygiene", "Consistent bedtime and no screens an hour before sleep improve rest."),
    "nps": ("Satisfaction client", "On devrait mesurer la satisfaction client chaque trimestre avec un court sondage."),
    "survey": ("Quarterly survey idea", "Run a short NPS survey every quarter to catch churn risk early."),
    "atlas": ("Migration Atlas", "La migration de données du client Atlas se fait en deux phases, bascule un dimanche."),
    "cutover": ("Cutover plan", "Database cutover on Sunday night, rollback plan ready, inventory of tables first."),
    "gateau": ("Fête de Léa", "Léa veut un gâteau au chocolat et des ballons mauves."),
    "door": ("Poignée de porte", "Réparer la poignée de la porte d'en arrière, acheter une pièce chez Rona."),
    "focus": ("Mode focus", "Idée: un mode focus avec des sons de pluie dans l'app."),
}
SHOULD = [("dodo", "sleep"), ("nps", "survey"), ("atlas", "cutover")]


def main() -> None:
    db = Path(tempfile.mkdtemp()) / "m.db"
    database.migrate(db)
    client = make_client(os.environ["OPENAI_API_KEY"])
    ids = {}
    with database.session(db) as conn:
        for k, (t, b) in NOTES.items():
            ids[k] = brain.create_note(conn, t, b)["id"]
        print(meaning.embed_notes(conn, client, "text-embedding-3-small"))
        vec = {k: meaning.unpack(conn.execute("SELECT embedding FROM note_embeddings WHERE note_id = ?",
                                              (ids[k],)).fetchone()[0]) for k in ids}
    keys = list(ids)
    pairs = sorted(((meaning.dot(vec[a], vec[b]), a, b) for i, a in enumerate(keys) for b in keys[i + 1:]), reverse=True)
    should = {tuple(sorted(p)) for p in SHOULD}
    for s, a, b in pairs:
        print(f"{s:.3f}  {'RELATED' if tuple(sorted((a, b))) in should else '       '}  {a} ~ {b}")
    with database.session(db) as conn:
        kept = {tuple(sorted((a, b))) for a, b, _ in meaning._pairs(conn)}
    names = {v: k for k, v in ids.items()}
    kept = {tuple(sorted((names[a], names[b]))) for a, b in kept}
    print("\nkept as related:", sorted(kept))
    print("missed:", sorted(should - kept), " extra:", sorted(kept - should))


if __name__ == "__main__":
    main()
