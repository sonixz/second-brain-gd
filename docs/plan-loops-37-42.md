# Plan: Loops 37 to 42 — missions in real use, @ mentions, folder import, routines

Agreed with the owner on 2026-11-06. The owner paces each loop (« je te cadence »); nothing starts without
their go. Each loop ends like the others: Python and Godot suites green, French for every new string,
screenshots where the UI changes, docs updated, committed on loop-32, merged fast-forward into main, pushed.

Order and why:
1. **Loop 37** first: the owner's real Cuisin'Plan missions decide what routines must remember and which
   output template a recipe needs.
2. **Loop 38, @ mentions**: small, asked for clearly, a quick win in daily use.
3. **Loops 39–40, folder import**: the owner's favourite of the brainstorm; independent of missions.
4. **Loops 41–42, routines**: they build on Loop 37 (remembered choices, notifications) and on the template
   seen in real use.

| Loop | Content | Size | Confidence | Waits on |
|---|---|---|---|---|
| 37 | Missions in real use: fixes, past choices, Windows notification, voice hand-over guide | 1 | 75 % | The owner's missions (part can start without) |
| 38 | @ mentions of Brain items | 1 | 90 % | — |
| 39 | Import A: import a folder (Obsidian, linked notes, Markdown) | 1 | 85–90 % | — |
| 40 | Import B: attachments, Logseq, Notion export, real vaults, guide | 1 | 70–75 % | The owner's tries on public vaults |
| 41 | Routines A: schedule, catch-up, output template, Routines card | 1 | 80 % | Loop 37 |
| 42 | Routines B: remembered answers, save directly, history, guide | 1 | 75 % | Loop 41 lived for a week or two |

---

## Loop 37 — Missions in real use

Details from docs/plan-loops-35-37.md (Loop 37), plus what was left from Loop 36.

- **What the owner reports.** Read their missions on a copy of their database (db, -wal, -shm copied to the
  scratchpad; never the live file): rounds, costs, the question, the draft, what was approved or changed.
  Fix the rules, the card or the engine accordingly.
- **Past choices.** A mission starts by searching the Brain for earlier missions with the same goal and
  what was kept or rejected, and says it in its plan (« la semaine passée, tu as sauté le poisson »).
- **Windows notification** when a question or a draft waits while the app is in the background (not only
  the sound). Without admin rights.
- **Voice hand-over guide** (left from Loop 36): a short How-to « Start a mission by voice ».
- **Can start before the owner's tests:** notification, past choices, guide. The fixes wait for their use.

