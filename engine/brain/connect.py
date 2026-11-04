"""How things connect (Loop 14): the path between two items, and the user's choices on related ideas."""
from __future__ import annotations

import heapq
import sqlite3
from typing import Any

from engine import brain
from engine.events import utc_now

# Cost of crossing one edge: a link you made is the strongest connection, then a related idea found by
# meaning, then a shared theme (two hops through the tag), then simply being in the same place.
COST = {"link": 1.0, "related": 1.5, "tag": 1.0, "space": 2.0, "area": 2.0}
WHY = {"link": "un lien", "related": "une idée liée par le sens", "tag": "le thème", "space": "la place", "area": "le domaine"}


def resolve(conn: sqlite3.Connection, text: str, client: Any = None) -> str | None:
    """An item id from an id or a title (exact, then by meaning or words)."""
    t = (text or "").strip()
    if not t:
        return None
    row = conn.execute("SELECT id FROM notes WHERE id = ? AND status != 'archived'", (t,)).fetchone()
    if row:
        return row["id"]
    for r in conn.execute("SELECT id, title FROM notes WHERE status != 'archived'"):
        if r["title"].casefold() == t.casefold():
            return r["id"]
    from engine.brain import meaning

    hits = meaning.search_notes(conn, client, t, 1)
    return hits[0]["id"] if hits else None


def path(conn: sqlite3.Connection, a: str, b: str) -> dict[str, Any]:
    g = brain.graph(conn)
    labels = {n["id"]: (n["label"], n["type"]) for n in g["nodes"]}
    adj: dict[str, list[tuple[str, str]]] = {}
    for e in g["edges"]:
        if e["from"] in labels and e["to"] in labels:
            adj.setdefault(e["from"], []).append((e["to"], e["type"]))
            adj.setdefault(e["to"], []).append((e["from"], e["type"]))
    if a not in labels or b not in labels:
        raise brain.NotFound("item")
    dist = {a: 0.0}
    prev: dict[str, tuple[str, str]] = {}
    heap = [(0.0, a)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == b:
            break
        if d > dist.get(u, 1e18):
            continue
        for v, kind in adj.get(u, []):
            nd = d + COST.get(kind, 3.0)
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                prev[v] = (u, kind)
                heapq.heappush(heap, (nd, v))
    if b not in dist:
        return {"found": False, "ids": [], "steps": [],
                "explanation": f"Aucun chemin entre « {labels[a][0]} » et « {labels[b][0]} » dans ton Brain."}
    chain = [b]
    steps = []
    while chain[-1] != a:
        u, kind = prev[chain[-1]]
        steps.append({"from": u, "to": chain[-1], "type": kind})
        chain.append(u)
    chain.reverse()
    steps.reverse()
    nodes = [{"id": i, "label": labels[i][0], "type": labels[i][1]} for i in chain]
    parts = []
    for st in steps:
        mid = labels[st["to"]]
        if mid[1] == "tag":
            parts.append(f"{WHY['tag']} {mid[0]}")
        elif mid[1] == "space":
            parts.append(f"{WHY['space']} {mid[0]}")
        elif st["type"] in ("link", "related"):
            parts.append(f"{WHY[st['type']]} vers « {mid[0]} »")
        else:
            parts.append(f"« {mid[0]} »")
    explanation = (f"« {labels[a][0]} » rejoint « {labels[b][0]} » en {len(steps)} étape" + ("s" if len(steps) > 1 else "")
                   + " : " + ", puis ".join(parts) + ".")
    return {"found": True, "ids": chain, "nodes": nodes, "steps": steps, "cost": round(dist[b], 2),
            "explanation": explanation}


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def choose_related(conn: sqlite3.Connection, a: str, b: str, choice: str) -> dict[str, Any]:
    """'kept' turns the suggestion into a real link; 'dismissed' hides it for good."""
    if choice not in ("kept", "dismissed"):
        raise ValueError("choice must be kept or dismissed")
    for nid in (a, b):
        brain.get_note(conn, nid)  # 404 for unknown items
    x, y = _pair(a, b)
    conn.execute("INSERT OR REPLACE INTO related_choices (a, b, choice, created_at) VALUES (?, ?, ?, ?)", (x, y, choice, utc_now()))
    if choice == "kept":
        conn.execute("INSERT OR IGNORE INTO links (from_note, to_note, kind, created_by, created_at)"
                     " VALUES (?, ?, 'related', 'user', ?)", (a, b, utc_now()))
    return {"a": a, "b": b, "choice": choice}
