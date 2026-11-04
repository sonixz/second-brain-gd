# Status

**Loop 7a — Hands-free: done (2026-11-03).** Hold **F8**, speak, release. The assistant hears you and answers
aloud, and she drives the interface: views (graph, today, projects, agents), a project's card, a note, the
theme, the volume, the weekly review, and « annule ça ». The engine validates every interface action, and
Godot performs it. A visible indicator shows when the microphone listens. A guard catches replies that
claim an action no tool performed, and asks the model once to act or correct itself.

| Real API (gpt-4o, 7-command spoken-style sequence) | Result |
|---|---|
| Open a project, show Today, open a note by meaning, theme and volume in one sentence | executed in every run |
| « Lance la revue », add a task, « annule ça » | executed in the last 3 runs. Once, the model asked which project the task belonged to (a fair question), then correctly said there was nothing to undo |

| Suite | Platform | Result |
|---|---|---|
| Python (125) | Linux 3.12 / Windows Store 3.13 | OK |
| Godot end-to-end (131, including pack export by voice, import by drop, layer removal, semantic zoom by voice, cards with full text, hidden modules, archivist receipts, new places, Captures view, clipboard capture, replay and voice speed by voice, « ouvre ma journée », F8 hold and release, listening indicator, real-costs panel, live conversation across a theme change) | Linux and Windows native | 131 passed |

**Loop 6c — Agent room, on by default: built and verified with the real Codex on Linux and Windows (2026-11-03).**
- **Setup:** a new step downloads the pinned official Codex app-server package (about 160 MB, about 0.4 to
  0.46 GB once unpacked). It checks the SHA-256 and unpacks it in the user data folder, with no admin rights. Offline, the step ends as "Not
  available", setup still succeeds, and the room offers a retry.
- **The Agents view** (next to Graph, Today and Projects): add folders, start an agent in one, and follow
  its messages, commands and file changes live. Every write or untrusted command shows an approval card
  (Approve, Approve for this session, Decline).
- **Tests:** the room is tested end to end against a fake app-server that speaks the documented protocol.
- **Real run (owner's go, 2026-11-03):** with the real package, `gpt-6-sol` and the owner's key, a turn
  under `untrusted` + `read-only` took about 11 s on Linux and on native Windows (PowerShell, no admin).
  Approve and Decline both work for commands and file changes. The key was never written to the Codex
  folder.

| Suite | Platform | Result |
|---|---|---|
| Python (85) | Linux 3.12 / Windows Store 3.13 | OK |
| Godot end-to-end (95, including the setup step, folder rules, a session, an approval and the applied change) | Linux and Windows native | 95 passed |

**Loop 6b — Responses API and gpt-6-astra: done (2026-11-03).** Reasoning models that cannot turn reasoning
off now use tools through the Responses API (`store: false`, reasoning passed back encrypted). The assistant
code is unchanged: `engine/assistant/llm.py` translates. The weekly review now uses `gpt-6-astra` (effort
low). If a user's OpenAI project lacks a configured model, the job falls back (review to gpt-4o, filing to
gpt-4o-mini), and the engine room shows one warning.

| Measured (real API, tools/model_bench.py) | Time | Verdict |
|---|---|---|
| Weekly review, gpt-4o | 3.5 s | Generic ("explore a new feature") |
| Weekly review, gpt-6-astra low | 10.6 s | Cites notes, links facts (the delayed Atlas demo and the late supplier call), sharp questions. **Default** |
| Weekly review, gpt-6-astra medium | 16.4 s | Barely deeper |
| Chat with tools, gpt-6-astra | 8.4 s | Correct; chat stays on gpt-4o (2.9 s) |

| Suite | Platform | Result |
|---|---|---|
| Python (75) | Linux 3.12 / Windows Store 3.13 | OK |
| Godot end-to-end (85) | Linux and Windows native | 85 passed |

**Loop 5b — Meaning memory: done (2026-11-03).** The embeddings model is now enabled. Every note is embedded
in the background (new or changed notes within seconds), related ideas are linked automatically (warm dashed
lines in the graph, a Related ideas section in the inspector), and search (the search box and the assistant)
uses meaning first, then words. Keyword search ignores common words and falls back to any word. Real API:
« habitudes pour mieux dormir » found nothing by words; by meaning the assistant cited the English note
“Bedtime routine”. Related-idea rule measured in `tools/meaning_bench.py`: 3 true pairs, 0 false.
`gpt-6-astra` measured: filing 10/10 in 2.7 s; it cannot turn reasoning off, and tools need the Responses API
(Loop 6b).

| Suite | Platform | Result |
|---|---|---|
| Python (68) | Linux 3.12 / Windows Store 3.13 | OK |
| Godot end-to-end (85 checks, including background meaning index and related ideas) | Linux and Windows native | 85 passed |

**Loop 6 (part 1) — Project mode: done (2026-11-02).** Each project has its own assistant instructions. In
project mode the assistant knows the card (goal, due date, next actions) and searches the project plus shared
resources first. Verified with the real API. The agent room (Claude Code sessions) needs an Anthropic API key.
Tests: 59 Python and 83 Godot checks.

**Loop 5 — Sources: done; meaning search waiting for the embeddings model (2026-11-02).** Drop files (PDF,
Word, Markdown, text, HTML) or paste a link. Each becomes a summarised reference note in the graph, with
searchable passages, and the assistant answers from them with citations. A real Wikipedia page took 3.5 s.
Meaning search was unblocked on 2026-11-03 (Loop 5b).

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
