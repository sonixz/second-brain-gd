# Knowledge model (Loop 1)

## What is stored

Everything lives in `<data dir>/data/second_brain.sqlite3` (migration `0002_knowledge`).

| Table | Holds | Notes |
|---|---|---|
| `spaces` | projects, areas, resources, archive, plus the fixed `inbox` | PARA-style; colour and icon for the graph |
| `notes` | every piece of knowledge | `kind`: note, idea, task, journal, reference. `source`: typed, voice, import, agent, seed |
| `links` | directed edges between notes | from `[[Title]]` in a body today; `created_by` leaves room for agents |
| `tags`, `note_tags` | `#hashtags` parsed from bodies | unused tags are removed automatically |
| `notes_fts` | full-text index (FTS5) | accents-insensitive, prefix search, kept in sync by triggers |
| `application_settings` | `last_visit_at` (briefing), `seeded_v1`, `installed_at` | from Loop 0 |

`source` and `created_by` already distinguish what a human typed from what voice capture or an agent will add.
The UI can then show, and the user can undo, everything an agent did.

## Mechanics

- **Capture.** The capture bar creates a note in the Inbox, or in the selected space. Text longer than 80
  characters keeps a short title and the full text as body. `[[links]]` and `#tags` work in the capture bar too.
- **Links.** `[[Title]]` links to the note with that title, case-insensitively. When a note is created later
  with a title that other notes already reference, those links appear then.
- **Graph.** `/brain/graph` returns spaces, notes and tags as nodes. Edges are note→space membership,
  note→note links and note→tag. Godot lays it out with a force simulation. New notes bloom next to their space.
- **Briefing.** `/brain/briefing` compares with the previous visit: new notes, updated notes, inbox count, recent
  notes. It records the visit, so Godot fetches it once per session.
- **Search.** `/brain/search?q=` uses FTS5 with BM25 ranking, title weighted 4×. Results light up in the graph.

## API

All routes need the local bearer token.

```
GET    /brain/briefing           GET  /brain/graph
GET    /brain/spaces             POST /brain/spaces          {name, kind?, color?, icon?}
GET    /brain/notes?space_id=    POST /brain/notes           {title, body?, space_id?, kind?, source?}
GET    /brain/notes/{id}         PATCH /brain/notes/{id}     {title?, body?, space_id?, kind?, status?, pinned?}
DELETE /brain/notes/{id}         GET  /brain/search?q=
```

## Voice capture (Loop 2)

Owner's decision: each user brings their own OpenAI key. Voice uses the realtime transcription model
`gpt-realtime-whisper`, configurable. Typing works without a key.

```
Godot mic ──(AudioEffectCapture, 48 kHz stereo)──► VoiceCapture: mono, 24 kHz, PCM16
      └─► VoiceStream ──WebSocket ws://127.0.0.1/voice/stream (local bearer token)──► engine
                                                    engine ──wss://api.openai.com/v1/realtime?intent=transcription──► OpenAI
      ◄── delta / final text ◄────────────────────────────────────────────────────────┘
```

- **Key (BYOK).** It is entered once in the onboarding step after setup, or later from the mic button. Godot
  sends it to `PUT /voice/key`. The engine checks it for free (`GET /v1/models/{model}`), refuses it on
  401/403, and stores it in the Windows Credential Manager, called directly (`engine/voice/secrets.py`, no
  package since Loop 27; keys saved earlier by `keyring` are read as they are). Elsewhere (Linux, WSL), a
  user-only file in `<data>/secrets/` is used. `OPENAI_API_KEY` from the environment is
  the last fallback, for developers using `dotenvx run`. Godot clears the field at once. The key never appears
  in logs, events, SQLite or `/voice/status`, which shows only the last four characters.
- **Session.** The engine sends `session.update` with `type: transcription`, `audio/pcm` at 24 kHz, the model,
  `languages` (default `["fr","en"]`), `delay: "low"` and `turn_detection: null`. This model has no server VAD,
  so the client commits. Push-to-talk: the first click starts, the second click commits.
  Deltas fill the capture bar live. The final text becomes a note with `source = 'voice'`.
- **Observability.** Every session is written to `system_events` with its audio duration and an estimated cost
  at list price ($0.017/min). The engine room has a Voice card showing the model, where the key is stored and
  its last four characters.
