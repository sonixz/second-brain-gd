# Plan: Loops 32 to 34 — missions for agents

Agreed with the owner on 2026-11-05. Goal: an agent can be given a **real job** ("this week's menu from the grocery
specials") and carry it through: a plan, visible progress, a question when it needs the user's choice, real sources
(never invented), a draft to approve, and the result kept in the Brain as linked items that have value later.

Why (seen in the owner's Cuisin'Plan session, 2026-11-05): in a live voice conversation the agent announced actions
without doing them, gave short answers and went round in circles. Causes:
- the voice model (gpt-realtime-2.1-mini) is small and built for speed, weak at chaining tools;
- voice pushes towards short answers;
- a chat message allows 8 tool rounds and 8,000 characters per page read: too little for a real job;
- a bug: the user's spoken sentences are not saved (0 user rows, 13 assistant rows in that conversation).

Principle: **voice is the remote control, the mission does the work.** The user starts, chooses and approves, by
voice or text; a strong model (gpt-6-sol by default) works in the background with its own budget.

Decisions already taken:
- Recipes are **found, not invented**: each one has its source link; the agent reads it before using it.
- About **60 %** of the chosen special ingredients used, "reasonable", not a puzzle to solve perfectly.
- Nothing goes into the Brain without the user's approval of the draft.
- Every mission has a **cost and time ceiling**; reaching it stops the mission cleanly, with what was found so far.
- Erasing stays impossible by voice; a mission never deletes anything.
- English first, French via the switch; every screen reviewed in both; How-to guide.

Each loop: build, test (Python + Godot), review screenshots (English and French), document, merge to main, push,
short report in French.

---

## Loop 32 — Voice fixes, then the mission engine

### 32a. Voice first (small)
| What | How |
|---|---|
| The user's spoken sentences are saved | Find why `conversation.item.input_audio_transcription.completed` gives nothing for the owner (transcription model, session refresh, event name); test on a recorded session; check on a copy of the owner's database. |
| Costs known for every model | The price tables match dated names (`gpt-4o-mini-2024-07-18` → `gpt-4o-mini`) and know `gpt-6-sol` / `gpt-6-astra`; "cost unknown" only for a truly unknown model. |
| Live does not pretend | Live instructions: never announce an action without calling the tool in the same turn; for a long job, start a mission (32b) instead. |

### 32b. The mission engine
| What | How |
|---|---|
| A mission, stored | New table (migration 0014): goal, agent, plan (steps with state: to do / running / done / skipped), findings (structured), pending question, draft, status (planning, running, waiting for you, draft ready, done, stopped, failed), cost, times. Survives closing the app: resumes where it was. |
| The runner | Background worker: the agent works step by step with the mission's model; budget about 40 tool rounds (instead of 8), page reads up to about 40,000 characters, cost and time ceiling (default 1 $ and 15 min, set per mission). Progress events for the app. |
| Tools for the agent during a mission | `plan_steps` (write or revise the plan); `note_findings` (structured rows: e.g. product, store, price, regular price, valid until, source); `ask_user` (a question with choices, checkboxes or one answer: the mission pauses until the user answers); `read_page_full` (longer read, also through the paired Edge extension, without adding the page to the Brain); `propose_draft` (the deliverable: notes, items, links, themes); `finish`. |
| Saving on approval | The draft becomes items in one step (one undo): e.g. each recipe as an item with its source link, ingredients and themes; the weekly plan as a note linked to its recipes; the grocery list. Linked to existing themes when they exist. |
| Starting a mission | From chat or voice: a `start_mission` tool ("make this week's menu"), available to agents with the new **Missions** capability. Live hands the job over and says it started. |
| API | `/missions` list, start, status, answer, approve (with edits), stop. |

Tests: a scripted model plays a whole mission (plan → findings → question → answer → draft → approval → items
linked); pause and resume after restarting the engine; ceiling reached → stopped cleanly with findings kept; voice
transcription saved; prices for dated names. Then one real run on the real model, small ceiling.

**Confidence 80 %** (mechanics), 90 % for 32a.

**Done 2026-11-06** (docs/architecture/missions.md).
- 32a: the cause of the lost sentences: the account no longer has access to `gpt-4o-mini-transcribe` inside a
  realtime session (`model_not_found`), and the failure event was ignored. Measured: only `gpt-realtime-whisper` and
  `gpt-live-transcribe` work now. The session tries them in order, switches on a refusal, remembers the one that
  works and shows a lost sentence in the chat. Checked on the real API (first sentence lost with the old model,
  second one transcribed and saved). Prices: gpt-6-sol / astra / luna from OpenAI's page, dated names matched.
- 32b: engine, API, the extension's background read (1.1.0: reload it), tests (12). First real mission: 13 rounds,
  56 s, 0.27 $, real specials and two real recipes with their links.

## Loop 33 — Missions in the app

| What | How |
|---|---|
| Mission card | In the agent's panel (dockable like the others): the plan with steps ticked as they go, a short feed of what the agent is doing ("reading Maxi's flyer…"), cost so far, **Stop**. |
| The question | Shown in the card with its checkboxes; answering resumes the mission. Voice: the agent reads the question out briefly and accepts a spoken answer. A notification when a mission waits for you. |
| The draft | Readable in full (recipes with their links, the plan, the list), **Approve**, **Change** (a sentence: the mission revises), **Discard**. |
| Agent settings | The **Missions** capability, its ceiling (cost, time) and model. |
| Engine room | Missions listed with their cost (running, waiting, done), next to the other costs. |
| Builder | Can write a mission method into a new agent's instructions. |

Screens reviewed in English and French; How-to guide "Give an agent a mission". **Confidence 80 %.**

## Loop 34 — First real mission: the weekly menu from the specials

| What | How |
|---|---|
| Cuisin'Plan's method | Instructions rewritten as steps: read the week's specials (IGA, Maxi, Provigo) → ask which ones tempt you → search real recipes using about 60 % of them → read each one → weekly plan + grocery list → draft. |
| Reading the flyers | Through the paired Edge extension (pages as the user sees them) when a site blocks robots or builds its flyer in JavaScript; through the web otherwise. Honest result per store: read / partly / not readable. |
| Real run | On the real model, the current week's flyers; cost and time measured; findings checked by hand against the flyers. |
| Recipes in the Brain | Checked after approval: items, links to ingredients and to the plan, source links work. |

**Confidence**: mechanics 80 %, real recipes with sources 75 %, **reading the flyers 55 %** (the fragile part: flyer
sites change and some are images). If a store cannot be read, the report says so plainly and the mission asks the
user (e.g. paste or photograph the flyer: pictures already go through OCR and vision).

---

## Possible blockers (none blocks starting)
- **Flyers**: some flyer pages are pictures or built by script; the Edge path and the "photo of the flyer" fallback
  cover most cases, not all.
- **The Edge extension must be connected** for the browser path: Reload it in `edge://extensions` (owner).
- **Cost of real runs**: each real test mission costs cents to about a dollar; kept small and reported.
- **Site terms**: reading a public flyer in the user's own browser for personal use; nothing is republished.

## What the owner can test meanwhile
- Cuisin'Plan in **text** mode for heavy requests (gpt-6-sol), voice for short questions.
- Reload the Edge extension.
