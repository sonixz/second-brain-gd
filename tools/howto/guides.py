"""The How-to guides: their text, step by step (the screenshots come from tools/howto.gd, same step numbers).

kind "real": the agents' answers are the real model's, recorded once (tools/howto.sh --record) and replayed.
kind "scripted": no model answer matters, the scripted showcase model is used.

  python3 tools/howto/guides.py --ids            the guide ids, in page order
  python3 tools/howto/guides.py --kind <id>      real | scripted
  python3 tools/howto/guides.py --edge <id>      yes when the guide drives a real Microsoft Edge (tools/howto.sh --edge)
  python3 tools/howto/guides.py --check <id>     one screenshot per step?
  python3 tools/howto/guides.py --cost <id>      the recorded run's cost, against the cap
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COST_CAP_USD = 0.25
TOKEN_CAP = 300_000  # per guide, whatever the model

# Each step: (what you do, what you see). "say" marks words you speak or type to an agent.
GUIDES: list[dict] = []


def guide(id: str, title: str, kind: str, minutes: int, goal: str, needs: list[str], steps: list[tuple[str, str]],
          trouble: list[tuple[str, str]], docs: list[tuple[str, str]], group: str, edge: bool = False) -> None:
    GUIDES.append({"id": id, "title": title, "kind": kind, "minutes": minutes, "goal": goal, "needs": needs,
                   "steps": steps, "trouble": trouble, "docs": docs, "group": group, "edge": edge})


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

guide(
    "scanned-pdf", "Read a scanned PDF", "real", 4,
    "A PDF made of pictures of pages (a scan, a letter photographed by your bank) is read on your own computer, "
    "then filed and searchable like any document.",
    ["Windows 10 or 11 (its OCR is built in), or Tesseract on Linux (<a href=\"docs.html#files\">Files and originals</a>)"],
    [("Drop the scanned PDF on the window. Here, a two-page home insurance renewal.",
      "There is no text to select in such a file, so the Brain reads the pages itself, one by one, with the OCR "
      "built into Windows. A line at the bottom follows it: <i>page 1 / 2 read (local OCR)</i>. Nothing leaves your "
      "computer for this."),
     ("Wait a few seconds.",
      "The Archivist files what the pages say: the policy number, the renewal date, the new premium of $1,284 "
      "(up 9.2 %), the new deductible and the leak-detector discount, with three themes."),
     ("Click the item, then <b>View document</b> in its tile, or say <span class=\"say\">open the document</span>.",
      "The original pages, full screen; <kbd>←</kbd> <kbd>→</kbd> turn them. At the top: <b>Read by Windows OCR</b>."),
     ("Close it (<kbd>Esc</kbd>) and ask the Archivist: <span class=\"say\">When does my home insurance renew, and "
      "what is the new premium?</span>",
      "The answer comes from the scanned pages, with a link to the document: December 1, 2026, $1,284, up from "
      "$1,176."),
     ("Optional: open the document again and press <b>Re-read with AI</b>.",
      "Local OCR sometimes confuses characters: on this scan it read <i>$l,ooo</i> for <i>$1,000</i>. The AI "
      "reading sends the page images to OpenAI and replaces the text; the label becomes <b>Read by AI</b>. It is "
      "never done unless you ask."),
     ],
    [("“No local OCR here”.", "On Linux, install Tesseract: <code>sudo apt install tesseract-ocr</code>. On Windows, "
      "check that the document's language is installed (Settings → Time &amp; language → Language)."),
     ("Figures are wrong.", "Use <b>Re-read with AI</b> on that document."),
     ("It takes long.", "Big scans are read page by page; the line at the bottom shows where it is.")],
    [("Scanned PDFs: local OCR first", "docs.html#files")],
    "The Brain")

guide(
    "graph", "Find your way in the graph", "scripted", 4,
    "Zoom from the whole Brain down to one text, fold what you are not using, filter, and switch to the timeline.",
    [],
    [("Zoom out (mouse wheel, or say <span class=\"say\">overview</span>).",
      "Each place is a zone with its name and how many items it holds; the Inbox sits in the middle. Zones keep "
      "their spot, so things stay where you left them."),
     ("Zoom towards a place, or say <span class=\"say\">zoom into Kitchen renovation</span>.",
      "Items become cards: their title, place, themes and first lines, and the first page of a PDF."),
     ("Keep zooming on one card.",
      "The scale disappears and you are reading the full text, inside the graph. The minimap, bottom right, keeps "
      "you oriented."),
     ("Double-click a place you are not using, or say <span class=\"say\">fold Cooking</span>.",
      "Its items gather into a <b>+N</b> badge. Double-click it again to unfold."),
     ("Click <b>Filter</b>, or say <span class=\"say\">show only the articles</span>.",
      "Filter by type, origin (typed, spoken, web, files, packs), date, or a word or theme. <b>× Show all</b> "
      "clears it."),
     ("Click <b>?</b>.",
      "What each line means: a real link (solid, with a dot travelling along), a suggestion by meaning (dashed), "
      "belonging to a place, carrying a theme, and the golden path that answers “how is X connected to Y?”."),
     ("Click <b>Timeline</b>, or say <span class=\"say\">show the timeline</span>.",
      "The same items along time, one lane per place, from minutes to months. Click <b>Timeline</b> again to go back "
      "to the zones."),
     ],
    [("The graph feels crowded.", "Fold places, filter, or press <kbd>Tab</kbd> to hide the panels."),
     ("You are lost.", "Zoom all the way out, or click a spot on the minimap.")],
    [("The graph", "docs.html#graph"), ("Voice commands", "docs.html#voice")],
    "The Brain")

guide(
    "packs", "Share a project as a pack", "scripted", 4,
    "Export part of your Brain as one <code>.brain</code> file, and bring in a pack someone shared, as a layer you "
    "can switch off.",
    [],
    [("Open <b>Captures</b>, then <b>Packs…</b> (or say <span class=\"say\">export the Kitchen renovation project</span>). "
      "Choose what leaves: a place, a theme, a search or chosen items.",
      "Before anything is written, the preview says what will leave (7 items, 3 sources) and what never does: "
      "your keys, settings, conversations and costs."),
     ("Add a title and your name, tick <b>Include the original files</b> if the PDFs should travel too, and press "
      "<b>Export the pack</b>.",
      "One file lands in the <code>exports</code> folder of your data folder; <b>Show in folder</b> opens it. Send it "
      "like any file."),
     ("To bring one in, drop a <code>.brain</code> file on the window, or press <b>Import a pack…</b>. Here, Julie's "
      "notes on sourdough.",
      "It becomes a layer: 4 items from Julie, listed with a switch to turn it off, <b>Merge</b> to make the items "
      "yours, and <b>Remove</b> to take it all out without touching your own items."),
     ("Close the dialog and look at the graph.",
      "Julie's items have their own place, <i>Sourdough</i>, with its links and themes, ready to search and to "
      "connect to yours."),
     ],
    [("“Nothing to export”.", "The selection is empty: choose another place or search."),
     ("An imported pack looks wrong.", "Switch its layer off, or remove it: your own items are never changed by an "
      "import.")],
    [("Brain packs", "docs.html#packs")],
    "The Brain")

guide(
    "connect", "Find how two ideas connect", "real", 3,
    "Search by meaning, ask how two things you know are related, and keep the links that matter.",
    [],
    [("Type in <b>Search your brain</b> at the top (or press <kbd>/</kbd>): <i>countertops</i>.",
      "The matching items light up in the graph and are listed with why they matched: by meaning, with a score, or "
      "by their words."),
     ("Ask the Archivist: <span class=\"say\">How is the opening story for my talk connected to Automerge?</span>",
      "The path is drawn in gold through the graph, and the answer tells it step by step: the story shares the "
      "#talk theme with the talk outline, which links to <i>CRDTs in plain words</i>, which cites Automerge."),
     ("Click an item to open its tile. Here, a note just written about merging edits without a server, linked to "
      "nothing yet.",
      "Under its text: its connections (none), then <b>Related ideas</b>: items close in meaning that are not linked "
      "yet, here <i>CRDTs in plain words</i>. In the graph, a suggestion is a dashed line."),
     ("Press <b>✓</b> next to a related idea to keep it (or <b>✕</b> to dismiss it for good).",
      "The suggestion becomes a real link, drawn as a solid line, and it now counts in paths and searches."),
     ],
    [("“No path”.", "The two items share nothing yet: link them, or add a note that connects them."),
     ("No related ideas.", "They appear once items are indexed by meaning (a few seconds after they come in).")],
    [("The graph", "docs.html#graph")],
    "Find and connect")

guide(
    "web", "Search the web and keep a page", "real", 3,
    "Ask a question about the world, read the answer with its sources, and keep the page you trust.",
    ["Internet on (it is by default: <a href=\"docs.html#internet\">Internet</a>)"],
    [("Ask the Archivist: <span class=\"say\">Search the web: what size of circuit does an induction cooktop "
      "need?</span>",
      "A short answer (a dedicated 40 A circuit for a 30-inch model, 50 A for some 36-inch ones, check the "
      "model's rating) with its sources listed as links under it. A click opens a source in your browser."),
     ("Say which one to keep: <span class=\"say\">Add the first source to Kitchen renovation.</span>",
      "The page is downloaded from your computer, kept as an original, summarised and filed where you said. Undo "
      "takes it out again."),
     ("Zoom into it in the graph.",
      "The page's summary and key points, in your Kitchen renovation project, ready for search and for the "
      "agents."),
     ],
    [("A site refuses automatic reading.", "The page becomes a reference card (title, what the search said, the "
      "link). With the <a href=\"#browser\">browser extension</a>, send it as your browser shows it."),
     ("Nothing is searched.", "Check that Internet is on for this agent (ⓘ, the Internet switch).")],
    [("Internet", "docs.html#internet")],
    "Find and connect")

guide(
    "browser", "Connect your browser", "real", 5,
    "Pair Microsoft Edge (or Chrome) with your Brain once; then send the page you are reading in one click, and "
    "let the Archivist open, add and close tabs when you ask.",
    ["The extension loaded once: <code>edge://extensions</code> → Developer mode → <b>Load unpacked</b> → the "
     "<code>browser-extension</code> folder of the project (<a href=\"docs.html#extension\">Browser extension</a>)"],
    [("In the app: <b>Captures</b> → <b>Send from browser…</b> → <b>Pair a browser</b>.",
      "A one-time code and the port the Brain listens on. The code works once and only for 10 minutes."),
     ("In Edge, click the Second Brain icon in the toolbar and type the code and the port.",
      "The extension's popup, in Edge. Keep the box ticked if you want to say “add it” for the pages the Brain "
      "opens."),
     ("Click <b>Pair</b>.",
      "Edge itself asks whether the extension may read the pages. Click <b>Allow</b>. It only ever reads a page you "
      "send, or one the Brain opened for you."),
     ("Back in the app.",
      "<b>● Connected: Edge</b>, with the extension's version. It reconnects by itself whenever the app is open."),
     ("On any page, the icon → <b>Send this page</b> (or <kbd>Alt</kbd>+<kbd>Shift</kbd>+<kbd>B</kbd>).",
      "The receipt shows in the popup: the page as Edge shows it (after your login, nothing downloaded again) is read, "
      "summarised and filed."),
     ("Look in Captures.",
      "The page is there, filed by the Archivist, like anything else you add."),
     ("Ask the Archivist: <span class=\"say\">Search the web: do cold-climate heat pumps still work at -25 °C?</span>",
      "An answer with its sources, as links."),
     ("<span class=\"say\">Open the first one.</span>",
      "Edge opens it in a new tab, in front: here a PDF from Natural Resources Canada, in Edge's own viewer. The "
      "Brain remembers it opened that tab."),
     ("<span class=\"say\">Add it.</span>",
      "The tab is kept and filed, with a receipt and Undo. A web page is taken as Edge shows it; a PDF, which the "
      "extension cannot read inside Edge's viewer, is downloaded by the Brain instead."),
     ("<span class=\"say\">Close it.</span>",
      "Edge closes the tab the Brain opened. Your own tabs are never touched."),
     ],
    [("“The Brain is not reachable”.", "The app must be open, and the port in the popup must be the one the app "
      "shows."),
     ("“Wrong code” or “no pairing code is active”.", "Ask the app for a new code (it works once, 10 minutes)."),
     ("“Add it” says the extension may not read pages.", "Open the popup and click <b>Allow reading the pages the "
      "Brain opens</b>.")],
    [("Browser extension", "docs.html#extension"), ("Internet", "docs.html#internet")],
    "Find and connect", edge=True)

guide(
    "organise", "Organise by voice", "real", 3,
    "Move, link and undo by naming things, the way you would ask a person.",
    [],
    [("Hold <kbd>F8</kbd> and say, or type: <span class=\"say\">What is still waiting in the Inbox?</span>",
      "The two items the Archivist could not file alone, as links."),
     ("<span class=\"say\">Put the heat pump rebate note in Finances.</span>",
      "It finds the item by its name and moves it. The receipt under the answer says exactly what changed, with "
      "Undo."),
     ("<span class=\"say\">Link the heat pump rebate to the renovation budget.</span>",
      "A real link between the two, drawn in the graph."),
     ("<span class=\"say\">Undo that.</span>",
      "The last change is reversed and the answer says which. Every change the agents make is journaled, so it can "
      "be undone."),
     ],
    [("It says it found nothing.", "Use a few words of the title, or ask “find…” first."),
     ("It did not do what it said.", "It cannot: the engine checks every reply against what really changed. "
      "If nothing changed, it says so.")],
    [("Voice commands", "docs.html#voice")],
    "Find and connect")

guide(
    "sparring", "Think an idea through with Sparring", "real", 6,
    "Talk an idea through with a partner that challenges you, then keep only what you decided.",
    [],
    [("Click <b>S</b> on the rail (or <kbd>Ctrl</kbd>+<kbd>2</kbd>).",
      "Sparring opens and waits for your idea. It never changes your Brain on its own."),
     ("Say the idea, and what you need: <span class=\"say\">I want to open my talk with a story and no slides for "
      "the first three minutes. Challenge me honestly.</span> Type it, hold <kbd>F8</kbd>, or press <kbd>F9</kbd> "
      "to talk freely.",
      "It reacts in a few sentences: what can work, the risk (three minutes of atmosphere before the point), and "
      "one question that moves things forward."),
     ("Answer, push back, add: <span class=\"say\">Instead of a diagram for CRDTs, I'd use a shared recipe card "
      "that everyone edits at once.</span>",
      "It weighs it: more inviting than a diagram, but it could teach the wrong lesson, and it proposes a demo "
      "that avoids it."),
     ("When the idea is ripe: <span class=\"say\">Sum it up.</span>",
      "The synthesis, in full: the idea, what was clarified, objections and answers, open questions and next "
      "leads. Marked <b>not saved yet</b>, with <b>Save to the Brain</b> and <b>Change it…</b>."),
     ("<span class=\"say\">Yes, save it.</span> (or the button)",
      "The Archivist files it like any item, here in the talk's project, with Undo."),
     ],
    [("It repeats what you said.", "Ask it to be more direct, or change its instructions with the Agent Builder "
      "(<a href=\"#own-agent\">Create your own agent</a>)."),
     ("Nothing is saved.", "That is the point until you approve: say “yes, save it” or press the button.")],
    [("Talking it through with Sparring", "docs.html#agents-profiles")],
    "Agents")

guide(
    "own-agent", "Create your own agent", "real", 6,
    "Describe the agent you need out loud; the Agent Builder interviews you and writes it. You never write a prompt.",
    [],
    [("Click <b>+</b> on the rail (or tell the Archivist <span class=\"say\">create an agent for me</span>).",
      "The Agent Builder opens and asks what the agent is for, with an example of an answer."),
     ("Answer in a sentence or two: <span class=\"say\">A coach to rehearse my local-first talk out loud before the "
      "meetup. It should know my talk.</span>",
      "It looks in your Brain, finds the talk's project and the reference place it relies on, and asks the next "
      "question: how it should coach you."),
     ("Answer its questions (tone, what it may do), then let it write.",
      "The whole agent, shown before anything is created: role, tone and format, how it works, what to avoid, its "
      "ground in your Brain, examples. <b>Create it</b> or <b>Change it…</b>."),
     ("<span class=\"say\">Yes, create it.</span>",
      "Talk Coach gets its own panel, its letter and its own conversation. A new agent only reads your Brain unless "
      "you say otherwise."),
     ("Talk to it in its panel.",
      "It answers as its instructions say, with what your Brain holds: here it asks you to go on and points to two "
      "other opening stories in your notes."),
     ("Press <b>ⓘ</b> in its title bar.",
      "Its settings in a tile: name, model, a switch per capability with the tools it gives, and its instructions. "
      "Change anything here, or press <b>Ask the Builder to change it…</b> and say what to change."),
     ],
    [("The Builder keeps asking.", "Say “that's all, write it”."),
     ("You want to undo it.", "ⓘ, then <b>Delete this agent</b>.")],
    [("What an agent is", "docs.html#agents-profiles")],
    "Agents")

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
    """Tokens per model and the cost where the price is known (the engine never invents a price)."""
    sys.path.insert(0, str(ROOT))
    from engine.assistant.llm import estimate_cost

    rec = json.loads((ROOT / "tools" / "howto" / "recordings" / f"{gid}.json").read_text(encoding="utf-8"))
    tokens: dict[str, int] = {}
    known = 0.0
    for c in rec["calls"]:
        u = c.get("usage") or {}
        tokens[c.get("model", "?")] = tokens.get(c.get("model", "?"), 0) + int(u.get("prompt_tokens", 0)) + int(u.get("completion_tokens", 0))
        known += estimate_cost(c.get("model", ""), u) or 0.0
    known += 0.03 * len(rec.get("web", []))  # hosted web search, per call (list price, approximate)
    total_tokens = sum(tokens.values())
    print(f"{gid}: {len(rec['calls'])} model calls, {len(rec.get('web', []))} web searches, "
          + ", ".join(f"{m} {t:,} tokens" for m, t in tokens.items()) + f"; priced part about ${known:.3f}")
    return 0 if known <= COST_CAP_USD and total_tokens <= TOKEN_CAP else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["--ids"]:
        print("\n".join(g["id"] for g in GUIDES))
    elif a[:1] == ["--kind"]:
        print(by_id(a[1])["kind"])
    elif a[:1] == ["--edge"]:
        print("yes" if by_id(a[1])["edge"] else "no")
    elif a[:1] == ["--check"]:
        sys.exit(_check(a[1]))
    elif a[:1] == ["--cost"]:
        sys.exit(_cost(a[1]))
    else:
        print(__doc__)