- **Tests without a microphone or cost.** With `SBGD_VOICE_PROVIDER=fake`, set only by the tests, the engine
  uses a test double that reports the audio duration it received. The Godot end-to-end test pushes a
  synthetic tone through the real encoder, WebSocket and engine, and checks the voice note in the graph.
- **Real benchmark.** `tools/voice-bench.sh` streams the WAV clips from `tests/fixtures/voice/` in real time
  to OpenAI, through the same relay class. It reports word error rate, time to first words and time to final
  text, and can compare models (`--models a,b`). Clips come from the built-in Windows voices
  (`tools/make-voice-fixtures.ps1`). The ElevenLabs key is limited to sounds and music.

### Measured against the real API (2026-11-02)

The clips were streamed in real time in 100 ms chunks. The French clip is read by an English Windows voice, so
it tests robustness, not a real accent.

| Model | Clip | Word errors | First words | Final text after commit |
|---|---|---|---|---|
| gpt-realtime-whisper | English sentence (15 words) | 0 % | 1.2 s | 0.4–0.65 s |
| gpt-realtime-whisper | English sentence (10 words) | 0 % | 1.2 s | 0.4–0.7 s |
| gpt-realtime-whisper | French read by English voice, auto-detect | 43–57 % | 1.35 s | 0.4–0.6 s |
| gpt-realtime-whisper | same, `language: "fr"` | 29 % | 1.15 s | 0.4 s |
| gpt-live-transcribe | — | not available to the owner's project yet | | |

Facts learned:
- `gpt-realtime-whisper` refuses `languages`, the plural form. It accepts `language` (one code) and `delay`.
- The engine sends `language` when exactly one language is set. The default is auto-detect, which suits
  mixed French and English.
- The full app path was verified with the real key: verification, storage, streaming through the local
  WebSocket, deletion. First words after 0.93 s, final text 0.36 s after commit, transcription exact, key absent
  from every log.

## The assistant (Loop 3)

It uses the user's own OpenAI key, the same as voice. `gpt-4o` handles conversation and the briefing,
`gpt-4o-mini` handles classification. Both are configurable through `PATCH /assistant/settings`. The
owner's key currently allows only these two chat models.

| Feature | How |
|---|---|
| Morning briefing | `POST /assistant/briefing`. Facts (open tasks, new notes, inbox, oldest ideas) go to the model, which writes a 60–110-word spoken text. It is cached once per day and spoken with **marin** (Québec accent instruction) |
| Conversation | `POST /assistant/chat` with tools (`search_notes`, `get_note`, `list_spaces`, `list_notes`, `create_note`, `update_note`), up to 5 tool rounds. Today's conversation is stored in `assistant_messages`. The reply cites notes as `[[Title]]`, which become clickable links |
| Auto-filing | After every capture made outside a selected space, `POST /assistant/classify/{id}` proposes a space, title, kind, 0–2 tags and 0–2 related links. It is applied only above 0.6 confidence, and a toast offers Undo |
| Voice out | `POST /assistant/speak` uses `gpt-4o-mini-tts`, voice `marin`, with a tone per theme and a Québec accent. It returns MP3, cached in `runtime/tts/`. Music and ambience duck while it speaks |
| Voice in | The assistant panel has its own mic: speech goes to the chat instead of becoming a note |
| Transparency | Every change goes into `assistant_actions` with the state before it, and can be undone. Notes created by the assistant have `source = 'agent'`, links it adds have `created_by = 'assistant'`. Every call is logged in `system_events` with tokens and estimated cost |

Measured with the real API (2026-11-02): auto-filing took 1.3–1.8 s and was correct on three messy
French captures. The briefing took about 1.3 s, a chat turn with tools about 3 s, and speech about 5 s for
a briefing. A whole demo session cost about 3 cents.

## Structure (Loop 4)

Migration 0004 turns spaces into PARA cards: `goal`, `why`, `due_date`, `status` (active, waiting, someday,
done), `area_id` and `instructions`. Tasks are notes of kind `task`, with `due_date` and `done_at`.
`checklists` and `checklist_items` hold lists such as the grocery list. Four editable areas are seeded once:
Famille, Santé, Maison, Vision au travail, plus an Épicerie list.

