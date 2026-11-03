# Status

**Loop 5 — Sources: done; meaning search waiting for the embeddings model (2026-11-02).** Drop files (PDF,
Word, Markdown, text, HTML) or paste a link. Each becomes a summarised reference note in the graph, with
searchable passages, and the assistant answers from them with citations. A real Wikipedia page took 3.5 s.
**Blocked on the owner:** enable `text-embedding-3-small` on the OpenAI project (`proj_k45r…`) for search by
meaning. Until then, search uses words.

| Suite | Platform | Result |
|---|---|---|
| Python (59) | Linux 3.12 / Windows Store 3.13 | OK |
| Godot end-to-end (81 checks, including file drop, dedupe, refused local link) | Linux and Windows native | 81 passed |

**Loop 4 — Structure: done (2026-11-02).** Areas (Famille, Santé, Maison, Vision au travail) own projects
with goals, due dates and statuses. Next actions have dates. Checklists start with Épicerie. Today and
Projects views live next to the graph, and the assistant runs a guided weekly review. The assistant creates
projects, adds dated tasks, ticks them and fills lists. Grocery-like captures go straight to the list. Filing
uses gpt-6-sol, which scored 10/10 on real French captures.

| Suite | Platform | Result |
|---|---|---|
| Python (51) | Linux 3.12 / Windows Store 3.13 | OK |
| Godot end-to-end (78 checks, including Today, groceries, project card, dated task, weekly review) | Linux and Windows native | 78 passed |
| Model comparison (`tools/model_bench.py`, real API) | Linux engine | filing: gpt-6-sol 10/10, gpt-6-luna 10/10, gpt-4o 9/10, gpt-4o-mini 7/10; tools: all correct |

Known limits: French questions do not find English notes (words, not meaning) until Loop 5. gpt-6 prices
are unknown, so their costs show as "unknown".

**Loop 3 — The assistant: done (2026-11-02).** She briefs you when you open the app and reads the
briefing aloud with the marin voice and a Québec accent. She answers from your notes, citing them as
links, and acts on your brain through tools: create, move, edit. She files every capture automatically,
and everything she does can be undone. You can type or speak to her.

| Suite | Platform | Result |
|---|---|---|
| Python (41) | Linux 3.12 / Windows Store 3.13 | OK |
| Godot end-to-end (68 checks: briefing, cited answer, auto-filing with toast and undo) | Linux and Windows native | 68 passed |
| Real OpenAI run (briefing, chat with tools, filing, speech) | Linux engine | correct, about 3 cents per demo session |

**Loop 2 — Voice capture (bring your own key): done and verified against the real OpenAI API.** Loops 0 and 1 are done.

## Loop 2

- Onboarding step "Talk to your Second Brain" after the first setup: paste an OpenAI key, verified with OpenAI,
  stored in the OS credential store. It can be skipped.
- Mic button (Ctrl+M) in the capture bar. Live words appear while you speak, and a pulsing ring follows your
  voice level. The second click turns the speech into a voice note that blooms in the graph.
- Engine: `/voice/status|key|key/test|settings` and the `/voice/stream` WebSocket relay to OpenAI realtime.
- Engine room: a Voice card (model, key last 4, where it is stored, list price).
- `tools/voice-bench.sh` for real accuracy and latency measurements.

| Suite | Platform | Result |
|---|---|---|
| Python (33) | Linux 3.12 | OK, 1 skipped |
| Python (33), including the Windows Credential Manager round trip | Windows, Store Python 3.13 | OK |
| Godot end-to-end (62 checks, voice session through the real pipeline with the test provider) | Linux and Windows native | 62 passed |
| Real OpenAI transcription (`tools/voice-bench.sh`, full app path) | Linux engine | English 0 % word errors, first words about 1 s, final 0.4 s after release |
| Owner's own voice and microphone | Windows | **not tested yet** |

## Loop 1

## What works now

- **The Second Brain screen** is the main screen. A living force-directed graph shows spaces, notes and tags,
  with pan, zoom, drag and hover-to-reveal neighbours. New thoughts bloom with a sound.
- **Capture bar:** a thought becomes a note in the Inbox or the selected space. `[[links]]` and `#tags` work.
- **Morning briefing** shows what is new since the last visit and the inbox count. A greeting follows the hour.
- **Spaces** for projects and areas, a **note inspector** with autosave, connections and delete, and
  **full-text search** that lights up matching nodes.
- **Themes:** Morning (soft felted blue, default), Focus, Evening, Forest, plus Auto by time of day.
  The whole UI and the music follow the theme.
- **Audio:** 23 min of generated music (2 tracks per theme), 4 ambience loops, 14 interface sounds.
  Separate Music, Effects and Ambience volumes and mute live in the bottom-right ambiance panel.
- **Engine room:** the Loop 0 System Console, reachable from the brain's status pill.

## Test results (2026-11-02)

| Suite | Platform | Result |
|---|---|---|
| Python unit + integration (28) | Linux, Python 3.12.3 | OK (1 skipped: hostname resolves to loopback in WSL) |
| Python unit + integration (28) | Windows 11, Store Python 3.13.14 | OK |
| Godot load check | Linux, Godot 4.7.2 | no script errors |
| Godot end-to-end (54 checks) | Linux | 54 passed |
| Godot end-to-end (54 checks) | Windows native, Godot 4.7.2 + Store Python 3.13 | 54 passed |

The Godot test now also captures a thought through the real capture bar. It checks the new node, its tag and
its link in the graph, switches theme and music, and finds the note again after a restart.

## Known limitations

- Runs from the source checkout only, not as an exported build yet.
- Python must be installed by the user. A prerequisites script with winget is proposed in BACKLOG.
- Voice capture is designed but not built. The mic button is visible and disabled.
- Graph labels can overlap in dense areas. The layout is not saved between sessions.
- Music licence: generated with the owner's ElevenLabs account. Check the plan's commercial terms before
  distributing to businesses.
- No licence file yet.
