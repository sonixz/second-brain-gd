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

## Status (2026-11-05)

Done: the frame (H1), guides 1, 2, 3, 4, 5, 7, 8, 9, 10, 11 (ten guides, seven with real answers).
Recording all real guides used about 240,000 tokens (mostly gpt-6-sol, whose price the engine does not list),
three web searches and a few cents of gpt-4o / gpt-4o-mini; replaying is free.

Found and fixed thanks to the real runs: English items got French receipts and summaries; a path explanation came
back in French; "Re-read with AI" timed out after 4 s; the item tile slid in over the Archivist; the Captures list
slid under the docked panel; replies showed raw **bold**; an agent's creation read "Updated" with an Undo that
could not work.

Guide 6 (the browser), done 2026-11-05 with the owner's go: the Edge screenshots are the real Edge window
(`tools/howto.sh --edge browser`, driver `tools/howto/edge.ps1`: throwaway profile, no sign-in, closed and deleted at
the end). The real runs found and fixed: pairing never finished when “read the pages” was ticked (Edge's permission
prompt closes the popup, which was doing the pairing: it now runs in the service worker); “open the first one” after a
web search failed (the conversation history did not keep the links listed under a reply); a PDF tab could not be added
(Edge's viewer has no readable text: the engine now downloads it); hidden popup buttons showed anyway (CSS); a source
title with line breaks was squeezed into a narrow column; the app's “Connected” line kept a stale permission warning;
the receipt toast said “Ressources”; the popup had a French phrase. Recording the guide costs about 45,000 tokens.

## Decisions to confirm with the owner

- Guide 6: the owner wants Edge shown for real (no screenshots from them): done with a throwaway Edge profile, with
  their go (2026-11-05). Re-running it takes the screen for about three minutes: ask first.
- Budget: approved by the owner ("pas de problème").

## Loop 25: pictures (2026-11-05)

Guide "Keep the pictures that matter" (`tools/howto.sh --record --edge images`), captured in the real Edge: a page sent
with its main image and figures, the card's picture, the reading view, Edge's own right-click menu (a real right-click
through DevTools, the menu item clicked through UI Automation), the picture as an item, a question about it. The
real runs caught: the vision model described English pages in French (now told the page's language, from its
`<html lang>` or its words); the guides' recorded OCR answered for any picture with the insurance scan's text (it now
answers only for PDF pages, or for a picture recorded by its hash). About 45,000 tokens per recording.
