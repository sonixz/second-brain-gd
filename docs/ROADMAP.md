# Roadmap

Agreed with the owner on 2026-11-02. The guiding question: how does input (text, voice, files, links)
become structured knowledge that helps run a life and develop a vision at work?

## The mechanics we are building

A second brain needs two complementary things:

1. **Structure (PARA).** **Areas** are permanent responsibilities: family, health, home, vision at work.
   **Projects** have an outcome and a deadline, and each belongs to an area. **Resources** are reference
   topics shared across projects. **Archive** holds what is done. A project is a real card: goal, why,
   deadline, status, next actions, decision log, key resources, and its own agent instructions.
2. **Semantic memory.** Every source is extracted, summarised, chunked and embedded. The assistant then
   finds information by meaning and connects ideas across projects.

And five work loops the app supports:

| Loop | When | What happens |
|---|---|---|
| Capture | Any time | Text, voice, file, link land in the Inbox, with no decision needed |
| Process | Seconds, automatic | The assistant detects the type (task, idea, decision, reference, list item), summarises, files and links. Files and links are extracted and indexed |
| Triage | Each morning, 2 min | The briefing says what was filed and what is uncertain. One click validates, and the Inbox goes back to zero |
| Review | Each week | A guided review, project by project and area by area: progress, blockers, next actions, reflective questions for the vision |
| Express | When working | Open a project. Its agent knows the context, drafts and plans, and what it produces goes back into the brain |

## Next loops

### Loop 4 — Structure ✅ (2026-11-02)
- Migration: areas, and projects with goal, why, deadline, status (active, waiting, done) and
  `area_id`. Next actions are tasks linked to a project. Checklists support items, recurring lists, and
  the grocery case.
- The Inbox, spaces and existing notes migrate in place. Existing spaces become projects or areas.
- Godot: a **Today** view with next actions across projects, due soon and checklists. A **project card**
  view with goal, status, next actions, recent notes and decisions. The graph stays the exploration view.
- Assistant: new tools (create a project, add a next action, tick an item, list due items). The
  classifier understands tasks versus list items. A guided **weekly review** ritual.
- Seed areas from what the owner described: Family, Health, Home, Vision at work. All are editable.
- Models: compare `gpt-6-luna` and `gpt-6-sol` with `gpt-4o` and `gpt-4o-mini` on filing accuracy and
  answer quality with real data, then choose defaults. Both need `reasoning_effort: none` when tools are
  sent through Chat Completions, or the Responses API for reasoning with tools. Their prices are not
  known yet, so cost estimates must say so.

### Loop 5 — Sources & semantic memory (sources ✅ 2026-11-02; meaning search waits for an embeddings model)
- Drop files (PDF, Markdown, text, Word) and paste URLs. The engine extracts, summarises, chunks and embeds.
- Vector index in SQLite (`sqlite-vec` or a plain cosine table first). "Related ideas" become automatic
  links. Ask across everything.
- Needs an embeddings model enabled on the OpenAI project (for example `text-embedding-3-small`).
  A local embedding model is a later option.

### Loop 6 — Project agents (project mode ✅ 2026-11-02; agent room waits for an Anthropic API key)
- Per-project instructions and memory, sharing rules between projects (default scope is the project plus
  shared resources, with explicit "search everything" and walls such as Family and Work).
- **Agent room:** Claude Code sessions through the Claude Agent SDK, rendered natively. Permission
  prompts appear in the UI, and the brain is exposed as an MCP server. It needs an Anthropic API key per
  user, because claude.ai login is not allowed for third-party apps.

### Cadence from 2026-11-03

Order agreed with the owner: the loops that need no decision come first.

