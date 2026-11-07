# Plan: Loops 35 to 37 — missions, finished

Agreed with the owner on 2026-11-06. Follows docs/plans/plan-loops-32-34.md: the mission engine and card work and were
checked on real flyers. What is left is the part around them: setting the ceiling without the API, seeing what the
missions cost, a How-to guide recorded on the real model, and fixing what the owner finds when using it on their own
Brain.

Each loop: build, test (Python + Godot), review screenshots (English and French), document, merge to main, push,
short report in French.

---

## Loop 35 — Ceiling in the agent's settings, missions in the engine room

| What | How |
|---|---|
| Ceiling per agent | The agent's settings get a "Missions" block (shown when the Missions capability is on): maximum cost per mission, maximum minutes, model used for missions. Defaults stay 1 $ / 15 min / gpt-6-sol. Saved with the agent; a mission started without a ceiling takes the agent's, then the global one. |
| Missions in the engine room | A "Missions" list: date, agent, goal, status, rounds, minutes, cost; total this month. Clicking one opens it: plan, findings with their source links, the question and the answer given, the draft, the items saved. |
| A mission seen again | From the list, "Run again" starts the same goal with the same agent (the weekly menu next week). No automatic schedule: the user starts it. |
| Doubtful details shown | Findings keep the source link next to each price; the draft shows "source" on every special so a doubt (like the "avec carte" seen in Loop 34) is one click from being checked. |

Tests: ceiling saved and used by a new mission; list and totals from a seeded database; "Run again" creates a new
mission with the same goal; screenshots EN/FR of the settings block and the engine room list.

**Confidence 85 %.**

**Done 2026-11-06.** The agent's settings (ⓘ) show a *Missions* block with the Missions capability: at most N $ and
N min, the mission model ("Same model as the agent" by default); saved at once, used by the next mission
(`GET /missions/limits?agent=`). The engine room has a *Missions* card: this month's count, cost and minutes, each
mission with its status, rounds, minutes and cost; opened, its plan, findings with a « source » link each, the
question and the answer, the draft and the items saved; **Run again** (`POST /missions/{id}/again`). The mission rules
now ask for the source link next to every price in the draft. Found on the way: two quick changes in an agent's
settings (a capability, then the ceiling) were saved at once and the last one erased the other; saves now go one
at a time. Screenshots m4 and m5 (EN/FR), Docs updated.

## Loop 36 — How-to guide "Plan the week's meals with a mission", real answers

| What | How |
|---|---|
| Recording missions | `tools/howto.sh --record` also records the mission's model calls (today it records chat answers only), so the replay plays the whole mission without network or cost. |
| The guide | Goal, about 5 minutes, needs an OpenAI key. Steps: turn on Missions for the agent → "Mission…" → the goal → the plan advancing → the question (choose the specials) → the draft → approve → the recipes and the plan in the Brain → undo if needed. "If it does not work": ceiling reached, a store's site refuses the reading (403), no key. Badge **Real answers**. |
| Recording cost | One real run, ceiling 1 $ (Loop 34 runs cost 0.27 $ to 0.41 $), throwaway demo Brain. |
| Voice hand-over | A short second guide, scripted: in Live, "make this week's menu" starts the mission and the card appears. |

Tests: the guide replays without network and fails if a step no longer works; screenshots checked; How-to page and
Docs link updated.

**Confidence 80 %** (the recording of mission calls is the new part).

**Done 2026-11-06.** Guide `mission` (How-to, group Agents, 7 steps, **Real answers**): recorded once on gpt-6-sol
with the real web (Maxi flyer November 5–11 on circulaires.club and aubaine.ca, three RICARDO recipes): 15 rounds,
7 searches, about 0.52 $. Every price it noted (8) checked against the recorded pages. Replayed without network.
What the recording needed: a mission's calls are replayed in their own order (`mission:` kind), the guide's cost cap
per guide (1 $ for this one), and `SBGD_ENV_KEYS` so a worktree finds the main checkout's `.env.keys`.
Found on the way and fixed:
- a mission's cost left out its web searches (shown 0.33 $ for 0.52 $): their tokens and per-call fee now count,
  so the ceiling holds;
- costs recorded or replayed for a guide were shown as 0 $;
- the saved recipes showed raw Markdown (`**`, `[source](…)`) in the graph's card: the card now draws plain text.
The real model did not ask a question this time (the goal left no choice to the user): the guide says when it asks.
Not done: the separate scripted "voice hand-over" guide; the guide's troubleshooting says it can be asked in Live.

## Loop 37 — Fixes from the owner's real use

Starts after the owner has run at least one mission on their own Brain with Cuisin'Plan (method from
docs/agents/cuisinplan-method.md, Missions capability on, extension 1.1.0).

| What | How |
|---|---|
| What the owner reports | Read on a copy of the owner's database (never the live file): missions, rounds, costs, the question asked, the draft, what was approved or changed. Fix what went wrong in the rules, the card or the engine. |
| Uses past choices | A mission starts by searching the Brain for previous missions with the same goal (choices made, recipes kept or rejected) and mentions it in the plan, e.g. "last week you skipped fish". |
| A mission when the app is in the background | The question or the draft ready is announced with a Windows notification, not only the sound. |

**Confidence 75 %** (depends on what the real use shows).

---

## Owner decisions inside these loops
- Loop 35: is "Run again" enough, or a weekly automatic mission (it would spend without asking each week)?
  Default: "Run again" only.
- Loop 36: about 1 $ of real API spending for the recording. Default: yes, within that ceiling.
