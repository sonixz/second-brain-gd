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
| **7a — Hands-free** | UI tools for the assistant (open a view or a project, read aloud, confirm, undo, theme, volume), a push-to-talk key, spoken confirmation for destructive actions, a visible "listening" indicator | Wake word: local model choice (see below) |
| **6c — Agent room, on by default** ✅ built 2026-11-03 (real binary to verify) | One Godot agent room with interchangeable connectors: Codex (GPT, the user's existing OpenAI key) first, then Claude Code (Agent SDK, Anthropic key). Codex comes as official native Windows binaries (no Node.js): a visible "Agents" setup step downloads a pinned release, checks its SHA-256, stores it in the user data folder, needs no admin, and is resumable. If it fails or the machine is offline, the rest of the app works and the room says "Non disponible". Agents start with approval on every action, inside folders the user chose. The brain is exposed as an MCP server | Nothing (Windows sandbox without admin to verify) |
| **7b — Real conversation** | Realtime speech-to-speech with interruptions, streaming replies, voice-driven project mode | The owner's go on cost |

### Loop 7 — Real conversation (now 7a and 7b above)
- Realtime speech-to-speech with interruptions, streaming replies, and voice-driven project mode
  ("on travaille sur Atlas"). Same tools as the text assistant.

### Later
- MCP server so Claude Code, ChatGPT and other tools can read and write the brain.
- Packaged Windows build, prerequisites script (winget), offline and local models, licence, going public.

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
