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
  401/403, and stores it with `keyring`: Windows Credential Manager, macOS Keychain or Secret Service. Without
  a credential store, a user-only file in `<data>/secrets/` is used. `OPENAI_API_KEY` from the environment is
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

## Later: daily router agent (direction)

A "daily" agent runs in the morning: it reads the Inbox, proposes a space for each thought, and suggests links.
Every proposal is written with `created_by = 'agent'` and shown in the briefing for approval. The graph can
show the agent as a visible actor moving between nodes, in line with the transparency principle.
