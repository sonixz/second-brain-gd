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

## Next: voice capture with Whisper (proposed, not built)

Recommended design, consistent with local-first:

1. **Godot** records the microphone with `AudioEffectRecord` on a dedicated bus. Push-to-talk on the mic button
   (sounds `mic_start` / `mic_stop` already exist). It saves a 16 kHz mono WAV to `runtime/`.
   Project setting `audio/driver/enable_input = true` is required. Windows asks for microphone permission once.
2. **Engine** gets an optional component, "Voice", installed from the console on demand. It uses
   `faster-whisper` (CTranslate2) in the same venv. The model downloads once into `<data dir>/models/` from
   Hugging Face, with its size and source shown before the user accepts.
3. **API** gets `POST /brain/voice` (WAV upload). It transcribes in a worker thread and streams progress through
   `system_events`. It creates a note with `source = 'voice'`. A `voice_captures` table (migration 0003) keeps
   duration, model, language and the audio path, with an option to delete audio after transcription.

Choices the owner has to make:

| Choice | Options | Recommendation |
|---|---|---|
| Model size | `base` (~150 MB, fast on CPU), `small` (~500 MB), `large-v3-turbo` (~1.6 GB, best, wants a GPU) | `small` by default, `turbo` when CUDA is detected |
| GPU | CPU only, or CUDA (the owner has an RTX 3060) | CPU first, CUDA as a detected bonus |
| Languages | French and English mixed is fine with auto-detect | auto, with a preferred language setting |
| Cloud fallback | ElevenLabs Scribe (key already in dotenvx) | off by default, explicit opt-in per user (not local-first) |

## Later: daily router agent (direction)

A "daily" agent runs in the morning: it reads the Inbox, proposes a space for each thought, and suggests links.
Every proposal is written with `created_by = 'agent'` and shown in the briefing for approval. The graph can
show the agent as a visible actor moving between nodes, in line with the transparency principle.
