"""The showcase Brain (SBGD_SEED=showcase): an English example used only for the website screenshots.

About fifty items filed the way the archivist files them (PARA places, themes, receipts), spread over
three weeks so the timeline has a shape: typed and spoken notes, web articles, a PDF quote and a photo of
a sketch, both kept as originals. Nothing here calls a model: the PDF and the image get their summaries
from ShowcaseChat, a scripted stand-in (SBGD_ASSISTANT_PROVIDER=showcase) that also answers the
archivist in English while the screenshots are taken.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from engine import brain, database
from engine.assistant.llm import FakeChat
from engine.brain import archivist

ASSETS = Path(__file__).resolve().parents[2] / "tools" / "showcase"

# name, PARA kind, colour, parent area
PLACES = [
    ("Kitchen renovation", "project", "#ffd2a1", "Home"),
    ("Talk: local-first software", "project", "#a6dcff", None),
    ("Learn Japanese", "project", "#ffb3c6", None),
    ("Health", "area", "#a9f0c7", None),
    ("Finances", "area", "#f5e6a3", None),
    ("Home", "area", "#9fd8d0", None),
    ("Local-first software", "resource", "#c8b6ff", None),
    ("Cooking", "resource", "#d8c3a5", None),
    ("Productivity", "resource", "#b9d7ff", None),
    ("Apartment move 2025", "archive", "#8fa3ba", None),
]

# place, days ago, hour, item_type, origin, title, body, url (articles)
ITEMS: list[tuple[str | None, int, int, str, str, str, str, str | None]] = [
    ("Kitchen renovation", 3, 18, "note", "voice", "Call with Marc about the electrical panel",
     "Marc says the panel is a 100 A from the eighties. There should be room for one more 40 A breaker, but he wants to "
     "open it before we sign anything. He can come Thursday morning. Ask him about the under-cabinet lights too. "
     "See [[Contractor quote — Brightline Renovations]]. #electrical", None),
    ("Kitchen renovation", 9, 20, "idea", "typed", "Open shelving on the window wall",
     "Two oak shelves instead of upper cabinets on the window side. Lighter room, fewer doors. "
     "Check the [[Kitchen layout sketch]]. #design", None),
    ("Kitchen renovation", 7, 12, "list", "typed", "Appliances shortlist",
     "- Induction cooktop, 30 in, 4 zones\n- Counter-depth fridge\n- Quiet dishwasher (≤ 44 dB)\n- Range hood, ducted outside\n\n"
     "The cooktop needs a 40 A circuit, see [[Call with Marc about the electrical panel]]. #appliances", None),
    ("Kitchen renovation", 2, 17, "note", "voice", "Tile samples: the matte green wins",
     "We put the three tile samples behind the sink. The matte green looks best in the evening light; the white "
     "gloss shows every splash. Order 32 square feet plus ten percent. #design", None),
    ("Kitchen renovation", 12, 21, "article", "url", "Quartz vs. butcher block countertops",
     "Quartz is non-porous and needs no sealing; butcher block is warmer and cheaper but must be oiled every few "
     "months and marks easily near the sink. Many kitchens mix both: quartz around the sink and cooktop, wood on the island.\n\n"
     "- Quartz: about $70–120 per sq ft installed\n- Butcher block: about $40–70 per sq ft\n- Wood near water needs care\n\n#countertops",
     "https://kitchenlab.blog/quartz-vs-butcher-block"),
    ("Talk: local-first software", 2, 10, "note", "typed", "Talk outline",
     "1. Story: the day the café Wi-Fi died\n2. What local-first means, see [[Local-first software: you own your data]]\n"
     "3. [[CRDTs in plain words]]\n4. Live demo, see [[Demo: unplug the network on stage]]\n5. What it costs you as a developer\n\n#talk", None),
    ("Talk: local-first software", 1, 8, "idea", "voice", "Opening story for the talk",
     "Start with the train ride: I wrote half a chapter with no signal and it all synced when we came out of the "
     "tunnel. Nobody noticed, and that is the point. Thirty seconds, then the first slide. #talk", None),
    ("Talk: local-first software", 4, 22, "idea", "typed", "Demo: unplug the network on stage",
     "Two laptops editing the same list. Pull the router's cable, keep editing on both, plug it back in and watch "
     "them merge. Practise it three times; have a video as a fallback. #talk #demo", None),
    ("Talk: local-first software", 10, 9, "note", "typed", "Send the abstract to the meetup organisers",
     "Twenty-minute slot on the 21st. Abstract: why your app should work on a plane, and how CRDTs make "
     "it possible. Due Friday. #talk", None),
    ("Learn Japanese", 16, 19, "journal", "typed", "Hiragana done, katakana next",
     "Finished all 46 hiragana with the flashcards. Katakana starts Monday, ten a day. #kana", None),
    ("Learn Japanese", 5, 7, "note", "voice", "Phrases for ordering at a café",
     "Practise: kōhī o hitotsu kudasai, one coffee please. Mise de tabemasu, I'll eat here. Mochikaeri de, to go. "
     "Say them out loud on the walk to work. #speaking", None),
    ("Learn Japanese", 13, 21, "list", "typed", "Daily routine for Japanese",
     "- 15 minutes of flashcards\n- One podcast episode on the bus\n- Write three sentences before bed\n\n"
     "Inspired by [[Spaced repetition, explained]]. #routine", None),
    ("Learn Japanese", 6, 20, "quote", "typed", "Komorebi",
     "Komorebi: sunlight filtering through the leaves of trees. My favourite word this week. #vocabulary", None),
    ("Productivity", 14, 13, "article", "url", "Spaced repetition, explained",
     "An interactive explainer on why reviewing just before you forget is the most efficient way to remember. "
     "Each successful review pushes the next one further away.\n\n- The forgetting curve flattens with each review\n"
     "- Short daily sessions beat long weekly ones\n- Cards should test one idea each\n\n#memory #learning",
     "https://ncase.me/remember/"),
    ("Health", 6, 7, "journal", "typed", "Sleep log: seven hours average",
     "Averaged 7 h this week, better since the phone stays in the kitchen. Two late nights before the quote "
     "meeting. #sleep", None),
    ("Health", 11, 18, "note", "voice", "Physio exercises for the left knee",
     "Three sets of twelve: wall sits, step-downs, and the band walk. Ice after running, not before. Next "
     "appointment in three weeks. #knee", None),
    ("Health", 13, 9, "note", "typed", "Book the annual check-up before December",
     "Clinic opens bookings on the first of the month. Ask about the knee and a blood test. #appointments", None),
    ("Health", 4, 19, "journal", "voice", "Ran 5 km under 30 minutes",
     "Twenty-nine forty-two. Knee felt fine, kept the pace easy for the first two kilometres. #running", None),
    ("Health", 17, 21, "article", "url", "Zone 2 training, the basics",
     "Zone 2 is an easy, conversational pace where the body mostly burns fat. Most of a week's running should "
     "feel this easy; hard sessions stay short.\n\n- Roughly 60–70 % of max heart rate\n- You can still talk in full sentences\n"
     "- Three to four sessions a week\n\n#running", "https://runningnotes.blog/zone-2-basics"),
    ("Finances", 14, 20, "note", "typed", "Renovation budget",
     "Cap at $18,000 with a 10 % buffer. The quote is $18,340 before taxes, so the island or the backsplash has to give. "
     "See [[Contractor quote — Brightline Renovations]] and [[Quartz vs. butcher block countertops]]. #budget", None),
    ("Finances", 16, 12, "list", "typed", "Subscriptions to cancel",
     "- Second music app\n- The meal-kit trial\n- Cloud storage tier I no longer use\n\n#budget", None),
    ("Finances", 19, 10, "list", "typed", "Tax documents checklist",
     "- Employer slips\n- Childcare receipts\n- Donation receipts\n- Home office hours #taxes", None),
    ("Home", 20, 9, "note", "typed", "Furnace filter every three months",
     "Size 16 × 25 × 1. Last changed in September. Next: December. #maintenance", None),
    ("Home", 7, 18, "note", "voice", "Snow removal contact from the neighbour",
     "Lucie next door uses Dan's Snow Service, about 400 for the season, they start after five centimetres. "
     "Number is on the fridge magnet. #winter", None),
    ("Local-first software", 8, 21, "note", "typed", "CRDTs in plain words",
     "A CRDT is a data structure that two people can edit at the same time without talking to each other, and "
     "that always merges to the same result. No server has to decide who wins. Used by [[Automerge]]. #crdt", None),
    ("Local-first software", 9, 13, "article", "url", "Local-first software: you own your data",
     "An essay arguing that apps should keep the primary copy of the data on your own device, work offline, "
     "collaborate in real time and still let you keep your data for decades. It proposes seven ideals and "
     "points to CRDTs as the most promising foundation.\n\n- Seven ideals: fast, multi-device, offline, collaboration, longevity, privacy, user control\n"
     "- Cloud apps trade ownership for convenience\n- CRDTs make merging without a server possible\n\n#local-first #crdt",
     "https://www.inkandswitch.com/local-first/"),
    ("Local-first software", 8, 10, "article", "url", "Automerge",
     "A library of data structures for building collaborative applications: a JSON-like document that merges "
     "concurrent changes automatically and works offline.\n\n- Documents sync over any network\n- Full history of changes\n"
     "- Bindings for JavaScript and Rust\n\n#crdt #library", "https://automerge.org/docs/hello/"),
    ("Local-first software", 10, 15, "article", "url", "SQLite as an application file format",
     "Makes the case for using an SQLite database as the file format of a desktop application: atomic updates, "
     "incremental saves, queries for free and a format that will still be readable in decades.\n\n"
     "- One file, many tables\n- Transactions protect against crashes\n- Readable by many tools\n\n#sqlite #file-formats",
     "https://www.sqlite.org/appfileformat.html"),
    ("Local-first software", 4, 11, "idea", "typed", "Sync as a plugin, never a requirement",
     "The app must be complete on one machine. Sync can come later as an optional plugin, and the data folder "
     "stays readable without it. Good point for the [[Talk outline]]. #local-first", None),
    ("Local-first software", 9, 16, "quote", "typed", "You own your data, in spite of the cloud",
     "\"You own your data, in spite of the cloud.\" Subtitle of [[Local-first software: you own your data]]. #local-first", None),
    ("Local-first software", 6, 12, "note", "voice", "Chat with Priya about offline-first mobile apps",
     "Priya's team caches everything in SQLite on the phone and syncs a change log. Conflicts are rare in "
     "practice; the hard part is schema migrations on old devices. Worth a slide. #local-first #mobile", None),
    ("Cooking", 18, 19, "article", "url", "No-knead bread",
     "Flour, water, salt and a pinch of yeast, mixed in two minutes and left for 12 to 18 hours. Baked in a "
     "very hot covered pot for a crisp crust.\n\n- 430 g flour, 345 g water, 8 g salt, 1 g yeast\n- 18 hours at room temperature\n"
     "- 30 min lid on, 15 min lid off at 250 °C\n\n#bread #recipe", "https://slowkitchen.blog/no-knead-bread"),
    ("Cooking", 12, 18, "note", "voice", "Mom's tomato sauce, the way she says it",
     "Lots of olive oil, a whole onion cut in half, never chopped, two cans of whole tomatoes, a knob of butter. "
     "Forty-five minutes on low, take the onion out. Salt at the end. #recipe #family", None),
    ("Cooking", 3, 11, "list", "typed", "Meal plan this week",
     "- Monday: tomato sauce pasta\n- Tuesday: miso soup and rice\n- Wednesday: leftovers\n- Thursday: sheet-pan chicken\n"
     "- Friday: homemade pizza on the [[No-knead bread]] dough #meal-plan", None),
    ("Cooking", 21, 17, "list", "typed", "Pantry staples",
     "- Canned tomatoes\n- Rice, pasta, oats\n- Miso, soy sauce\n- Olive oil, butter\n- Flour and dry yeast #pantry", None),
    ("Productivity", 7, 16, "list", "typed", "Weekly review checklist",
     "- Inbox to zero\n- Look at every project\n- Pick three outcomes for the week\n- Archive what is done #review", None),
    ("Productivity", 20, 21, "article", "url", "The CODE method: capture, organize, distill, express",
     "Describes a personal knowledge workflow in four steps: capture what resonates, organize it by actionability "
     "(projects, areas, resources, archives), distill the essence, and express it in your own work.\n\n"
     "- PARA sorts by how actionable information is\n- Distill in layers, not all at once\n- Notes exist to be reused\n\n#para #pkm",
     "https://fortelabs.com/blog/basboverview/"),
    ("Productivity", 5, 8, "idea", "voice", "Capture by voice on walks",
     "Most of my ideas come while walking. Hold the key, talk for ten seconds, let the archivist file it. "
     "Review the Inbox on Sunday with the [[Weekly review checklist]]. #capture", None),
    ("Productivity", 15, 14, "quote", "typed", "Your mind is for having ideas",
     "\"Your mind is for having ideas, not holding them.\" David Allen. #capture", None),
    ("Apartment move 2025", 21, 10, "note", "typed", "Movers contact and invoice",
     "Two Brothers Moving, paid in full, invoice in the documents folder. #moving", None),
    ("Apartment move 2025", 21, 11, "list", "typed", "Change-of-address list",
     "- Bank\n- Employer\n- Health card\n- Library\n- Magazine subscription #moving", None),
    (None, 0, 9, "note", "voice", "The book Julie recommended",
     "Julie mentioned a novel at lunch, the one set in a lighthouse in the seventies. She said I would like the ending. "
     "Look it up.", None),
    (None, 0, 8, "note", "typed", "Heat pump rebate",
     "Ask whether the provincial heat pump rebate still applies this winter.", None),
]

INBOX_QUESTIONS = {
    "The book Julie recommended": "Do you remember the title or the author? Then I can file it under a reading list.",
    "Heat pump rebate": "Is this for the Home area or the Finances area?",
}

# Scripted summaries for the two files (what a summary model returns), by file name.
FILE_SUMMARIES = {
    "kitchen-quote": {
        "title": "Contractor quote — Brightline Renovations",
        "summary": "Quote #BL-2611 for a full kitchen remodel at 14 Maple Street: cabinets on two walls, a 4 × 6 ft "
                   "island, quartz countertops, a 40 A circuit for an induction cooktop and a tiled backsplash. "
                   "Total $18,340 before taxes, six weeks of work, paid in three milestones.",
        "key_points": ["Total: $18,340 before taxes", "Appliances not included",
                       "Panel upgrade quoted separately if there is no room for 40 A",
                       "Six-week schedule; countertops take 8–10 business days", "Two-year warranty on workmanship"],
        "tags": ["quote", "budget"],
    },
}
IMAGE_DESCRIPTION = ("A hand-drawn floor plan titled “Kitchen — new layout, v2”: counters and cabinets along the top wall "
                     "with the sink and an induction cooktop, a pantry wall on the left, a 4 × 6 island with three stools "
                     "in the middle, a door on the right and a note “fridge here?”. Notes say 1.1 m of clearance "
                     "and “40 A for the cooktop!”.")


class ShowcaseChat(FakeChat):
    """Scripted stand-in for the showcase (no network): English archivist answers and file summaries."""

    provider = "showcase"

    def embed(self, model: str, texts: list[str]) -> list[list[float]]:
        return [_embed(t) for t in texts]

    def complete(self, model: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None,
                 json_mode: bool = False, temperature: float = 0.4, effort: str | None = None) -> dict[str, Any]:
        usage = {"prompt_tokens": 100, "completion_tokens": 20}
        last = messages[-1]
        system = str(messages[0].get("content", ""))
        if isinstance(last.get("content"), list):
            return {"message": {"role": "assistant", "content": IMAGE_DESCRIPTION}, "usage": usage, "model": model}
        if json_mode and "fiche de référence" in system:
            src = json.loads(last["content"])
            known = "brightline" in str(src.get("text", "")).lower()
            out = FILE_SUMMARIES["kitchen-quote"] if known else {"title": src.get("title") or "Document", "summary": None}
            return {"message": {"role": "assistant", "content": json.dumps(out)}, "usage": usage, "model": model}
        if json_mode and "ARCHIVISTE" in system:
            return {"message": {"role": "assistant", "content": json.dumps(_file(json.loads(last["content"])))},
                    "usage": usage, "model": model}
        from engine import missions

        if tools and missions.is_mission(messages):
            return {"message": missions.scripted_reply(messages), "usage": usage, "model": model}
        scripted = _scripted(system, messages, [t["function"]["name"] for t in tools or []])
        if scripted is not None:
            return {"message": scripted, "usage": usage, "model": model}
        res = super().complete(model, messages, tools, json_mode, temperature, effort)
        content = res["message"].get("content")
        if isinstance(content, str) and not res["message"].get("tool_calls"):
            res["message"]["content"] = _english(content)
        return res


    def web_search(self, model: str, query: str) -> dict[str, Any]:
        return {"text": WEB_ANSWER, "sources": WEB_SOURCES, "usage": {"prompt_tokens": 100, "completion_tokens": 60},
                "model": model}


# ---------------------------------------------------------------- scripted conversations (English, for the website)
# They go through the real engine and tools (web_search, draft_synthesis, draft_agent); only the model is scripted.
# The wording follows what the real model answered in the owner's own tests.
WEB_ANSWER = ("Most electrical codes put an induction cooktop on its own dedicated 240 V circuit, usually 40 A for a "
              "standard 30-inch unit and 50 A for larger ones; the installation manual gives the exact rating.")
WEB_SOURCES = [{"title": "Induction cooktop circuit requirements — Electrical Safety Guide",
                "url": "https://example.org/guides/induction-cooktop-circuit"},
               {"title": "How to wire a cooktop: breaker and wire sizes", "url": "https://example.com/wiring/cooktop"}]
SYNTHESIS = {"title": "Talk opening: tell it as a story, no slides",
             "body": "## The idea\nOpen the local-first talk with the plane story, no slides for the first three minutes.\n"
                     "## Kept\n- The story makes the problem felt before it is explained\n"
                     "- The shared recipe card replaces the CRDT diagram\n"
                     "## Objections and answers\n- Without a diagram people lose the thread: the recipe-card analogy, "
                     "then one simple drawing\n"
                     "## Open questions\n- Does the analogy work for people outside tech?\n"
                     "## Next\n- Try the opening on two friends this week\n- Rehearse the network-unplug demo"}
TALK_COACH = ("You are Talk Coach. Your role: help the user rehearse the talk in [[Talk: local-first software]] until it "
              "flows without notes.\n\n"
              "## Tone and format\n- Demanding but kind: say what does not work, then how to fix it\n"
              "- Short spoken answers, two or three sentences, no lists out loud\n\n"
              "## How you work\n- Ask the user to deliver one part out loud, then react to it\n"
              "- Time each part against the 20-minute slot\n- Suggest one concrete improvement at a time\n\n"
              "## Avoid\n- Rewriting the whole talk for the user\n- Generic advice about public speaking\n\n"
              "## Your ground in the Brain\n- The place Talk: local-first software, and Local-first software for facts\n\n"
              "## Examples\n- \"Run me through the opening, I'll time it.\"\n"
              "- \"That demo transition was abrupt: say why you are unplugging the network before you do it.\"")
SPARRING_TURNS = [
    "Bold, and it can work: your [[Opening story for the talk]] already makes people feel the problem. The weak spot is "
    "the CRDT part, where a diagram usually carries the room. Without a slide, what will hold their attention there?",
    "A shared recipe card everyone edits at once is a good image: everyone has fought over one. I would still try it on "
    "someone outside tech first, because if the analogy needs explaining, it costs you the minute it was meant to save.",
]
BUILDER_TURNS = [
    "Happy to. What should its tone be: a demanding rehearsal coach, or an encouraging one? For example: "
    "\"tough but kind, short answers\".",
]


def _tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    return {"role": "assistant", "content": None,
            "tool_calls": [{"id": "call_" + name, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}


def _say(text: str) -> dict[str, Any]:
    return {"role": "assistant", "content": text}


def _scripted(system: str, messages: list[dict[str, Any]], names: list[str]) -> dict[str, Any] | None:
    """English answers for the website's conversations: web search, Sparring, the Agent Builder."""
    last = messages[-1]
    users = [str(m.get("content", "")) for m in messages if m.get("role") == "user"]
    low = users[-1].lower() if users else ""
    if last.get("role") == "tool":
        found = json.loads(str(last.get("content") or "{}"))
        if "answer_from_the_web" in found:
            return _say("From the web: a dedicated 240 V circuit, usually 40 A for a standard 30-inch cooktop and 50 A "
                        "for larger ones. Check the rating in its manual. Two sources below; want me to add one to your "
                        "kitchen project?")
        if found.get("draft_ready") and found.get("mode"):
            return _say("Here is Talk Coach: a demanding but kind rehearsal coach that knows your talk and times each part. "
                        "Shall I create it?")
        if found.get("draft_ready"):
            return _say("Here is the synthesis: the story opening, the recipe card instead of the diagram, and one test "
                        "this week. Shall I save it to your Brain?")
        return None
    if last.get("role") != "user":
        return None
    if "ÉLÉMENTS MENTIONNÉS" in system and "budget" in low:  # Loop 38: a question about @ mentioned items
        if "français québécois" in system:
            return _say("D'après [[Renovation budget]], la soumission est à 18 340 $, soit 340 $ au-dessus du plafond de "
                        "18 000 $. Dans [[Appliances shortlist]], la hotte avec sortie extérieure est la coupure la plus "
                        "simple; sinon, le dosseret, comme le suggère la note du budget.")
        return _say("From [[Renovation budget]]: the quote is $18,340, $340 over the $18,000 cap. In [[Appliances "
                    "shortlist]], the ducted range hood is the easiest trim; otherwise the backsplash, as the budget "
                    "note suggests.")
    if "web_search" in names and low.startswith("search the web"):
        return _tool("web_search", {"query": users[-1].split(" for ", 1)[-1].strip(" ?.")})
    if "Tu es Sparring" in system:
        if "draft_synthesis" in names and ("sum it up" in low or "synthes" in low):
            return _tool("draft_synthesis", SYNTHESIS)
        turn = sum(1 for u in users[:-1] if u.strip()) % len(SPARRING_TURNS)
        return _say(SPARRING_TURNS[turn])
    if "Agent Builder" in system and "draft_agent" in names:
        if "tough" in low or "kind" in low:
            return _tool("draft_agent", {"name": "Talk Coach", "instructions": TALK_COACH,
                                         "capabilities": ["read_brain", "interface"],
                                         "intro": "Ready to rehearse? Tell me which part, and I'll time it."})
        return _say(BUILDER_TURNS[0])
    return None


