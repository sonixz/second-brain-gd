"""Builds tools/howto/files/sourdough-starter.brain: a small pack "a friend shared", for the packs guide.
Pure engine code on a throwaway database: python3 tools/howto/make_pack.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine import brain, database  # noqa: E402
from engine.brain import packs  # noqa: E402

NOTES = [
    ("Feeding schedule for a sourdough starter",
     "Feed once a day at room temperature: discard all but 50 g, add 50 g flour and 50 g water. In the fridge, once a "
     "week. A healthy starter doubles in 4 to 8 hours. #sourdough"),
    ("Why my starter smells like nail polish",
     "An acetone smell means it is hungry, not dead. Feed it twice a day for two days, a little warmer. #sourdough"),
    ("Country loaf, 75 % hydration",
     "500 g flour (450 white, 50 whole wheat), 375 g water, 100 g active starter, 10 g salt. Four sets of stretch and "
     "folds, 30 minutes apart; bulk until +50 %; shape; 12 h in the fridge; bake 20 min covered and 25 uncovered at 245 °C. "
     "#sourdough #bread"),
    ("Flour notes from the mill visit",
     "Fresh stone-ground whole wheat absorbs more water: add 5 % more. Rye ferments faster. #flour #bread"),
]

if __name__ == "__main__":
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "brain.sqlite3"
    database.migrate(db)
    with database.session(db) as conn:
        sp = brain.create_space(conn, "Sourdough", "resource", color="#ffd2a1")
        for title, body in NOTES:
            brain.create_note(conn, title, body, sp["id"], kind="note", source="typed")
    out = packs.export(db, {"place": "Sourdough"}, tmp / "out", "Sourdough starter, from Julie",
                       author="Julie", licence="CC BY 4.0", description="My notes on keeping a starter alive and a first loaf.")
    dst = ROOT / "tools" / "howto" / "files" / "sourdough-starter.brain"
    shutil.copy(out["path"] if isinstance(out, dict) and "path" in out else out, dst)
    print(dst, dst.stat().st_size)