| Endpoint | Purpose |
|---|---|
| `GET /brain/structure` | areas with their projects, loose projects, resources, archive |
| `GET /brain/today` | overdue, today, this week, next action per project, projects without one, inbox, checklists |
| `GET /brain/spaces/{id}/card`, `PATCH /brain/spaces/{id}`, `POST /brain/projects` | project and area cards |
| `GET/POST /brain/tasks`, `PATCH /brain/tasks/{id}` | next actions, done, due dates |
| `/brain/checklists…`, `/brain/checklist-items/{id}` | lists: add, tick, rename, delete, clear checked |
| `POST /assistant/review` | guided weekly review |

The assistant gained `get_today`, `get_structure`, `create_project`, `add_task`, `complete_task` and
`add_to_checklist`. All of them are journaled and undoable. The classifier sends list-like captures to a
checklist, and it now sees each space's kind, goal and area.

## Sources (Loop 5)

Drop files on the window, use **+ File** in the Spaces tab, or paste a web link in the capture bar.

1. **Extract.** Text, Markdown, CSV, JSON and HTML use the stdlib, DOCX is read through its zip XML, PDF uses
   PDFium (`pypdfium2`, which also renders the pages). Web pages are fetched over http(s) only. Local and private addresses are refused, so the engine
   cannot be used to probe the LAN. The limit is 15 MB.
2. **Dedupe.** A SHA-256 of the text means the same document is never added twice.
3. **Chunk.** Paragraph-aware passages of about 1,200 characters with overlap go into `source_chunks`, plus the
   FTS index `chunks_fts`.
4. **Summarise.** gpt-4o writes a title, summary, key points and tags. This becomes a `reference` note
   (`source = import`) in the graph, and is then auto-filed like any capture.
5. **Embed (optional).** Passages get float32 vectors from `text-embedding-3-small` when the OpenAI project
   allows it. Otherwise the refusal is recorded and retried at most every 6 hours.

Search (`/sources/search`, assistant tool `search_sources`) uses meaning first when vectors exist, and words
otherwise. The engine room shows sources, indexed passages and the embeddings status.

## Project mode (Loop 6, first part)

Each space has **assistant instructions**, edited on its card (tone, language, people, constraints). When the
assistant works in a project (the card's *Ask the assistant*, or a selected space), its system prompt includes
the card: goal, why, due date, status, open next actions, and those instructions. Search defaults to the project
plus shared resources, through `search_notes` with `space_ids`. It looks everywhere only when asked.

Real check: in "Client Atlas", with the instruction "the client is English-speaking, contact Mark Chen", a
follow-up email request in French produced an English email addressed to Mark.

## Later: daily router agent (direction)

A "daily" agent runs in the morning: it reads the Inbox, proposes a space for each thought, and suggests links.
Every proposal is written with `created_by = 'agent'` and shown in the briefing for approval. The graph can
show the agent as a visible actor moving between nodes, in line with the transparency principle.


## Meaning memory for notes (Loop 5b)

- `note_embeddings`: one vector per note (`text-embedding-3-small`, normalised float32, so cosine is a dot
  product), with the hash of title and body at embedding time. A changed hash means re-embed.
- A background worker (`engine/brain/meaning.py`, started in the API lifespan) embeds pending notes every
  30 s, and right after any write to `/brain`, `/assistant` or `/sources`. It reads, calls the API with no
  database lock held, then writes. Without a key, or when the model is refused, it does nothing, and the
  refusal is re-checked every 6 hours.
- `note_related(owner, other, score)`: each note's picks, which are its closest note if it scores ≥ 0.33,
  plus any note ≥ 0.45, up to 5. A pair is related when either side picked it. Adding a note also refreshes
  the picks of a note whose closest neighbour it becomes. Thresholds come from `tools/meaning_bench.py`.
- Served as `type: "related"` edges in `/brain/graph` (drawn as warm dashed lines), and by
  `/brain/notes/{id}/related` (the inspector's Related ideas section). `/brain/meaning/status` gives counts.
- Search (`/brain/search` and the assistant's `search_notes`): meaning first (floor 0.25), then keyword hits.
  Keywords skip common French and English words. If no note has every word, any word counts.