STOP = set("""about after again also back because been before being between both could does doing during each every
from have here into just like made make many more most much must only other over same should since some still such
than that their them then there these they this those through under very want was were what when where which while
with would your yours you'll it's i'll""".split())


def _embed(text: str) -> list[float]:
    """Content words only, hashed into 2048 dimensions: items share a direction when they share their subject."""
    import hashlib

    v = [0.0] * 2048
    for w in re.findall(r"[a-zà-ÿ0-9-]+", text.lower()):
        w = w.strip("-")
        if len(w) < 4 or w in STOP:
            continue
        w = w[:-1] if w.endswith("s") and len(w) > 4 else w
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 2048] += 1.0
    return v


KEYWORDS = [("kitchen", "Kitchen renovation"), ("cooktop", "Kitchen renovation"), ("electric", "Kitchen renovation"),
            ("talk", "Talk: local-first software"), ("crdt", "Local-first software"), ("sync", "Local-first software"),
            ("japanese", "Learn Japanese"), ("run", "Health"), ("sleep", "Health"), ("budget", "Finances"),
            ("recipe", "Cooking"), ("bread", "Cooking")]


def _file(ctx: dict[str, Any]) -> dict[str, Any]:
    it = ctx["item"]
    text = (it["title"] + " " + it.get("content", "")).lower()
    by_name = {p["name"]: p for p in ctx["places"]}
    name = next((n for k, n in KEYWORDS if k in text and n in by_name), None)
    links = [c["id"] for c in ctx["candidates"][:2]]
    if name is None:
        return {"title": it["title"], "item_type": "note", "language": "en", "confidence": 0.4, "place": {},
                "themes": [], "question": "Which place should this go to?", "receipt": ""}
    kind = by_name[name]["kind"]
    label = {"project": "Projects", "area": "Areas", "resource": "Resources"}.get(kind, kind)
    item_type = "article" if it.get("origin") == "url" else ("document" if it.get("origin") == "file" else "note")
    theme = "electrical" if any(w in text for w in ("electric", "circuit", "breaker")) else re.sub(r"[^a-z]", "", name.split()[0].lower())
    return {"title": it["title"], "item_type": item_type, "language": "en", "summary": None, "key_points": [],
            "entities": {"concepts": [theme]}, "place": {"space_id": by_name[name]["id"]}, "themes": [theme],
            "link_ids": links, "confidence": 0.94, "question": None,
            "receipt": f"A {item_type} on {theme} work, filed in {label} › {name}, linked to {len(links)} item"
                       f"{'s' if len(links) != 1 else ''}."}


