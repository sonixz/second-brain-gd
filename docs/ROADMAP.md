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
| **7b — Real conversation** ✅ built 2026-11-03 (mini model by default; real run waits for model access) | Realtime speech-to-speech with interruptions, streaming replies, voice-driven project mode (F9). See docs/architecture/live-conversation.md | The owner enables `gpt-realtime-2.1-mini` on the OpenAI project |

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
| **9 — One intake for everything, with the archivist** | **Input record.** Every input becomes one **item**, which keeps the original (file or page, with a hash), its type, source and date.<br>**Pipeline.** Each item goes through the same pipeline: extract per type (text, voice, PDF, Word, Markdown, URL; images and email later), then Distill (title, summary, key points, language), then Organize (PARA place, themes, confidence; low confidence goes to the Inbox), then link by meaning, then index.<br>**Migration.** Notes and sources merge into this one model; the existing data migrates.<br>**The archivist.** The Brain's AI is a data-oriented archivist: no opinions, no challenge. It understands each input as well as it can (concepts, people, organisations, dates, document type) and **creates places and themes when none fit**, starting from an empty, broad PARA template. It asks only what is needed to file the input, and answers with a **receipt**: what it is, the summary, where it was filed, themes, links and confidence. « Je veux structurer le projet X » sets a working context for the next inputs.<br>**Fresh start.** A new Brain starts with the Inbox, a Getting started guide and an empty PARA skeleton. The default areas and demo data are gone (they stay in tests and screenshots only). The owner's current data is wiped (no backup) and setup is re-run from zero.<br>**Capture in one gesture.** Paste anything in the capture bar, drop files, use a clipboard hotkey, or tell the browser « Envoyer au Brain » (bookmarklet first, extension later).<br>**Captures feed.** A view of what came in: cards with summary, place and themes | « ajoute ça au Brain » (clipboard URL or text), « classe-le dans… », « qu'est-ce que j'ai ajouté aujourd'hui? » |
| **10 — The Graph first, deep zoom** | The Graph is home. Module tabs are hidden behind a Modules switch.<br>**Semantic zoom**, so the scale fades as you get closer: clusters by PARA and theme from afar; nodes and titles at mid range; cards with summary and themes up close; the **readable full text inside the node** very close.<br>A much wider zoom range, level-of-detail rendering for thousands of nodes, smooth zoom to the cursor, a minimap, and a visual pass | « zoome sur Atlas », « montre les thèmes », « ouvre cet article », « recule », « cherche… » (results light up in the graph) |
| **11 — Brain packs: export, import, share** | **Export** the whole Brain or a selection (a project, a theme, a search result) as a `.brain` file. It is a zip holding a SQLite subset (items, links, themes, vectors and the embedding model's name), the originals as an option, and a manifest (version, counts, checksum, author, licence).<br>**Import** a pack as a **layer** you can switch on or off, merge, or remove. Duplicates are found by content hash, and the pack is re-embedded if its embedding model differs.<br>**Restart a project** from a pack.<br>**Share** a pack by any means; a catalogue of packs comes later.<br>**Safety.** Imported text is data, never instructions, and checksums are verified. Packs never hold keys, because keys live in the OS keyring. The export preview shows exactly what leaves | « exporte le projet Atlas », « importe ce pack », « désactive le pack X » |
| **12 — Working conversations** (the assistant module, reborn) | Open a conversation on a subject, a project or a pack. It starts with the relevant items, and answers cite them. Templates for brainstorms and structure (« standards »). Results go back into the Brain as linked items. Live voice (F9) talks to the Brain | « on brainstorme sur… », « structure ça en plan », « garde ça dans le Brain » |

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
