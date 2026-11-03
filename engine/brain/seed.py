"""First-run content so a new brain is not an empty void. Runs once."""
from __future__ import annotations

import sqlite3

from engine import brain, database

WELCOME = [
    ("Welcome to your Second Brain", "idea",
     "This is your space to think. Every note is a star in your graph.\n\n"
     "Start with [[Capture a thought]], then see how [[Links make constellations]].\n"
     "The engine underneath is visible any time in the [[Engine room]].\n\n#start"),
    ("Capture a thought", "note",
     "Type in the capture bar at the bottom and press Enter.\n"
     "The thought lands in your Inbox and appears in the graph. Sort it later.\n\n#start #capture"),
    ("Links make constellations", "note",
     "Write [[double brackets]] around the title of another note to link them.\n"
     "Write #tags to group ideas. Links and tags become lines in the graph.\n\n"
     "Back to [[Welcome to your Second Brain]].\n\n#start"),
    ("Engine room", "reference",
     "The System Console shows what really runs: the local API, the database,\n"
     "the Python environment and storage. Everything stays on this computer.\n\n#system"),
]


def seed_if_empty(conn: sqlite3.Connection) -> bool:
    brain.ensure_inbox(conn)
    if database.get_setting(conn, "seeded_v1"):
        return False
    if conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0:
        space = brain.create_space(conn, "Getting started", "resource", color="#ffd6a5", icon="spark")
        for title, kind, body in WELCOME:
            brain.create_note(conn, title, body, space["id"], kind=kind, source="seed")
    database.set_setting(conn, "seeded_v1", True)
    return True


def seed_all(conn: sqlite3.Connection) -> None:
    from engine.brain.structure import seed_structure

    seed_if_empty(conn)
    seed_structure(conn)