def _english(text: str) -> str:
    if text.startswith("C'est fait") or text.startswith("Contexte"):
        return "Done."
    if text.startswith("J'ai trouvé: "):
        return "Found: " + text[len("J'ai trouvé: "):]
    if text.startswith("(test) Tu as dit: "):
        return "Noted."
    return text


def _at(days: int, hour: int, minute: int = 0) -> str:
    local = (datetime.now().astimezone() - timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if local > datetime.now().astimezone():
        local = datetime.now().astimezone() - timedelta(minutes=30 + minute)
    return local.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _date(conn: sqlite3.Connection, note_id: str, when: str) -> None:
    conn.execute("UPDATE notes SET created_at = ?, updated_at = ? WHERE id = ?", (when, when, note_id))
    conn.execute("UPDATE item_meta SET created_at = ?, updated_at = ? WHERE note_id = ?", (when, when, note_id))
    conn.execute("UPDATE sources SET created_at = ?, updated_at = ? WHERE note_id = ?", (when, when, note_id))


def _summary_of(body: str) -> tuple[str | None, list[str]]:
    paras = [p for p in body.split("\n\n") if p.strip() and not p.lstrip().startswith("#")]
    summary = paras[0] if paras else None
    points = [ln[2:].strip() for ln in body.splitlines() if ln.startswith("- ")]
    return summary, points[:6]


def seed_showcase(conn: sqlite3.Connection) -> bool:
    from engine.sources import core as sources

    brain.ensure_inbox(conn)
    if database.get_setting(conn, "seeded_showcase"):
        return False
    ids: dict[str, str] = {"Inbox": brain.INBOX_ID}
    for name, kind, color, _ in PLACES:
        ids[name] = brain.create_space(conn, name, kind, color=color)["id"]
    for name, _, _, area in PLACES:
        if area:
            conn.execute("UPDATE spaces SET area_id = ? WHERE id = ?", (ids[area], ids[name]))
    conn.execute("UPDATE spaces SET goal = ?, due_date = ? WHERE id = ?",
                 ("New kitchen before the holidays", (datetime.now() + timedelta(days=45)).strftime("%Y-%m-%d"), ids["Kitchen renovation"]))
    conn.execute("UPDATE spaces SET goal = ?, due_date = ? WHERE id = ?",
                 ("A 20-minute talk at the local meetup", (datetime.now() + timedelta(days=17)).strftime("%Y-%m-%d"),
                  ids["Talk: local-first software"]))

    client = ShowcaseChat()
    # Files first, so the notes that link to them by title resolve.
    quote = sources.ingest_file(conn, client, str(ASSETS / "kitchen-quote.pdf"), ids["Kitchen renovation"])
    sketch = sources.ingest_file(conn, client, str(ASSETS / "layout-sketch.png"), ids["Kitchen renovation"])
    brain.update_note(conn, sketch["note_id"], title="Kitchen layout sketch",
                      body=IMAGE_DESCRIPTION + "\n\nSee [[Open shelving on the window wall]]. #design")
    conn.execute("UPDATE sources SET title = 'Kitchen layout sketch' WHERE note_id = ?", (sketch["note_id"],))
    for nid, itype, theme, when, receipt in (
            (quote["note_id"], "document", ["quote", "budget"], _at(4, 14),
             "A quote for the kitchen remodel ($18,340 before taxes), filed in Projects › Kitchen renovation, linked to 2 items."),
            (sketch["note_id"], "image", ["design"], _at(8, 19),
             "A photo of a hand-drawn kitchen layout, filed in Projects › Kitchen renovation.")):
        meta = dict(item_type=itype, origin="file", language="en", themes=theme, confidence=0.96, filed=1, receipt=receipt)
        if itype == "document":
            meta.update(summary=FILE_SUMMARIES["kitchen-quote"]["summary"], key_points=FILE_SUMMARIES["kitchen-quote"]["key_points"],
                        entities={"organizations": ["Brightline Renovations"], "places": ["14 Maple Street"], "dates": ["October 30, 2026"]})
        archivist.save_meta(conn, nid, **meta)
        _date(conn, nid, when)

    for i, (place, days, hour, itype, origin, title, body, url) in enumerate(ITEMS):
        space = ids[place] if place else brain.INBOX_ID
        kind = archivist.NOTE_KIND.get(itype, "note")
        if url:
            src = sources.ingest(conn, None, "url", url, title, body, "text/html", len(body), space)
            nid = src["note_id"]
            brain.update_note(conn, nid, title=title, body=body + f"\n\nSource: {url}")
        else:
            nid = brain.create_note(conn, title, body, space, kind=kind, source="voice" if origin == "voice" else "typed")["id"]
        themes = re.findall(r"#([\w-]+)", body)[:3]
        summary, points = _summary_of(body) if itype == "article" else (None, [])
        if place:
            sp_kind = dict((n, k) for n, k, _, _ in PLACES)[place]
            label = {"project": "Projects", "area": "Areas", "resource": "Resources", "archive": "Archives"}[sp_kind]
            what = {"article": "An article", "note": "A note", "idea": "An idea", "list": "A list", "quote": "A quote",
                    "journal": "A journal entry"}[itype]
            subject = themes[0].replace("-", " ") if themes else title.lower()
            receipt = f"{what} about {subject}, filed in {label} › {place}."
            archivist.save_meta(conn, nid, item_type=itype, origin=origin, origin_uri=url, language="en", themes=themes,
                                summary=summary, key_points=points, confidence=round(0.86 + (i % 7) * 0.02, 2),
                                filed=1, receipt=receipt)
        else:
            q = INBOX_QUESTIONS[title]
            archivist.save_meta(conn, nid, item_type=itype, origin=origin, language="en", confidence=0.42, filed=0,
                                question=q, receipt=f"Received “{title}”. I left it in the Inbox: {q}")
        _date(conn, nid, _at(days, hour, (i * 7) % 50))
    # Wikilinks written before their target existed resolve now.
    for row in conn.execute("SELECT id FROM notes").fetchall():
        brain._sync_links_and_tags(conn, row["id"])

    from engine.assistant.core import today_conversation

    conv = today_conversation()
    for role, content in (
            ("briefing", "Since yesterday: 4 new items. 3 are filed (Kitchen renovation, Talk: local-first software, "
                         "Health). 2 items wait in the Inbox for one answer each."),
            ("user", "What do I have on countertops?"),
            ("assistant", "Two items: [[Quartz vs. butcher block countertops]] (an article, Kitchen renovation) and the "
                          "countertop line of [[Contractor quote — Brightline Renovations]]: quartz, 3 cm, $3,900.")):
        conn.execute("INSERT INTO assistant_messages (conversation, role, content, created_at) VALUES (?, ?, ?, ?)",
                     (conv, role, content, _at(0, 8, 5)))
    database.set_setting(conn, "seeded_showcase", True)
    database.set_setting(conn, "seeded_v2", True)
    return True
