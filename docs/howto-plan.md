# How-to guides: work plan

A **How-to** page on the website (`public/howto.html`), next to Docs. Docs explains how things work (reference);
How-to shows how to get one thing done, step by step, from the start to a visible result.

Everything on the website is in English, including the phrases you say to the agents.

## What a guide looks like

- A goal in one sentence, the time it takes, what you need (an OpenAI key, the extension…).
- 4 to 8 numbered steps. Each step: what you do (click, type or say), a screenshot of the real app at that moment,
  and what you should see.
- "If it does not work": the two or three usual causes.
- "Next": links to the related guides and to the Docs section.
- A badge per guide: **Real answers** (recorded from the real model) or **Scripted answers** (written for the guide).

## How the guides are made: captured, never drawn

`tools/howto.gd` drives the real app on a private virtual display (Xvfb, no window), like `tools/showcase.gd`.
Each guide is a script of steps: the clicks, typing and voice requests are simulated, the app and the engine are
real, and a screenshot is taken after each step. Re-running it after a change refreshes every guide, so they never
go stale, and a step that no longer works makes the run fail (the guides double as end-to-end tests).

The agents' answers come in two kinds:

| Kind | How | When |
|---|---|---|
| **Authentic** | `tools/howto.sh --record <guide>`: the real model (key through dotenvx, a throwaway demo Brain, a cost cap per guide) answers; the replies are saved to `tools/howto/recordings/<guide>.json`. | Archivist answers, web search, Sparring, the Agent Builder: anything where the model's real behaviour is the point. |
| **Replayed** | `tools/howto.sh <guide>` replays the recording: same answers, no network, no cost. | Every later refresh of the screenshots. |
| **Scripted** | Answers written in the guide script (as the website showcase does). | Steps where the answer does not matter (a receipt, a "done"). |

What cannot be captured: sound (voice steps show the sentence said and the answer shown) and the browser itself
(the extension guide shows the app side; the two browser screens are an extension popup rendered alone, or
screenshots the owner provides).

## The guides

| # | Guide | Steps (outline) | Answers |
|---|---|---|---|
| 1 | **Your first five minutes** | add a thought · paste a link · drop a PDF · read the receipts · see them in the graph · undo one | scripted |
| 2 | **Read a scanned PDF** | drop it · watch the page-by-page progress · open the reading view · re-read with AI (optional) | scripted |
| 3 | **Find your way in the graph** | zoom out to the zones · fold a place · filter by type · zoom down to the text · timeline | scripted |
| 4 | **Find how two ideas connect** | search by meaning · ask "how is X connected to Y?" · the path · keep a suggested link | authentic |
| 5 | **Search the web and keep a page** | ask a question · read the sources · "add the first one to…" · find it filed | authentic |
| 6 | **Connect your browser** | load the extension · pair with the code · send this page · send a selection · voice: open, add, close | app side captured, browser shown |
| 7 | **Think an idea through with Sparring** | open Sparring · F9 · challenge / reassure · "sum it up" · approve · find the synthesis | authentic |
| 8 | **Create your own agent** | + on the rail · the interview · the draft · "yes, create it" · talk to it · adjust in ⓘ | authentic |
| 9 | **Arrange your panels** | drag, dock, stack and share an edge · shrink to the rail · Ctrl+1–9 · Tab · reset | scripted |
| 10 | **Share a project as a pack** | export with a preview · import as a layer · switch off · merge | scripted |
| 11 | **Organise by voice** | "put my CVs in Job search" · link, unlink · delete a place · undo | authentic |

## Loops

Each loop: build, capture, look at every screenshot, test, document, commit and push; then a short report.

- **H1, the frame**: `tools/howto.gd` and `tools/howto.sh` (steps, captures, record and replay), the
  `howto.html` page (guide list, guide layout, badges, mobile), links from the home page and Docs, guides **1** and **9**.
- **H2, the Brain**: guides **2**, **3**, **10**.
- **H3, real answers**: recording with the real model (cost cap, throwaway Brain), guides **4**, **5**, **11**.
- **H4, agents**: guides **7** and **8** (recorded), guide **6** (browser screens to decide with the owner).
- **H5, review**: re-run every guide from scratch, check every screenshot and sentence against the app, a test
  that fails if a guide breaks, timing and cost of a full refresh noted in this file.

## Decisions to confirm with the owner

- Guide 6: render the extension's popup alone, or the owner takes two browser screenshots once.
- The cost cap per recorded guide (proposed: $0.25, about $2 for all of them).
