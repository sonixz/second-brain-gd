"""The How-to guides: their text, step by step (the screenshots come from tools/howto.gd, same step numbers).

kind "real": the agents' answers are the real model's, recorded once (tools/howto.sh --record) and replayed.
kind "scripted": no model answer matters, the scripted showcase model is used.

  python3 tools/howto/guides.py --ids            the guide ids, in page order
  python3 tools/howto/guides.py --kind <id>      real | scripted
  python3 tools/howto/guides.py --check <id>     one screenshot per step?
  python3 tools/howto/guides.py --cost <id>      the recorded run's cost, against the cap
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COST_CAP_USD = 0.25

# Each step: (what you do, what you see). "say" marks words you speak or type to an agent.
GUIDES: list[dict] = []


def guide(id: str, title: str, kind: str, minutes: int, goal: str, needs: list[str], steps: list[tuple[str, str]],
          trouble: list[tuple[str, str]], docs: list[tuple[str, str]], group: str) -> None:
    GUIDES.append({"id": id, "title": title, "kind": kind, "minutes": minutes, "goal": goal, "needs": needs,
                   "steps": steps, "trouble": trouble, "docs": docs, "group": group})


def by_id(gid: str) -> dict:
    for g in GUIDES:
        if g["id"] == gid:
            return g
    raise SystemExit(f"no guide {gid}")


# ---------------------------------------------------------------- the guides (page order)
# GUIDES-START
guide(
    "first-minutes", "Your first five minutes", "real", 5,
    "Add a thought and a PDF, and see where the Archivist files them, without choosing anything yourself.",
    ["Second Brain GD installed, with your OpenAI key (<a href=\"docs.html#install\">Install</a>)"],
    [("Click the capture bar at the bottom (or press <kbd>Ctrl</kbd>+<kbd>Space</kbd>) and type a thought as it "
      "comes: <i>Ask Northwind if the heat pump quote includes the smart thermostat</i>.",
      "No place to choose, no tags to add. The bar says where it would land if nobody filed it: your Inbox."),
     ("Press <kbd>Enter</kbd>.",
      "The Archivist reads it and files it at once. Its receipt says what it is and where it went: “A question "
      "about a heat pump quote, filed in Areas › Home and linked to the heat pump rebate.” Undo, under the "
      "receipt, puts it back."),
     ("Drop a PDF on the window (or use <b>+ File</b> in Places). Here, a quote for a heat pump.",
      "The file is copied into your originals, read, summarised and filed: “A heat pump installation quote, filed "
      "in Areas › Home and linked to 2 related items.” The summary keeps what matters: $14,690 before taxes, a "
      "rebate of up to $5,000, valid until December 15."),
     ("Click <b>Captures</b> at the top.",
      "Everything that came in, newest first, with its place, its type and where it came from (typed, spoken, a "
      "file, the web). Items still waiting in the Inbox show the Archivist's question in orange."),
     ("Back in <b>Graph</b>, zoom into the new item: scroll over it, or say <span class=\"say\">zoom into the "
      "heat pump quote</span>.",
      "Close up, the card shows the quote's summary and its first page. Zoom further and the whole text is there, "
      "inside the graph."),
     ],
    [("The item stays in the Inbox.", "The Archivist asks a question when it is not sure. Answer it in its panel, "
      "or drag the item into a place."),
     ("No receipt at all.", "Filing needs your OpenAI key (<a href=\"docs.html#openai-key\">Your OpenAI key</a>). "
      "Without one, items wait in the Inbox."),
     ("The PDF says it has no text.", "It is a scan: see <a href=\"#scanned-pdf\">Read a scanned PDF</a>.")],
    [("Capture anything", "docs.html#capture"), ("How the Archivist files", "docs.html#archivist")],
    "Start")

guide(
    "panels", "Arrange your panels", "scripted", 3,
    "Move, dock, stack and shrink the panels around the graph, and get the default layout back.",
    [],
    [("Start from the default layout.",
      "The Archivist's panel is docked on the left. On the far left, the rail holds the panels you have shrunk "
      "(S Sparring, P Places, B the Agent Builder) and <b>+</b> to create an agent."),
     ("Drag a panel by its title bar (⠿). Here, Sparring.",
      "While you drag, the place where it would land lights up. Near the left, right or bottom edge it docks; "
      "anywhere else it floats where you drop it."),
     ("Drop it near the right edge. Then click <b>P</b> on the rail to open Places.",
      "Sparring is docked on the right. Places opens on the left, under the Archivist: two panels on the same "
      "edge share it."),
     ("Drag the short line between two stacked panels.",
      "One gets more height, the other less. Any panel also resizes from its bottom-right corner."),
     ("Click <b>–</b> in a panel's title bar, or double-click its title.",
      "It shrinks into its letter on the rail; a click on the letter brings it back where it was. From the "
      "keyboard: <kbd>Ctrl</kbd>+<kbd>1</kbd> the Archivist, <kbd>Ctrl</kbd>+<kbd>2</kbd> Sparring, "
      "<kbd>Ctrl</kbd>+<kbd>3</kbd> Places, <kbd>Ctrl</kbd>+<kbd>4</kbd> the item tile, and up for your own agents."),
     ("Press <kbd>Tab</kbd> on the graph.",
      "Every panel steps aside: the graph alone. <kbd>Tab</kbd> again brings them back."),
     ("Lost? Scroll to the bottom of Places and press <b>Reset the panel layout</b>.",
      "Everything goes back to its default place. Otherwise your layout is remembered from one session to the "
      "next."),
     ],
    [("A panel is nowhere to be seen.", "Look for its letter on the rail, or press its shortcut."),
     ("A panel covers what you need.", "Shrink it, press <kbd>Tab</kbd>, or dock it on another edge.")],
    [("Arranging the panels", "docs.html#agents-profiles")],
    "Start")

guide("scanned-pdf", "Read a scanned PDF", "real", 4, "", [], [("", "")] * 5, [], [], "The Brain")
guide("graph", "Find your way in the graph", "scripted", 4, "", [], [("", "")] * 7, [], [], "The Brain")
guide("packs", "Share a project as a pack", "scripted", 4, "", [], [("", "")] * 4, [], [], "The Brain")
# GUIDES-END


def _check(gid: str) -> int:
    g = by_id(gid)
    shots = sorted((ROOT / "docs" / "screenshots" / "howto" / gid).glob("*.png"))
    if len(shots) != len(g["steps"]):
        print(f"{gid}: {len(shots)} screenshots for {len(g['steps'])} steps", file=sys.stderr)
        return 1
    print(f"{gid}: {len(shots)} steps captured")
    return 0


def _cost(gid: str) -> int:
    sys.path.insert(0, str(ROOT))
    from engine.assistant.llm import estimate_cost

    rec = json.loads((ROOT / "tools" / "howto" / "recordings" / f"{gid}.json").read_text(encoding="utf-8"))
    total = sum(estimate_cost(c.get("model", ""), c.get("usage")) or 0.0 for c in rec["calls"])
    total += 0.03 * len(rec.get("web", []))  # hosted web search, per call (list price, approximate)
    print(f"{gid}: {len(rec['calls'])} model calls, {len(rec.get('web', []))} web searches, about ${total:.3f}")
    return 0 if total <= COST_CAP_USD else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--ids"]:
        print("\n".join(g["id"] for g in GUIDES))
    elif a[:1] == ["--kind"]:
        print(by_id(a[1])["kind"])
    elif a[:1] == ["--check"]:
        sys.exit(_check(a[1]))
    elif a[:1] == ["--cost"]:
        sys.exit(_cost(a[1]))
    else:
        print(__doc__)