**Owner's first real mission and talk (2026-11-06 evening), refocusing Loop 37:**
- Mission read on a copy of their DB: 9 items saved (6 real RICARDO recipes, menu, grocery list), 18 rounds,
  224 s, 1.01 $ (cap 1.00 $: the last round finishes). The instruction block was pasted as the mission goal (the
  agent's instructions were empty); the three Edge reads failed (extension 1.1.0 likely not reloaded), so only
  11 specials from one article; the owner answered the 12-choice question in free text.
- Owner direction: recipes first, grocery lists built from chosen recipes (not specials first); the agent as a
  kitchen assistant (« la paella, donne-moi les ingrédients » from their own recipe).
- To do: one input at a time during a mission (the Mission row closes, the chat field becomes « add a detail
  to the mission »); warn when an instruction block is pasted into the Mission field; structured recipe card at
  capture (schema.org Recipe read without AI: picture, servings, times, ingredients with quantities, steps,
  rating; ingredients as nodes); grocery list from chosen recipes (quantities added, by aisle).
- Ricardo spike (12 pages, 0 $): every recipe page carries a complete schema.org Recipe; listing pages carry
  rating and votes. Its terms forbid robots that access or index the site, but allow personal download with the
  source URL: capture stays user-driven (one recipe the owner opens), bulk import only for sources that allow it.
- **Done:** graph glides and rests (ff55318: no reheat on an unchanged refresh, fixed 1/60 s steps); **.zip
  import** (engine/sources/zip_import.py: safe unpack into <data>/imports/zips, nested Notion zips, size limits,
  links/absolute/../ refused; dropped or chosen zip opens the folder preview); file names with underscores read
  as titles with spaces (D&D SRD 5.1 zip: 1,021 notes, 778 of 779 links, imported in 1.2 s, < 0.01 $). Zip import on Windows (599b6b3): the
  app waited 4 s, unpacking took 5.2 s; imports now wait up to 10 min, « Stop » in the preview (nothing kept), the
  same zip unpacked once. Big graph after the SRD import (owner: « ça lag »; 1,065 items, 3,904 related edges):
  the push between items runs on a worker thread (14 ms → 2 ms on the frame), an unchanged 20-second refresh costs
  2 ms instead of 42, a big graph at rest redraws at ~20 fps, imported items get one plain ring and labels no
  shadow; a new item moves freely while the rest barely stirs (shaking 22 % → 2 % on the owner's graph).
- **Voice memos** (owner's idea, 2026-11-07: record ideas offline, drop the file at home). engine/sources/audio.py:
  length and recording date read from the file (MP4 mvhd, MP3 Xing/frames, WAV; a date in the name wins), preview
  with cost before anything is sent (and a free check that the key may use a transcription model), transcription
  with OpenAI (gpt-transcribe, falling back to gpt-4o-transcribe / mini, the working one remembered), then one chat
  call cuts the memo into ideas, tasks and notes (place chosen among the user's places), each linked to the memo
  with « vers 1:32 », all dated when recorded; the memo keeps the audio and the full transcript (searchable).
  .ogg/.opus/.aac are refused with a way out (no converter is installed). scenes/brain/audio_import_dialog.gd
  (several files or a folder of memos at once, Stop after the memo under way). The owner's OpenAI project allows
  no transcription model yet: to allow in Settings → Project → Limits before the first real memo.

## Loop 38 — @ mentions

**Done 2026-11-06.** engine/brain/mentions.py (suggest by title, no model; context block with each item's text,
6,000 characters each, 18,000 in all, chunks for documents; spoken « dans la recette du poulet, … » resolved
only when one item clearly matches). Chat, missions (« Run again » keeps them) and GET /brain/mention. In the
panel: the @ picker (arrows, Enter, click), chips with ×, « Answered from » after a spoken match, « Ask about
this » on a graph item. Tests: 7 Python (tests/python/test_mentions.py), 5 Godot checks. Screenshots
docs/screenshots/mentions-en and mentions-fr; docs.html#mentions.

- Typing `@` in the assistant or an agent's panel opens a picker of Brain items, searched as you type
  (title, then meaning). Chosen items show as chips in the message and can be removed.
- The chosen items are pinned as the context of that question: the answer comes from them and cites them;
  normal retrieval adds nothing unless asked.
- By voice: « dans la recette du poulet, … » or « avec la circulaire Maxi, … » resolves to the item (best
  match, confirmed on screen when unsure).
- In the graph: a selected node offers « Ask about this ».
- Works in missions too: « Mission… » with mentioned items starts from them.
- Tests: picker, chips, the pinned context sent to the model (recorded run), voice resolution.

## Loops 39–40 — Import a folder

Full detail in docs/plan-loops-import.md.

- **39 (Import A) — done 2026-11-06.** engine/sources/folder_import.py, POST /brain/import/scan and /run,
  scenes/brain/folder_import_dialog.gd, « + Folder », a dropped folder, and the voice tool ui_import_folder
  (« mon vault Obsidian » reads Obsidian's own vault list). Learned from real vaults and added: links in front
  matter (kepano style) and properties kept readable at the top; .base and attachment links are not notes;
  template folders and placeholders left out; a vault inside a subfolder; escaped pipes in table links.
  Measured: kepano/kepano-obsidian 51 notes, 55 of 96 links (the rest are notes its author never wrote);
  ObsidianStarterVault 102 of 103; obsidianmd/obsidian-help (local only, no licence) 1,682 of 1,686, 179 notes
  read in 0.07 s and imported in 0.19 s. Not done: « to create » nodes for missing notes (listed in the report
  instead), summaries at import (the archivist summarises on demand). Tests: 8 Python, 5 Godot checks.
  Screenshots docs/screenshots/folder-import-en and -fr; docs.html#folder-import.
- **39 (Import A), as planned.** « Import a folder… » and dropping a folder; detection shown, never put forward
  (« Obsidian vault detected »); notes, front matter, `[[links]]` (alias, heading), tags and folders read
  without a model; missing links as « to create » nodes; preview with counts and cost; a layer like packs;
  re-import adds only what changed; an honest report (links resolved and unresolved, with the list).
  Tests on a synthetic vault.
- **40 (Import B) — done 2026-11-06.** Pictures embedded in notes (wiki and Markdown embeds, found by path or by
  name anywhere in the vault, 12 per note) are kept as originals and attached to their item; its card shows the
  first (sources route: a note's main image). Markdown links between notes ([text](other.md), « ../ », URL
  encoding) resolve like wiki links. Logseq: page properties « key:: value », aliases, #[[tags]], namespaces
  (a___b), journal days, places Pages and Journals. Notion export: 32-hex ids taken out of titles and folders,
  the repeated « # Title » removed, links between pages kept (CSV rows: the pages already carry them). Cards hide
  picture embeds and show a link's alias. Measured on logseq/docs (MIT, pages only): 319 pages in 0.11 s, 977
  links resolved; the rest are pages Logseq makes implicitly. Guide « Bring your Obsidian vault » with our own
  sample vault (tools/howto/files/My vault, no third-party content). Tests: 4 more Python tests (12 in all) and
  one Godot check.
- **40 (Import B), as planned.** Attachments `![[…]]`; Logseq; Notion export; the owner's tries on public vaults
  (kepano/kepano-obsidian, SoRobby/ObsidianStarterVault and logseq/docs are MIT; obsidianmd/obsidian-help
  has no licence: local tries only); fixes from those tries; How-to guide « Bring your Obsidian vault ».

## Loops 41–42 — Routines

Full detail in the roadmap (« Next: routines, scheduled missions »).

- **41 (Routines A).** A routine = a mission on a schedule: when, agent, goal with variables, output
  template the engine enforces, where it lands in the graph, approval (draft that waits, by default),
  ceilings per run and per month, pause after two failures. Catch-up at the next launch when the PC was off.
  « Make it a routine… » on a finished mission; a Routines card in the engine room (next run, last run,
  month's cost, Pause, Run now). By voice: « chaque vendredi, … », « mets la routine épicerie en pause ».
- **42 (Routines B).** Answers remembered in the routine (« pas de poisson », « 4 portions »); save
  directly as an option once proven; the same items linked week to week (price history); How-to guide.
  A user-level Windows Task Scheduler start stays an option for later.

---

## After Loop 42 (roadmap, not scheduled)

- **Markdown mirror**, then edits coming back from the folder, then possibly files as the source of truth.
- **MCP server** so Claude Code and Claude Desktop can search and feed the Brain.
- **Data analysis and reports** (time entries, calendar).
- **Local model option** for sensitive or simple tasks.
- More import detections by demand (Evernote, Bear, Joplin, Day One, Google Keep, Roam).

## Owner actions still pending
- Restart the app; reload the Edge extension (1.1.0); paste docs/agents/cuisinplan-method.md into
  Cuisin'Plan's instructions; turn on its Missions capability; run real missions (Loop 37 input).
- From docs/audit-before-public.md: rotate the keys, decide whether .env stays versioned, ElevenLabs audio
  rights, third-party pages in recordings, the licence, a backups folder.