| Loop | Content | Blocked by |
|---|---|---|
| **5b — Meaning memory** ✅ 2026-11-03 | Embeddings are now enabled (`text-embedding-3-small`, FR to EN search measured). Embed notes as well as sources, show "related ideas" as automatic links in the graph, the assistant searches by meaning first, and the keyword fallback ignores common words | Done |
| **6b — Responses API and Astra** ✅ 2026-11-03 | A Responses API adapter so reasoning models can use tools. `gpt-6-astra` cannot turn reasoning off and refuses tools in Chat Completions. Use it for the weekly review and deep project syntheses. A per-model capability table replaces `startswith("gpt-6")` | Nothing |
| **7a — Hands-free** ✅ 2026-11-03 (F8 push-to-talk; wake word set aside) | UI tools for the assistant (open a view or a project, read aloud, confirm, undo, theme, volume), a push-to-talk key, spoken confirmation for destructive actions, a visible "listening" indicator | Wake word: local model choice (see below) |
| **6c — Agent room, on by default** ✅ 2026-11-03 (real Codex verified on Linux and Windows) | One Godot agent room with interchangeable connectors: Codex (GPT, the user's existing OpenAI key) first, then Claude Code (Agent SDK, Anthropic key). Codex comes as official native Windows binaries (no Node.js): a visible "Agents" setup step downloads a pinned release, checks its SHA-256, stores it in the user data folder, needs no admin, and is resumable. If it fails or the machine is offline, the rest of the app works and the room says "Non disponible". Agents start with approval on every action, inside folders the user chose. The brain is exposed as an MCP server | Done |
| **8a — Real costs** ✅ 2026-11-03 (to verify with the owner's admin key) | OpenAI's billed amounts and tokens, read live from the Costs and Usage APIs with an admin key restricted to "Usage API: Read". Daily stacked chart, per-model table, line items. Nothing is stored | Admin key from the owner |
| **7b — Real conversation** ✅ 2026-11-03 (verified live with gpt-realtime-2.1-mini) | Realtime speech-to-speech with interruptions, streaming replies, voice-driven project mode (F9). See docs/architecture/live-conversation.md | The owner enables `gpt-realtime-2.1-mini` on the OpenAI project |

### Loop 7 — Real conversation (now 7a and 7b above)
- Realtime speech-to-speech with interruptions, streaming replies, and voice-driven project mode
  ("on travaille sur Atlas"). Same tools as the text assistant.

### Later
- MCP server so Claude Code, ChatGPT and other tools can read and write the brain.
- Packaged Windows build, prerequisites script (winget), offline and local models, licence, going public.

## Refocus on the Brain (owner, 2026-11-03)

The app had drifted into a personal assistant: Today, tasks, projects, agents and the daily briefing.
The owner's definition of the product is:

> A tool that takes in context. You inject any data (URL, PDF, text, voice…). AI parses it and files it by
> theme, links it to the rest, and lets you find it again by meaning at any time. You then use the whole
> base to explore, ask questions, brainstorm and structure ideas, and what comes out goes back into it.

The method is **CODE**: Capture, Organize, Distill, Express. **PARA** is the skeleton: Projects, Areas,
Resources, Archives. Free themes and links by meaning go on top. The **Graph is the first module** and the
home screen.

Principles:
- **Today, Projects, Agents and the assistant are kept, but hidden as modules.** Nothing is deleted; they
  return through the module system later.
- **Everything works by voice, 100%.** Each loop below lists the spoken commands it adds. F8, F9, the
  voices and the API integrations all stay.
- **Structure every input before injecting data.** One intake, with the same structured record whatever
  the input type.

| Loop | Content | Spoken commands added |
|---|---|---|
| **8b — Voice fixes** ✅ 2026-11-03 | Concise spoken answers (1–2 sentences, detail on screen). A natural to brisk pace, with a speed setting, for both the read-aloud voice and the live voice. A **▶ Replay** button on every answer, which costs nothing because the audio is already cached | « relis-moi ça », « parle plus vite / moins vite » |
| **9 — One intake for everything, with the archivist** ✅ 2026-11-03 (see docs/architecture/intake.md) | **Input record.** Every input becomes one **item**, which keeps the original (file or page, with a hash), its type, source and date.<br>**Pipeline.** Each item goes through the same pipeline: extract per type (text, voice, PDF, Word, Markdown, URL; images and email later), then Distill (title, summary, key points, language), then Organize (PARA place, themes, confidence; low confidence goes to the Inbox), then link by meaning, then index.<br>**Migration.** Notes and sources merge into this one model; the existing data migrates.<br>**The archivist.** The Brain's AI is a data-oriented archivist: no opinions, no challenge. It understands each input as well as it can (concepts, people, organisations, dates, document type) and **creates places and themes when none fit**, starting from an empty, broad PARA template. It asks only what is needed to file the input, and answers with a **receipt**: what it is, the summary, where it was filed, themes, links and confidence. « Je veux structurer le projet X » sets a working context for the next inputs.<br>**Fresh start.** A new Brain starts with the Inbox, a Getting started guide and an empty PARA skeleton. The default areas and demo data are gone (they stay in tests and screenshots only). The owner's current data is wiped (no backup) and setup is re-run from zero.<br>**Capture in one gesture.** Paste anything in the capture bar, drop files, use a clipboard hotkey, or tell the browser « Envoyer au Brain » (bookmarklet first, extension later).<br>**Captures feed.** A view of what came in: cards with summary, place and themes | « ajoute ça au Brain » (clipboard URL or text), « classe-le dans… », « qu'est-ce que j'ai ajouté aujourd'hui? » |
| **10 — The Graph first, deep zoom** ✅ 2026-11-03 | The Graph is home. Module tabs are hidden behind a Modules switch.<br>**Semantic zoom**, so the scale fades as you get closer: clusters by PARA and theme from afar; nodes and titles at mid range; cards with summary and themes up close; the **readable full text inside the node** very close.<br>A much wider zoom range, level-of-detail rendering for thousands of nodes, smooth zoom to the cursor, a minimap, and a visual pass | « zoome sur Atlas », « montre les thèmes », « ouvre cet article », « recule », « cherche… » (results light up in the graph) |
| **11 — Brain packs: export, import, share** ✅ 2026-11-03 (see docs/architecture/packs.md) | **Export** the whole Brain or a selection (a project, a theme, a search result) as a `.brain` file. It is a zip holding a SQLite subset (items, links, themes, vectors and the embedding model's name), the originals as an option, and a manifest (version, counts, checksum, author, licence).<br>**Import** a pack as a **layer** you can switch on or off, merge, or remove. Duplicates are found by content hash, and the pack is re-embedded if its embedding model differs.<br>**Restart a project** from a pack.<br>**Share** a pack by any means; a catalogue of packs comes later.<br>**Safety.** Imported text is data, never instructions, and checksums are verified. Packs never hold keys, because keys live in the OS keyring. The export preview shows exactly what leaves | « exporte le projet Atlas », « importe ce pack », « désactive le pack X » |
| **12 — Working conversations** (the assistant module, reborn) | Open a conversation on a subject, a project or a pack. It starts with the relevant items, and answers cite them. Templates for brainstorms and structure (« standards »). Results go back into the Brain as linked items. Live voice (F9) talks to the Brain | « on brainstorme sur… », « structure ça en plan », « garde ça dans le Brain » |

### Graph loops (agreed 2026-11-03; modules are set aside entirely)

| Loop | Content |
|---|---|
| **12 — Originals and the document viewer** ✅ 2026-11-03 | `originals/` keeps every file and page. PDF pages render as images, sharper as you zoom, in the graph's cards and in a full-screen viewer. Images are inputs. Voice commands. Packs can carry originals. See docs/architecture/originals.md |
| **13 — An organised graph** ✅ 2026-11-03 | Each place gets a stable zone, and places can be folded and unfolded. Filters by type, theme, origin, date and pack. By voice: « replie Recettes », « montre seulement les articles sur l'IA » |
| **14 — Search and connect in the graph** ✅ 2026-11-03 | Results light up in the graph with the reason. The path between two items. Accept or dismiss a related idea. Edit text in the card |
| **15 — Large volume and timeline** ✅ 2026-11-03 | Thousands of items stay fluid (faster layout, only visible items drawn). A timeline view of captures |

## Next: routines, scheduled missions (owner, 2026-11-06)

A routine is a mission on a schedule, so a standard workflow runs by itself (« chaque vendredi, prépare les
soupers de la semaine avec la circulaire Maxi ») and lands the same structured data in the graph each time.
Planned after Loop 37 (notifications, missions using past choices) and shaped by the owner's real Cuisin'Plan
missions.

- **Settings.** When (weekly, monthly, a time); which agent; the goal with variables ({lundi}, {dimanche},
  {semaine}); the output template; where it goes in the graph (e.g. Recettes › Semaine {n}, linked to that
  week's flyer); approval (draft that waits, by default, or save directly once it has proven itself);
  ceilings per run and per month.
- **Standard output.** A fixed schema per routine (e.g. recipe: title, ingredients, price found, store,
  source link); the engine refuses a draft that does not match. Same items are linked to the new week, not
  duplicated, so history builds up (price of chicken at Maxi since September) and feeds the reports idea.
- **When the PC is off.** Catch up at the next launch first; a user-level Windows Task Scheduler entry (no
  admin) to start the engine in the background is a later option.
- **Unattended questions.** The routine reuses earlier answers (« pas de poisson », « 4 portions ») kept in
  the routine; otherwise the mission waits and a Windows notification tells the owner.
- **Safety.** Per-run and monthly ceilings; automatic pause after two failures in a row.
- **UI and voice.** « Make it a routine… » on a finished mission pre-fills everything; a Routines card in the
  engine room (next run, last run, month's cost, Pause, Run now). By voice: « chaque vendredi, … », « mets la
  routine épicerie en pause ».
- **Size.** About two loops: (1) schedule and catch-up, output template, Routines card, « Make it a
  routine », ceilings; (2) remembered answers, notification, save-directly mode, week-to-week history and
  links, a How-to guide.

## Next: @ mentions (owner, 2026-11-06)

Typing `@` in the assistant or an agent's panel offers Brain items by title (search as you type); the chosen
items are pinned as the context of that question, so the answer comes from them rather than from guessed
retrieval. By voice: « dans la recette du poulet, … » resolves to the item. Idea seen in
github.com/timskillet/second-brain (files only there); ours targets any Brain item. One loop.

## Later: data analysis and reports (brainstorm 2026-11-06, parked)

The owner wants this kept for later; the product focus stays on the Brain and missions for now.

- **Goal.** Any agent can analyse any data the owner drops (JSON, CSV, .ics calendar, Excel) and answer with
  an interactive, high-quality report. First real case: the owner's time entries and full calendar since
  2026-01-01 (« détaille-moi la semaine 14 : interne contre projet, les projets qui ont pris le plus de temps »).
- **Data.** A generic import into a local analysis base (DuckDB) that infers the columns. The agent gets the
  schema and sample rows; nothing is specific to time entries.
- **Compute.** Read-only SQL by default (exact, no file access). Model-written Python only in a sandbox
  (Pyodide, Python in WebAssembly in the browser sandbox, vendored in the repo), never run freely on Windows.
- **Numbers never come from the model.** Every figure comes from a query; a « Show the query » button under
  each chart; the agent reads its results before writing; « Run again for next week » replays the queries
  with no model call.
- **Display.** Vega-Lite specs (a general chart grammar) rendered by one polished, vendored template
  (palette, light and dark, tooltips, data table, clean PDF print), served by the local engine and opened
  in the browser. Free agent HTML and JS only in an isolated page (separate origin, no network, no access to
  the engine). In the app: a report card with key figures, and the report saved as a Brain node linked to
  what it covers.
- **Order.** Generic import and SQL tool, then Vega-Lite reports and a « Reports » agent capability, then
  sandboxed free HTML, then Pyodide only if SQL falls short on real cases.
- **Open questions.** The files' source tool and format; whether entry descriptions may be sent to the model.

## Model cadence (owner's OpenAI project, 2026-11-02)

| Use | Now | To evaluate in Loop 4 |
|---|---|---|
| Filing, quick classification | **gpt-6-sol** (measured: 10/10 French captures, 1.45 s; gpt-6-astra 10/10 but 2.7 s; gpt-4o 9/10; gpt-4o-mini 7/10) | — |
| Conversation with tools, briefing, weekly review | **gpt-4o** (correct with tools in 2.9 s; gpt-6 also correct but 4.4 s) | gpt-6 for the weekly review if depth matters more than speed |
| Weekly review, deep synthesis | **gpt-6-astra**, effort low, via the Responses API (10.6 s; it cites notes and links facts; gpt-4o is generic; medium effort is barely deeper) | — |
| Voice to text | gpt-realtime-whisper | gpt-live-transcribe (now enabled) |
| Text to speech | gpt-4o-mini-tts, voice marin, Québec accent | — |
| Embeddings | **text-embedding-3-small** (enabled 2026-11-03; FR question to EN source: 0.41–0.47, unrelated at most 0.16, floor 0.25) | Local model later |
| Images (later, e.g. project covers) | — | gpt-image-2.5-sunburst |
