"""First-run content. A new Brain starts almost empty (Loop 9): the Inbox and a short
Getting started guide. Its places and themes grow from what you put in it.

The older demo seed (English welcome notes plus preset areas such as Famille and Santé)
is kept for the tests and screenshots only: SBGD_SEED=demo, or seed_all() in tests.
"""
from __future__ import annotations

import os
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


GUIDE = [
    ("Bienvenue dans ton Second Brain", "idea",
     "Ton Brain prend tout ce que tu lui donnes, le comprend, le classe et le relie.\n\n"
     "1. [[Capturer n'importe quoi]]\n2. [[Comment le Brain classe]]\n3. [[Retrouver et explorer]]\n"
     "4. [[Tout faire à la voix]]\n\nTu peux effacer ce guide quand tu veux.\n\n#guide"),
    ("Capturer n'importe quoi", "note",
     "Écris ou colle dans la barre du bas, puis Entrée: une idée, un texte, un lien web.\n"
     "Glisse un PDF, un Word ou un Markdown sur la fenêtre. Ou parle (F8).\n"
     "Tout arrive dans l'Inbox, puis l'archiviste s'en occupe en quelques secondes.\n\n#guide"),
    ("Comment le Brain classe", "note",
     "Méthode CODE: Capturer, Organiser, Distiller, Exprimer. Classement PARA:\n"
     "- Projets: un résultat avec une échéance\n- Domaines: une responsabilité permanente\n"
     "- Ressources: un sujet d'intérêt\n- Archives: ce qui n'est plus actif\n\n"
     "Ton Brain part vide: l'archiviste crée les places et les thèmes au fur et à mesure, "
     "résume les longs documents, relie les éléments par le sens et te donne un reçu. "
     "S'il n'est pas sûr, il laisse l'élément dans l'Inbox et te pose une question. Tout est annulable.\n\n"
     "« Je veux structurer le projet X » classe les prochains éléments dans ce projet.\n\n#guide"),
    ("Retrouver et explorer", "note",
     "Cherche par le sens (« l'article sur les agents qui… »), même entre le français et l'anglais.\n"
     "Le graphe montre tes places, tes éléments et leurs liens. L'onglet Captures montre tout ce qui est entré.\n\n#guide"),
    ("Tout faire à la voix", "note",
     "Maintiens F8 et parle, relâche pour envoyer. F9 ouvre une conversation en direct.\n"
     "Exemples: « ajoute ça au Brain », « cherche l'article sur… », « ouvre les captures », "
     "« relis-moi ça », « parle plus vite », « annule ça ».\n\n#guide"),
]


def seed_brain(conn: sqlite3.Connection) -> bool:
    """What a real install starts with: the Inbox and the Getting started guide. Runs once."""
    brain.ensure_inbox(conn)
    if database.get_setting(conn, "seeded_v1") or database.get_setting(conn, "seeded_v2"):
        return False
    if conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 0:
        space = brain.create_space(conn, "Getting started", "resource", color="#ffd6a5", icon="spark")
        for title, kind, body in GUIDE:
            brain.create_note(conn, title, body, space["id"], kind=kind, source="seed")
    database.set_setting(conn, "seeded_v2", True)
    return True


def seed_for_app(conn: sqlite3.Connection) -> None:
    """The app's first start: the fresh Brain, or the demo content when SBGD_SEED=demo (tests, screenshots)."""
    if os.environ.get("SBGD_SEED") == "demo":
        seed_all(conn)
    else:
        seed_brain(conn)
