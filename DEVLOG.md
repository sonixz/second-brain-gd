# Devlog

Entries from Loop 15 onwards up to 2026-11-07 are written from the commit messages, newest first. The plans behind them are in docs/plans/.

## VIEW-B: saved views (2026-11-10)

« ★ Views » in the graph's filter bar keeps what you see under a name: the view (Zones, Timeline), its filters and
where the camera was. Click a name and the filters come back, the layout changes and the camera glides there; a view
saved under an existing name replaces it; ✕ forgets one. They live with the app's preferences (`graph/saved_views`).
Not done yet: asking the assistant to open a saved view by name.
Tests: Godot end to end 283 (the engine is untouched).

## VIEW-A: the graph has a view picker (2026-11-10)

First loop of the plan for richer graph views (docs/plans/plan-graph-views.md), from the owner's wish for views that
are « plus avancées, plus étendues, plus mouvables ». The Timeline toggle in the filter bar becomes a view picker
(Zones, Timeline). Inside, layouts are a list (`GraphView.LAYOUTS`): the zones are the living simulation, every other
layout gives each item a target and the graph glides to it, so a new view is a small addition. Leaving the zones
remembers every position and coming back restores it. The assistant (« show the timeline »), the saved state, the
capture tools, the Docs and the How-to follow the picker; the How-to screenshot of that step still shows the old
toggle until the guides are captured again.
Tests: Python 350 (with the app's own environment), Godot end to end 282.

## Approving agents' proposals no longer freezes: instant approval, filing in the background (2026-11-08)

Owner's report: with many MCP proposals, « Approve all » showed nothing for 30 to 60 seconds, then everything updated
at once. Cause: one request applied every proposal in turn, and each one waited for the archivist to file it (one
OpenAI call each); the dialog gave no feedback and the button stayed live. Now an approval only creates the item (a
database write), the request answers at once, and the archivist files the items afterwards in a background thread,
each in its own transaction; the proposal's receipt is then updated with where the item went. Nothing is lost if the
app closes meanwhile: the items are already in the Inbox. The dialog disables the buttons and dims the rows as soon as
you click (« Approving 12… »), then shows « The archivist is filing the approved items: 3 of 12… » until it is done
(`GET /mcp/filing`). A test checks that approving makes no model call and that filing reaches 5 of 5.
Tests: Python 350 (with the app's own environment), Godot end to end 281.

## Three new built-in themes: Terminal, Paper, Neon (2026-11-07)

Ambiance → Theme now offers Terminal (green phosphor, a monospace font, square corners and nodes, dashed links on a
grid), Paper (the first light theme: warm paper, ink blue) and Neon (deep violet, pink and cyan, rounder, more glow).
A theme now brings its own style tokens as well as its colours (`THEME_STYLES`); new themes borrow the music and voice
tone of the first four (`THEME_SOUNDS`). A test checks every theme's contrast (WCAG ratio: text 7:1, secondary text
and accents 4.5:1). The light theme showed that Godot's white defaults for pressed, focused and icon colours were never
set: they now come from the theme, so a pressed tab stays readable on paper. Themes as folders and their import stay
parked.

## MCP fixes from a real session: accents through the WSL relay, retried proposals, one restore point (2026-11-07)

A tool connected from WSL proposed a note: its « — » arrived as « â€” » (the relay ran on Windows Python, whose
console reads cp1252); it now speaks UTF-8 both ways. The tool had sent its proposal three times and approving gave
three items: a proposal identical to one still waiting (same tool, same title) is now the same proposal. The three
approvals each made a restore point: one lock and the memory of the point just made keep it to one. The owner's
« go back » for that tool alone undid the three items cleanly.

## Themes, step 1: style tokens, the surface beyond colours (2026-11-07)

Fonts, text size, corners, borders, shadows, padding and the graph's look (circle or square nodes, solid or dashed
links, glow, stars, plain or grid background) now go through style tokens (`SbTheme.STYLE`, docs/architecture/themes.md).
The defaults are the app's own look: before/after captures differ only by the animation noise two runs of the same
build already show, and still screens are identical. `SBGD_STYLE=<tokens.json>` previews a style
(tools/style-preview/terminal.json: monospace, square, a grid). Step 2: themes as folders of data.

## MCP, not one tool: any AI tool connects, a generic guide for servers (2026-11-07)

The « Who may read your Brain » tab now asks which tool: Claude Code, Codex, VS Code (GitHub Copilot), Cursor or any
other MCP client, and shows its own way in (a command, through the stdio relay from WSL; the lines for mcp.json; or
the address and key). The How-to section is now « MCP: your AI tools »: « Connect an AI tool to your Brain » (shown
with Codex) and « Give your agents tools (MCP servers) », a generic guide with no model call that replaces the
Microsoft Learn example (Context7 is shown; Microsoft Learn moves to the end of the starters). Site and doc images
redone.

## UX-A/B/C: simpler settings — the AI tools window in two tabs, agent presets, one ⚙ entry (2026-11-07)

The MCP window becomes « AI tools and your Brain » with two tabs: « Who may read your Brain » (connected tools as cards with what each may do in plain words, proposals first, recent calls folded) and « Tools for your agents » (each server a folded card with its state in plain words; « Settings » opens its tools, key, monthly limit, writing with your model and « Remove this tool »; « Add a tool » below, a local program under « Advanced »). Labels no longer cut off; jargon reworded (« 0 = no limit », « read only », « apply its suggestions without asking me »). An agent's settings get three presets in one click (Read only, Assistant, Everything) and keep the tool names hidden until asked. The engine room puts « Start fresh » and « Uninstall » apart in a « Sensitive actions » box. A ⚙ button in the top bar leads to every setting: agents, AI tools, voice and key, theme and sounds, your data, the timeline. Nothing was removed.

## MCP-F: local MCP servers with approval, pinned versions, clean environment (2026-11-07)

A local server is a program the Brain starts on this computer and talks to over stdio. It is prepared from the catalogue or a pasted command, shown exactly, and runs only after « Approve and start »; a changed command needs a new approval. Versions are pinned (never latest), the runtime it needs is detected and never installed, the process gets a clean environment (no secret of the Brain; only the variables it declares, from the OS credential store), runs without a window, restarts after a crash, stops with the app, and keeps a short log.

## MCP-E: account sign-in (OAuth), server questions, sampling off by default (2026-11-07)

A server that answers 401 with a Bearer challenge shows « Sign in »: the Brain discovers the sign-in server, registers itself as a public client, opens the user's browser with PKCE and gets the answer back on a one-time 127.0.0.1 listener; tokens live in the OS credential store, are refreshed, and « Disconnect the account » revokes them. During a call a server can ask the user a question (elicitation), shown in the MCP window with its fields; asking the Brain's model to write (sampling) is refused unless the user allows it for that server, 20 times a month at most. Checked for real: Notion's discovery up to its sign-in page.

## MCP-D: keys, catalogue, tools on/off, budget, outside-write guard (2026-11-07)

Servers can carry a key (kept in the OS credential store, never in settings). The catalogue offers a hand-checked list (Microsoft Learn, Context7, DeepWiki, Exa) and a search in the official MCP registry, each entry with its family and publisher. Per server: tools on or off, a monthly budget, this month's calls and tokens. A tool that may write outside waits for the user's « Allow once » at each call, and the window warns when an agent reads the Brain and could write outside. The client follows paged tool lists, reads event streams as they come (progress on hover, Stop cancels), and speaks the older HTTP+SSE transport.

## MCP out: agents use remote MCP servers, Microsoft Learn first (MCP-C) (2026-11-07)

The Brain is also an MCP client (standard library, JSON or event-stream answers, sessions started again when a server forgets them). Servers the user connects in the MCP window — Microsoft Learn suggested — give their tools to all agents or to one, as mcp__<server>__<tool>, in chats and missions. Results are cut at 8,000 characters and marked as external data; destructive tools are not offered. The « ⇢ out » light turns green when a server is ready and red during a call. Tried for real: the archivist answered an Azure Functions question with two Microsoft Learn tools and cited them.

## Timeline of changes and restore points (MCP-B2) (2026-11-07)

Who changed what and when — you and the archivist, or an MCP client — with restore points made by hand or automatically before a client's first write of a session (plus a full backup once that write is committed). « Go back here » undoes every change after a point, newest first, for everyone or one author; an item changed by hand since is left as it is and listed; items created since go to the trash, never erased. Opened from the MCP window.

## MCP in, proposals: Claude Code proposes, the archivist decides (MCP-B1) (2026-11-07)

A client never writes. At its level it gets propose_item (an item the archivist files with the owner's rules) and propose_change (move to an existing place, link, unlink, set fields, trash; refused when the item changed since it was read). Proposals wait for the owner's approval in the MCP window (approve, reject, approve all; a count by the ⇠ light) unless the client is trusted; every applied action is journaled with its author, so Undo works for it too; receipts go back to the client (my_proposals). Rate limits: 60 a minute, 500 a day.

## MCP in, read: Claude Code can search and read the Brain (MCP-A) (2026-11-07)

The Brain is an MCP server (JSON-RPC over Streamable HTTP, standard library): POST /mcp on 127.0.0.1 only, a token per client kept as its hash, 11 read tools with short paged answers (overview, search, get_item, places, items of a place, neighbours, path, recent, inbox, item types, table), content marked as the user's data, the archivist protocol sent as the server's instructions. A stdio relay run with the app's Windows Python lets Claude Code in WSL reach it without any network setting. The « ⇠● ⇢● » lights in the top bar turn green when a tool is connected and red during a call; their window connects a tool (commands to copy, key shown once), disconnects it and lists recent calls. Tried for real: a Claude Code session searched and read a Brain over HTTP and through the relay.

## Letter export: recipes, grocery lists and notes as PDF (37D) (2026-11-07)

Any items print as a clean Letter (8½ × 11) page: a recipe has its facts, its kept picture embedded, ingredients beside numbered steps, rescaled for the servings asked; a grocery list prints as boxes to tick by aisle; other items as their text. Edge prints the PDF headless with a throwaway profile, no window (1.2 s on the owner's PC); without Edge the page opens for Ctrl+P. « PDF » in the table, « PDF for the fridge » in the grocery list, and by voice (« exporte la recette de paella en PDF »). Rewritten ingredient lines read as French (« 82 g de beurre », « 2 boîtes de 796 ml »).

## Table view and grocery totals (37C) (2026-11-07)

A « Table » tab shows the same items in rows and columns: pick a type (a recipe's fields become columns) or every item, search titles, fields and ingredients, sort by a column title, edit a cell in place, save the view, export CSV. Tick recipes and « Grocery list » adds their ingredients up at the servings chosen: converted to ml or g and summed, cans kept as cans with their size, grouped by aisle in shop order, nothing guessed. Saving makes a note linked to the recipes and fills the « Épicerie » checklist. By voice: « montre-moi en tableau mes recettes au poulet ».

## Typed items: recipes read from their page, types agents define (37B) (2026-11-07)

A type names the fields an item carries; values live in item_props as data the engine can sort, add up and export. The recipe is built in: a page captured by the extension or a pasted link that carries a schema.org Recipe becomes a recipe item without AI (servings, times, rating, picture, ingredients parsed into quantity, unit and name in French and English, cans with their size, steps with their sections), its text written from the fields. Agents can define their own types and save typed items; the assistant reads and rescales a recipe (« la paella pour 6 ») and edits fields; mission drafts carry type and fields.

## Voice memos: words in the app's language, screenshots, real run measured (2026-11-07)

The memo's title, « Transcript », « at about 1:32 » follow the FR / EN switch. ShowcaseChat scripts a memo for the screenshots (docs/screenshots/audio-memos-en, -fr). Measured with the owner's key once gpt-transcribe was allowed: a 29-second French memo, 4 items (2 tasks, the paella filed in Cuisine), 0.65 cents.

## Voice memos: drop a recording, get its ideas in the graph (2026-11-07)

A memo recorded anywhere (m4a, mp3, wav, mp4, webm) dropped on the window, chosen with + File, or a folder of them opens a preview: length and recording date read from the file itself (MP4 mvhd, MP3 Xing/frames, WAV, a date in the name), the estimated cost, and a free check that the key may use a transcription model. Each memo is transcribed by OpenAI (gpt-transcribe, then gpt-4o-transcribe or the mini when a project refuses one; the working model is remembered), then one chat call cuts it into ideas, tasks and notes, placed among the user's places, each linked to the memo with about when it was said, all dated when recorded. The memo keeps the original audio and the full, searchable transcript.

## Big graphs stay fluid: push on a worker, no work on unchanged refresh (2026-11-07)

After importing the D&D SRD (1,065 items, 3,904 related edges) the owner's graph lagged: each layout step took 14 ms on the frame and every 20-second refresh rebuilt everything (42 ms). Now, from 600 items, the push between neighbours is a pure function run on a WorkerThreadPool task (one step late; a step waits rather than reusing an old push), 2 ms on the frame. An unchanged refresh is skipped (2 ms); the edge signature is a sum computed while edges are read. A big graph at rest redraws at about 20 fps; imported items draw one plain ring, labels no shadow. A new item moves freely while the rest barely stirs.

## Zip import: no 4-second limit, unpack once, a Stop button (2026-11-07)

On Windows, unpacking the D&D SRD zip (1,021 notes) took 5.2 s and the app gave up after 4 s: « Impossible de lire ceci ». Folder and zip imports now wait up to 10 minutes; the preview has « Stop » while it works (also when closed), and the engine ends at its next file, keeping nothing (no commit, half unpack removed). The same zip is unpacked once for the preview, the toggle and the import. Refusals show the engine's words instead of « HTTP 422 ».

## Import a .zip of notes; underscore file names read as titles (2026-11-06)

- engine/sources/zip_import.py: a dropped or chosen .zip (a vault, a GitHub download, a Notion export) is unpacked into <data>/imports/zips/<key>/, never next to the download, then read by the folder import. Only notes, pictures, documents and .obsidian/logseq markers come out; links, absolute paths, drives and ../ are refused; sizes are counted while unpacking (1 GB in all, 200 MB per file, 60,000 files); zips inside the zip are unpacked once; unpacked folders are swept after a day; the same zip finds its layer. - A GitHub download's single top folder is used, shown without -main. - File names with underscores (Detect_Magic.md) are titles with spaces, and links match either way; place names lose underscores. On the D&D SRD 5.1 zip: 1,021 notes, 778 of 779 links resolved (265 before), 1.2 s. - Preview line: unpacked from « x.zip », your download stays as it is. - Voice: ui_import_folder accepts a zip (also found in Downloads). - Tests: 8 Python (GitHub zip, unsafe members, zip bomb, nested Notion zip, bad zip, sweep, voice path, underscores), 1 Godot (dropped zip preview). - Plan: the owner's first real mission and the Loop 37 refocus.

## Graph glides and rests: no reheat on unchanged refresh, fixed layout steps (2026-11-06)

The 20 s graph refresh reset the layout to full heat even when nothing had changed, so tiles moved again every 20 s (up to 116 px on the owner's graph). Slow frames ran one big step (delta x 60, up to 3), which overshot and made crowded tiles shake (27% direction reversals at 24 fps).

- set_graph reheats only when items or links changed, and gently (reheat(): heat climbs over about half a second); filters, folds and the layout switch use it too. - The layout advances in fixed 1/60 s steps (up to 3 per frame, 1 in big graphs), whatever the frame rate. - Lower top speed; an item at rest stops instead of trembling; the crowded-cell shortcut only applies from 600 items. - Godot check: settled graph has no shakes at 24 fps with hitches, an unchanged refresh moves nothing, a new item wakes it gently.

## Loop 40: pictures in notes, Logseq, Notion export, vault guide (2026-11-06)

Pictures embedded in imported notes are kept and attached to their item (its card shows the first). Markdown links between notes resolve like wiki links. Logseq graphs (properties, aliases, #[[tags]], namespaces, journals) and Notion exports (ids out of titles and folders) are detected and read. Cards hide picture embeds and show link aliases. New How-to guide « Bring your Obsidian vault » on our own sample vault. Measured on logseq/docs: 319 pages, 977 links. Python 279 OK, Godot 239/239.

## Loop 39: import a folder of notes (Obsidian vault, Markdown) (2026-11-06)

« + Folder », a dropped folder or « importe mon vault Obsidian » opens a preview that says what was detected (Obsidian vault, linked notes, Markdown) without putting it forward, with counts and cost. The import reads the structure without any model call: notes, front matter (kept readable, its links resolved), [[links]] the Obsidian way (folder, heading, alias, escaped pipes in tables), tags, folders as PARA places, template folders left out. It is a layer like a pack, and importing again adds only what changed. Measured on public vaults: 102/103, 55/96 (the rest by design) and 1,682/1,686 links resolved. Docs, EN and FR screenshots, 8 Python tests, 5 Godot checks.

## Loop 38: @ mentions of Brain items (2026-11-06)

Type @ in an agent's panel to pin Brain items to one question: a title picker (no model call), chips with x, and the answer comes from those items and cites them. Ask about this on a graph item, a spoken « dans la recette du poulet, … » when one item clearly matches, and missions that start from mentioned items (Run again keeps them). Docs, EN and FR screenshots, 7 Python tests and 5 Godot checks.

## Roadmap: routines, scheduled missions (2026-11-06)

## Roadmap: @ mentions of Brain items (2026-11-06)

## Roadmap: park the data analysis and reports idea (2026-11-06)

## Loop 36: How-to guide 'Plan the week's meals with a mission', recorded on the real model (2026-11-06)

- Recording: mission calls replay in their own order; per-guide cost cap; SBGD_ENV_KEYS for worktrees - Guide mission (7 steps, real answers): Maxi flyer Nov 5-11, three RICARDO recipes, about 0.52 $ - A mission's cost now includes its web searches (tokens and per-call fee); recorded/replayed costs shown - Graph item cards draw Markdown as plain text (SbFormat.plain)

## Loop 35: mission ceiling in the agent's settings, Missions card in the engine room, Run again (2026-11-06)

- Agent profile gets missions {max_cost, max_minutes, model}; GET /missions/limits; the next mission uses it - Engine room Missions card: month summary, per-mission status/rounds/minutes/cost, detail with source links - POST /missions/{id}/again; GET /missions returns a summary - Mission rules: source link next to every price in the draft - Agent settings saves one at a time (two quick changes erased each other)

## Loop 34: first real missions on the IGA, Maxi and Provigo flyers; a meal-planning method (2026-11-06)

Three real runs (gpt-6-sol): the three flyers read through flyer sites, 23 specials checked by hand against their pages, seven real recipes, four suppers with the grocery list, 0.41 USD. Mission rules: one choice per item in a question (they were grouped by store), prices and conditions copied as the page gives them.

## Loop 33: missions in the app (mission card, Mission… button, docs) (2026-11-06)

Every agent's panel has a Mission… button and a mission card: the plan ticked as it goes, what the agent is doing, the cost, Stop; the question with boxes to tick (a sound when it waits); the draft with Approve and save, Discard and Change; what was saved. An agent starting a mission from chat or voice opens its card. A long draft scrolls inside the card with its buttons in view. The fake model plays a scripted mission for the tests and the screenshots (English and French). Docs: Missions section.

## Loop 32b: missions for agents (engine, API, background browser read) (2026-11-06)

An agent can carry a longer job through in the background: a plan, structured findings, a question with choices (the mission waits), a draft to approve, then every item saved in one step (one undo), linked by [[titles]] and #themes. 40 rounds, a cost and time ceiling, resumes after a restart. New Missions capability: chat and live agents can start, follow, answer, approve, revise and stop missions. The Edge extension (1.1.0) reads a page in a background tab for missions (pages built by script, sites that block robots).

First real run (gpt-6-sol): 13 rounds, 56 s, 0.27 USD: this week's Maxi specials with links, the question asked, two real recipes read, a draft of 4 linked items.

## Loop 32a: Live saves what the user says again; costs known for gpt-6 and dated model names (2026-11-06)

The realtime session's transcription model (gpt-4o-mini-transcribe) became unavailable to the account: every spoken sentence failed with model_not_found, silently (0 user rows in the owner's live conversations). The session now tries transcription models in order, switches when one is refused, remembers the one that works, and shows a lost sentence in the chat. Verified on the real API.

## Live conversation follows the agent's settings changed while it is open (2026-11-05)

The owner switched Internet and Browser on for the Agent Builder during a live conversation: the session kept the tools and instructions it was opened with, so the agent kept saying it could not search the web. A live session now remembers a fingerprint of its agent's profile (instructions, capabilities) and the app's language; each time the user starts speaking it compares, and sends the new instructions and tools before the reply when they changed. The settings card and the docs now say changes apply from the next message, live conversations included. Tests: test_live (a capability switched on mid-conversation reaches the next reply; no extra update otherwise), Python 241, Godot 217/217.

## Engine room: open folders with a click (backups, database, storage, Python) (2026-11-05)

- Your data: the backups path is a read-only field you can select and copy, and "Open folder" opens it in the file manager (created first if no backup went there yet). - Every engine-room card: a value that is a folder or file on this computer (database file, data folder, virtual environment, base interpreter…) is shown as a link; a click opens the folder, or shows the file in its folder. - English and French; Godot checks for both (217/217), Python 239.

## Engine room: load the Your data panel by path (a blank engine room when Godot's class list was stale) (2026-11-05)

Running from the source without the editor, Godot's class list (.godot/global_script_class_cache.cfg) did not know the new DataPanel class, so system_console.gd failed to parse and the engine room stayed blank (seen by the owner on Windows). The panel is now preloaded by path; CONTRIBUTING says to run `godot --headless --import` after pulling.

## Loop 31: audit before opening the repository (2026-11-05)

- docs/audit-before-public.md: the whole history scanned (75 commits, all branches) for keys, tokens and sensitive files: only the tests' fake keys; the .env committed by design holds only dotenvx-encrypted values and its private key was never committed. Recommendations and a checklist for the owner: rotate the three keys, decide about versioning .env, check the ElevenLabs plan for the generated audio, two third-party pages kept in the How-to recordings, choose the licence, then (only the owner) the visibility. - Godot's licence and its components' notices were missing from the package: tools/package/licenses.gd writes LICENSES/godot.txt at build time; THIRD_PARTY_NOTICES.md (Godot, CPython, the 15 packages with their real licences read from their metadata, Codex on demand, content) is copied into every package. - README rewritten for newcomers (get it, keys and costs, what stays where, docs); CONTRIBUTING.md; docs: uninstall by hand; How-to page credits the web pages shown (Wikipedia CC BY-SA 4.0, Government of Canada). - Tests: Python 239, Godot 214/214. Nothing about the repository's visibility was changed.

## Loop 30: Your data in the engine room (backups, export, packs, repair, start fresh, uninstall) (2026-11-05)

- scenes/dashboard/data_panel.gd: one card in the engine room: last backup and its age, where backups go (with a plain warning while they share the Brain's disk) and Choose…, how often (6 h to a week, or off), the list with Restore…, Export everything / Import a backup file, Packs… (moved here from Captures), Repair the installation, Start fresh, Uninstall. Restoring, starting fresh and uninstalling need a typed word; uninstall keeps the backups folder by default and removes the data, the API keys and the app preferences, then quits. - Engine: export_file (one zip: database, manifest, files) and import_file (only its own entries, sizes capped, every file hashed against its name, verified before it is listed); installer --repair rebuilds the venv; voice tools backup_now / backup_status for the Archivist (restoring or erasing is never a voice action); rotation keeps the last 5 manual backups too (two in a day collapsed into one, seen in the screenshots). - English and French (766 texts); EN and FR screens reviewed: the typed-word dialog stretched to the full height (fixed), Godot's own "Cancel" translated, the restore message reworded, the export file named in local time. - How-to: new guide "Back up and restore"; the packs guide goes through the engine room. Docs: Backups section. Journal: Loops 29 and 30. - Tests: Python 239 (export/import round trip, tampered and foreign files refused, voice tools, repair), Godot 214/214 (back up now, list, typed word, restore, folder removal keeping backups).

## Loop 29: backups, restore and start fresh (the engine) (2026-11-05)

- engine/backups.py: consistent copy of the live database (SQLite online backup) with a manifest; originals copied once into a fingerprint-named store; every backup reopened and checked (checksum, quick_check, counts, files) before it counts, deleted otherwise; rotation 7 days / 4 weeks / 6 months + 30 days of safety copies, unused files removed; automatic backups every N hours (worker, first check a minute after start). - Restore: deep-verified backup, safety copy first (no copy, no change), files back, older backups migrated in a temporary copy, then the live database replaced in place; files of the replaced Brain removed. - Start fresh: safety copy first, a new Brain with its starter notes, originals cleared. - engine/appstate.py: browser pairing, bookmark capture key, the Brain's id and the last backup live outside the database (<data>/app_state.json, user-only), moved there on first read: restore and fresh keep them. - API /data/backups, /data/fresh (restore and fresh need a typed confirmation word). - Packs: page pictures (Loop 25) now travel in packs, their small files always included. - Tests: test_backups.py (restore into an empty folder identical, incremental files, fresh keeps a verified copy and the pairing, no backup no erase, damage and missing files caught, older schema migrated, rotation, GC, worker, path escape refused, appstate move, pack pictures). Python 235, Godot 207/207. Checked on a read-only copy of the owner's Brain.

## Loop 28: Python inside the app (Windows and Linux), agent room on demand (2026-11-05)

- tools/package/build.py: the app's own Python, a python-build-standalone CPython 3.12.15 pinned in tools/package/runtime.json (file + SHA-256, cross-checked with the release's SHA256SUMS), stripped (tests, Tk, IDLE, pip, duplicated links), with the locked wheels installed into its site-packages for the target platform (a Windows runtime builds on Linux). `app` adds the Godot export, the engine and the extension, zips it and writes SHA256SUMS. Windows runtime 50 MB, Linux 94 MB unpacked; Windows app zip 79 MB. - The installer recognises it (python/sbgd-runtime.json next to the interpreter): no virtual environment, nothing installed, the engine runs on that Python; a runtime built from another lock is refused. - Godot: the app folder is the executable's when exported; the app's own Python is the first candidate. - The agent room (Codex, ~160 MB) is no longer downloaded at setup, only when opened and the user says yes; an existing install is still checked (SBGD_AGENTS=install keeps the old behaviour for tests). - tools/package/check_runtime.py runs the real setup with a runtime: SQLite FTS5 + WAL, every migration, engine, /health. Linux 9.8 s; Windows 3.7 s on Windows. The exported Windows app (headless, autosetup, throwaway folder) found its own Python, set up, started the engine, which stopped with the app. - .github/workflows/package.yml: manual only; Godot and its templates pinned (SHA-512 checked); builds both packages, checks them (Linux on Ubuntu, Windows on a Windows runner), keeps them as artifacts, never publishes. - export_presets.cfg versioned (no secrets: since Godot 4.1 they live in .godot/export_credentials.cfg). - Docs: install from the package vs from the source. Tests: Python 221, Godot 207/207.

## Loop 27: fewer dependencies (27 -> 15 Python packages) (2026-11-05)

- keyring and the nine packages it pulled (cryptography, cffi, pycparser, jaraco x3, more-itertools, secretstorage, jeepney, pywin32-ctypes) replaced by engine/voice/secrets.py calling the Windows Credential Manager directly (ctypes). It writes and reads exactly as keyring did on Windows (names "<provider>@<service>" and keyring's older "<service>" naming, UTF-16 values, enterprise persistence), so existing keys are found as they are. Checked on Windows against keyring itself on test service names (read both ways, delete leaves nothing). The persistence matters: with another one Windows kept a second credential behind the first. Elsewhere (Linux, WSL) the private file, as before. - pypdf removed: PDF text comes from PDFium (pypdfium2, already used for pages). Same or better text on the sample PDFs (pypdf split some words of the kitchen quote into letters). - Lock regenerated with uv (universal, hashes); the 15 remaining packages keep their versions. A fresh venv from the lock runs every test: Python 214 OK (3 skipped instead of 9: the PDF tests now run), Godot 207/207.

## Edge extension in English and French; a false "no change" correction fixed; site images refreshed (2026-11-05)

- The extension follows the browser's language (_locales/en, _locales/fr): popup, right-click menu items, messages, its name and description. Checked in a real French Edge. - Real-model check of the FR / EN rule (gpt-6-sol): app in English + French message -> French; app in French + English message -> English; the briefing follows the app. It surfaced a real bug: a plain description such as « des notes reliées entre elles » was taken for a claimed change, and the engine's correction replaced a good answer with « aucun changement ». French claims now need an action form (« j'ai classé », « ont été détachés », « c'est classé », or a sentence opening « Classé dans… »), as the English already did. - Website: engine room, costs and the hero graph recaptured (tools/screens.gd also captures the costs card). "1 files" in the engine room now reads "1 file".

## Loop 26 follow-up: review of the other screens in French, How-to guides replayed (2026-11-05)

tools/screens.gd (SBGD_CAPTURE_SCRIPT=screens tools/showcase.sh): welcome, setup, Today, Projects, the agent room and the engine room, for reviewing a language. "Brain" capitalised in the last French texts. The ten replayable How-to guides replay unchanged after the translation work; their screenshots now show the FR / EN switch.

## Loop 26: English or French, one FR / EN switch for the whole app (2026-11-05)

English is the product's language; French is the other choice. Every interface text (about 690) is written in English inside I18n.t() (scripts/core/i18n.gd), its French in i18n/fr.json; tools/i18n.py --check fails when a text has no French or placeholders differ, and the tests run it. The FR / EN switch (top right of the welcome screen and of the Brain) rebuilds the screen in the chosen language, is remembered, and tells the engine.

The engine follows it (setting ui_language, English by default): the agents' default language (they still answer in the language spoken), the briefing and weekly review, the Live transcription (was forced to French), what the buttons say on your behalf, capability and model labels, the pack preview, the browser and bookmark receipts, fallback replies. The voice reads French with a Québec accent and English with a neutral one (was always Québec). French left in the English interface removed (Today's example, the project prompt, the bookmark page).

Checked by capturing every screen in French (SBGD_UI_LANG=fr tools/showcase.sh): placeholders shortened to fit. Tests: Godot FR / EN switch check, engine language tests, translation coverage test.

## Loop 25: pictures that matter, from web pages and by right-click in Edge (2026-11-05)

A web page brings its main image (shown on its card) and its figures, at most five; logos, icons, ads, menus and small pictures never. Chosen by the extension with real sizes, or from the HTML for a pasted link (engine/sources/images.py). Each is a kept original, deleted with its item; its caption, the text read in it locally and, for pictures that hold information (text, a diagram or chart caption, PNG), a vision description in the page's language are indexed with the page. The reading view shows them first, with captions. Right-click a picture in Edge -> "Send this image to the Brain": an item of its own that remembers its page.

How-to guide "Keep the pictures that matter", captured in the real Edge (Edge's own context menu included). The real runs caught French descriptions of English pages, and the guides' recorded OCR answering for any picture; both fixed. Migration 0013 (source_images). Tests: test_images.py, a WebP card check in Godot.

## How-to guide 6: connect your browser, shown in the real Microsoft Edge (2026-11-05)

The guide's Edge screenshots are the real Edge window: tools/howto.sh --edge browser drives a separate Edge (tools/howto/edge.ps1: throwaway profile, no sign-in, no sync, extension loaded from browser-extension/, DevTools on 127.0.0.1 and UI Automation for Edge's permission prompt; closed and its profile deleted at the end). Edge pairs, sends a page, and opens, adds and closes a tab when the Archivist is asked to.

Fixes found by the real runs: - pairing never finished with "read the pages" ticked: Edge's permission prompt closes the popup, which did the pairing; it now runs in the service worker (error shown when the popup reopens) - "open the first one" after a web search: the history now keeps the links listed under each reply - a PDF tab could not be added (Edge's viewer has no readable text): the engine downloads it - hidden popup buttons were shown anyway (CSS display overrode [hidden]) - a source title with line breaks was squeezed into a narrow column - the app's "Connected" line kept a stale permission warning; next steps shown once paired - the browser receipt said "Ressources"; the popup had a French phrase

## How-to guides H2-H5: ten guides on howto.html, seven with the real model's answers; fixes found by the real runs (2026-11-05)

- Guides: Read a scanned PDF, Find your way in the graph, Share a project as a pack, Find how two ideas connect, Search the web and keep a page, Organise by voice, Think an idea through with Sparring, Create your own agent (plus the first two). Every guide replays offline; a broken step fails the run. - Recordings keep web pages (gzip) and no pictures; a token check per recorded guide. - Fixed, each with a test: "Re-read with AI" timed out after 4 s (job id in the query); a path explanation came back in French to an English question; the item tile slid in over the Archivist; replies showed raw **bold** (now bold, and read without the stars); related ideas suggested items already linked; an agent's creation read "Updated" with an Undo that could not work; the minimap sat under right-docked panels; a document's title said "- English". - Website: Loop 24 in the journal, How-to linked everywhere, screenshots recaptured; docs explain how to regenerate the guides. Guide screenshots (PNG) are no longer committed, only the site's WebP.

## How-to H1: guides captured from the real app, real answers recorded once and replayed; first two guides (2026-11-05)

- tools/howto.sh + tools/howto.gd: each guide is a scenario on the real app (Xvfb, no window), a screenshot per step; tools/capture_base.gd shared with the website showcase. - engine/assistant/recording.py: SBGD_ASSISTANT_PROVIDER=record keeps the real model's answers, web searches and downloaded pages; replay serves them back offline, remapping item ids from run to run. - SBGD_OCR=recorded replays a real Windows OCR reading (sample scan made with render_page.ps1). - tools/howto/guides.py (text, checks, cost cap) and build_page.py generate public/howto.html. - Guides: "Your first five minutes" (real answers) and "Arrange your panels". - Found by the real run and fixed: the Archivist wrote French receipts and summaries for English items (now the item's language; English place labels in the interface); the Captures list slid under the docked panel; a file's origin read "Document · Document". - Buttons that speak for you (approve, create, the rail's +) follow a voice/language setting (fr default).

## Website up to date and English only: agents, Internet, extension, panels; journal loops 16-23; How-to plan (2026-11-05)

- Landing page: new Agents section (Archivist, Sparring, Agent Builder, settings tile), Internet and browser feature, panels; every screenshot recaptured from the real app; roadmap and stats updated; journal entries for loops 16-23 with an Agents phase; every French phrase translated. - Docs: all spoken examples in English; Codex agent room renamed so it is not confused with agents. - The engine understands the English phrases the site shows: approvals and refusals (synthesis, agent creation), false-success and clipboard guards; agents answer in the user's language. - App text: English quotes instead of « », the bookmark is named "Send to Brain", agent drafts show headings as capitals. - Showcase: scripted English conversations through the real engine (web search, Sparring synthesis, Agent Builder draft), new shots 17-21. - docs/howto-plan.md: the How-to guides and the loops to build them.

## Agent settings in a movable tile: on/off switches per capability, model, name, first words, instructions (2026-11-04)

Owner: ⓘ was a read-only box. Now it opens a floating tile (same style, movable, dockable, shrinkable, ✕ to close): name, model (gpt-6-sol, gpt-6-astra, gpt-4o, gpt-4o-mini), each capability an iPhone-style on/off switch with its tools listed (saved at once), first words (custom agents), editable instructions (Save), « Ask the Builder to change it… » (hands over by voice), Back to the original / Delete. GET /assistant/agents also returns each capability's tools and the models. - Title bars are lighter: speaker and info icons (new SVGs) instead of « Voice » text and a missing ⓘ glyph; a docked edge is never narrower than its panels' title bars, so the graph toolbar is no longer covered. - Tests: tile opens, switching Internet off saves at once, model change, instructions saved. Showcase shot 16 shows the settings tile.

## Loop 3: the Agent Builder interviews you, writes rich instructions, and creates or changes an agent on your yes (2026-11-04)

- A built-in Agent Builder (B) with a new capability « Manage agents » (list_agents, get_agent, draft_agent, save_agent): one short question at a time (purpose, tone, behaviour, what to avoid, places, capabilities, examples), then structured instructions (20-50 lines), a name, an intro and capabilities (read-only by default; organising only when asked). draft_agent refuses thin instructions; save_agent creates or applies only on approval (no « non / change »). - ui_open_agent lets any agent hand over (« crée-moi un agent » to the Archivist opens the Builder; « passe-moi Sparring »). - App: « + » at the bottom of the always-visible rail opens the Builder; the draft shows in full (NEW AGENT · NOT CREATED YET / CHANGES · NOT APPLIED YET) with Create it / Apply it and Change it…; on creation the new agent's panel appears. Non-archivist agents answer in plain text (no Markdown). - Real check (gpt-6-sol): a three-question interview produced a rich « Coach Entrevue » (DevSecOps/Azure, made for spoken practice in the car), created on « oui, crée-le ». - Tests: builder capability, interview → draft → refusal → create, changing an agent needs rich text and approval, archivist hand-over; Godot: « + » opens the Builder, draft shown before creation, agent panel on yes. Docs and README.

## Loop 2: agents are profiles with capabilities; ⓘ shows instructions; panels follow the stored agents (2026-11-04)

- engine/assistant/agents.py: seven capabilities group all 51 tools (+ synthesis); a test fails if a new tool joins none. Profiles (name, letter, colour, instructions, capabilities, model, intro) stored in the « agent_profiles » setting; Archivist and Sparring are built-in profiles that can be adjusted and reset; custom agents can be created and deleted. Synthesis rules are added when the capability is there; drafts are per agent; custom models fall back to gpt-4o. - Chat, live and history take any agent id; GET/POST /assistant/agents, PATCH /agents/{id}, POST /agents/{id}/reset, DELETE /agents/{id}; /assistant/draft?agent=. - App: every agent is a floating panel built from its profile (refresh_agents adds new ones on the rail, removes deleted ones); ⓘ in each title bar shows model, capabilities (✓/—) and instructions, with Back to the original or Delete; Ctrl+5… for custom agents; the synthesis draft opens in the panel of the agent that wrote it. - Tests: capabilities cover every tool, adjust/reset, custom agent tools/conversation/model, deletion fallback; Godot: new agent panel on the rail, ⓘ, deleted panel goes. Docs: what an agent is.

## Loop 1: Sparring rephrases only when the idea is long, vague or unclear; varied openings (2026-11-04)

Owner noticed it restated every message (« Tu hésites entre… »), tiring over a 20-minute spoken session. The persona now goes straight to a view, an angle or an objection, rephrases only when needed, and never opens two replies the same way. Checked on four real replies (gpt-6-sol).

## Panels, modern handling: drop preview, gliding moves, splitter between stacked panels, icon rail, Ctrl+1-4, Tab for the graph alone (2026-11-04)

- While a panel is dragged, the place it would land (left, right, bottom) lights up; moves and size changes glide (0.18 s), except at start-up, while dragging and in tests. - Panels on the same edge share it by weight; the line between two is a splitter (weights remembered). - A shrunk panel leaves the layout and waits as a letter on a rail at the left edge (A, S, P, I); a click opens it again. The graph toolbar moves aside for the rail. - Ctrl+1 Archivist, Ctrl+2 Sparring, Ctrl+3 Places, Ctrl+4 the item tile: open (and talk to that agent) or shrink; Tab on the graph shrinks every open panel and brings the same ones back. - Opening an item reveals its tile even if it was shrunk; reset keeps a closed tile closed. - Tests: rail, toolbar, drop preview on/off, dock, float, remember, splitter, Ctrl+2 both ways, Tab both ways, reset. Docs: « Arranging the panels ».

## Sparring: a thinking partner agent that argues, never changes the Brain, and saves a synthesis only on approval (2026-11-04)

- engine/assistant/agents.py: agent profiles (archivist, sparring): persona, allowed tools, model setting, own conversation per day. Sparring reads the Brain, documents and the web; its tools exclude every graph-changing one (enforced in chat and in live). draft_synthesis keeps a pending synthesis; save_synthesis is refused unless the user's message asks to save or approves (no « non / change »); the archivist then files it as an idea, undoable. - Chat and live (F9 ?agent=) take the agent; history per agent; GET /assistant/draft. Setting sparring_chat_model (gpt-6-sol, fallback gpt-4o). - App: a SPARRING floating panel (own conversation, intro, Voice/Live in its title bar); the synthesis shows in full (« SYNTHESIS · NOT SAVED YET ») with Save to the Brain / Change it…; F8 and F9 talk to the agent you last used (● in its title); the live pill names Sparring. - Real check (throwaway brain, gpt-6-sol): replies in 2-3 s, a real challenge, and « synthétise et enregistre » saved a structured synthesis filed in Recherche d'emploi. - Tests: role/model/tools/conversation, cannot change the graph, save only after approval, one-go save, live tool set; Godot: active agent, draft shown, saved on approval, separate history. Docs: « Archivist and Sparring ».

## The archivist's briefing is about what the Brain holds, not tasks (2026-11-04)

Owner: « Il est là pour accueillir de l'information », not a to-do list. The briefing no longer reads overdue items, due dates, next actions or checklists. knowledge_facts(): what came in since the last visit and where it went (by place, by origin, examples), what waits in the Inbox, the most active places this week, growing themes, one strong related-ideas pair not yet decided, one item to rediscover, the places. The prompt forbids tasks and deadlines, says what came in, at most one interesting thing, then 2-3 concrete leads (explore a place, brainstorm a project, clarify links) and an open question; an almost empty Brain is invited to take in information. Checked with the real model on a throwaway brain.

## Floating panels: the Archivist, Places and the item tile move, dock, shrink, resize and remember their place (2026-11-04)

- SbFloatingPanel: drag by the title bar; dropped with the cursor near the left, right or bottom edge it docks there, elsewhere it floats; – or double-click shrinks it to its title bar; bottom-right grip resizes; place saved per panel (settings « panels »). - SbPanelLayer: panels on the same edge share it (a shrunk one keeps only its bar), bottom dock between the side docks, free panels kept on screen; the graph toolbar, legend and centre move into the free area. - The left column is split: ARCHIVIST (the conversation; Voice and Live in its title bar) and PLACES · TODAY (briefing, places, sources, now scrollable; shrunk by default under the archivist). The item tile on the right is a floating panel too. « Reset the panel layout » in Places. - « Assistant » is now « Archivist » in the interface. - Tests: docking by default, toolbar follows, drag to the middle floats, drop near the right edge docks, remembered, shrink, reopen, reset.

## Browser extension (Edge, Chrome): send the page you see, and let the assistant open, add and close tabs by voice (2026-11-04)

- browser-extension/ (Manifest V3, Chrome 116+/Edge): popup to pair, send the page or the selection; Alt+Shift+B; right-click menus; service worker with one WebSocket to 127.0.0.1 (engine pings every 20 s, alarm reconnects), commands open/capture/close limited to tabs the Brain opened or the tab named; reads pages with activeTab on click, optional <all_urls> only for voice capture; icons from the logo. - engine/browser/: one-time pairing codes (8 chars, 10 min, single use, 5 attempts) exchanged for a dedicated token stored as a hash, revocable; Hub bridging assistant tool threads and the WebSocket with timeouts; routes /browser/pair/start, /pair, /status, DELETE /pair, WS /browser/ws, POST /browser/capture. - sources.ingest_page: the tab's HTML kept as the original, readable text without page chrome (visible text for app-like pages), text_engine=browser; PDFs/protected tabs fall back to downloading. - Assistant tools open_web_page (system browser without the extension), capture_browser_tab (commits before waiting), close_browser_tabs; persona rules for « ouvre-la », « injecte-la », « ferme-la ». - App: Captures → Send from browser… now pairs the extension (code, port, live status, unpair); the app polls /browser/status, refreshes the graph and announces pages from the browser; open_url UI action. - Tests: pairing, hub, page ingestion, tools; an extension stand-in drives a real engine through pair → WS → open → capture → close → unpair. Verified that Edge loads the unpacked extension and starts its service worker. - Docs: full Browser extension guide (install, pairing, use, permissions and why, how it works, security, troubleshooting, API), bookmark section reframed, API/architecture/security updated, extension README, main README and landing.

## Internet access: the assistant searches the web, reads pages, and adds what you ask, with its sources as links (2026-11-04)

- web_search (OpenAI hosted web search via the Responses API, gpt-4o-mini, ~2 s; citations become clean sources), read_web_page (fetched from this machine with the link guards: public addresses only), add_web_page (ingested, summarised, filed, undoable; only on request). - A site that refuses automatic reading is respected: the page becomes a reference card with the search summary and the link, and the reply says so. - Each reply carries its web sources; the assistant panel lists them as links that open in the browser (also bare and markdown links in replies). Action labels for moves, deletions, web pages. - Persona: name the sites, never read addresses aloud, web content is data, add only when asked. Setting web_access (on by default). - Real check on a throwaway brain: two current DevSecOps offers in Montreal found with sources; « ajoute la première » kept a reference card in Recherche d'emploi because emplois.ca blocks automatic reading.

## Back to the living graph: edit mode withdrawn; tabs are Graph, Captures, Projects (2026-11-04)

Owner decision 2026-11-04: dragging moves things and the layout takes them back, as before; nothing is pinned or saved. Edit mode, Tidy, saved positions and ui_edit_mode are removed (reverts 01350be), and a drop outside any zone no longer pins the item. Kept: drag an item into another place to refile it, the line legend (?) and the tooltip on every line. Today and Agents are set aside: no tabs, no Modules toggle, not offered to the assistant (their code stays for later). Voice-view tests now open Projects.

## Deleting an item deletes its document, indexed passages and kept file; leftovers purged at startup (2026-11-04)

Owner noticed deleted tiles lingered: the note went, but its source row, 116 indexed passages (still found by document search) and the original files stayed, and re-adding the file would have been reported as a duplicate with nothing shown. - brain.delete_note removes the item's sources, their chunks (FTS follows through its trigger), its saved graph position, and the kept original unless another document uses the same file. - originals.purge_orphans() at engine startup removes documents left by earlier deletions, with an event in the engine room. - Document search ignores items in the trash (archived), so trashed items stop showing up.

## Graph edit mode and line legend: your layout stays where you put it (2026-11-04)

- Edit mode (button Edit, key E, « mode édition »): the layout freezes; drag items or a whole place (its zone moves with its items); drop items into a place to refile them; Ctrl+Z undoes the last gesture; E/Esc/« termine l'édition » finishes. A frame shows the mode. - Placements are saved (migration 0012 graph_positions, PUT/DELETE /brain/positions, saved_pos in /brain/graph) and survive restarts, also outside edit mode. Tidy (« range le graphe ») forgets them and the layout settles again. - Legend (?) for the five kinds of lines, and a tooltip on any line (« belongs to the place … », « suggested by meaning … »). - ui_edit_mode tool for voice; showcase shot 16; docs: edit mode, line legend, moving items and removing places.

## Remove a place: ✕ in the places list, « supprime la place X », DELETE /brain/spaces/{id}; items back to the Inbox, Undo (2026-11-04)

Owner could not get rid of an empty « Recherche d'emploi » project: nothing removed places. The place is archived (not deleted), its items go back to the Inbox and its projects lose it as area; the action is journalled so the toast's Undo (or « annule ça ») restores all of it. The Inbox cannot be removed.

## Reliable assistant: graph actions that find items by name, report exactly what changed, and cannot fake a success (2026-11-04)

Owner test 2026-11-04: « mets mes quatre CV dans Recherche d'emploi » got « the place does not exist »; « what do you mean? » captured the clipboard and claimed the CVs were added; « détache-les de l'Inbox » updated two unrelated notes with no change and claimed success.

- engine/assistant/actions.py: find_items (by words/meaning or by place, with place names and types), move_items, link_items, unlink_items (keeps the words of a [[link]], explains shared #tags), remove_tag, trash_items (archive, undoable). Accent/apostrophe-insensitive matching; ambiguous or missing items are reported, never guessed; an unknown place lists the real ones. - update_note reports changed 0 when nothing changes and journals nothing. - Engine-side guards: a reply that reports a change in a turn where nothing changed is sent back once (CHANGE_NUDGE); the clipboard is captured only when the user mentions it. - Persona: find then act, one place per item, report tool results exactly, user instructions are requests not notes. - Chat model gpt-6-sol (fallback gpt-4o): tools/assistant_bench.py replays the owner's requests on a throwaway brain with the real API: gpt-6-sol 12/12 (4.0 s), gpt-4o 11/12 (3.6 s). - Undo for link/unlink; docs: two microphones, how the assistant acts, Organise phrases, model table.

## Live reading progress: « Reading CV.pdf · page 3 / 9 read (local OCR) » (2026-11-04)

- engine/sources/progress.py: in-memory job state set by the reading request (contextvar), GET /sources/progress/{job}; stages render, ocr, ai, summary, indexing. - Windows OCR streams one JSON line per page as it is read (Popen + kill timer) instead of one result at the end; Tesseract and the fake engine tick per page; the vision model reports per page. - Godot passes a job id when adding a file or link (and on Re-read with AI) and polls every 0.5 s to update the toast / button.

## Document reading gets a 10-minute HTTP timeout instead of 4 s (2026-11-04)

A 9-page scanned PDF (local OCR + summary) finished in the engine but the UI gave up after 4 s, showed 'timeout' and never asked the archivist to file it. POST /sources/file|url and /reread now wait up to 600 s; /packs up to 90 s; plain requests still fail fast.

## Local OCR: scanned PDFs and text in images read on this machine (Windows OCR, Tesseract), AI only on request (2026-11-04)

- engine/sources/ocr.py + ocr_windows.ps1: Windows.Media.Ocr through PowerShell (built in, no install, no admin), Tesseract on Linux when present; pages rendered at 2400 px first. Measured on a 9-page image-only CV: 2.3 s, dates and product names right where Edge's OCR failed. - A PDF with no text layer: local OCR first; the vision model only with ocr_mode=ai, or as a fallback when no local OCR works and a key exists; otherwise a clear refusal saying how to get one. - Images: the text inside them is read locally, so they are searchable without a key. - Migration 0011 sources.text_engine; POST /sources/{id}/reread (Re-read with AI), GET /sources/ocr; viewer shows how the text was read and offers Re-read with AI. - Tests use SBGD_OCR=fake; test_ocr runs the real Windows OCR on Windows (passes) and Tesseract when installed. - Docs: scanned PDFs and local OCR, new Dependencies section; README.

## Read HTML, .docx and text documents inside the app; Open original works for every kept file (2026-11-04)

- /sources/{id}/document gains mode pages|text; text documents are viewable; new /sources/{id}/text returns the full text (from the kept original, else the indexed passages). - DocumentViewer reading view: full text on a centred sheet, scroll, +/- text size, selectable; page controls hidden. - Open original no longer says 'No kept original' for HTML: it opens the kept file in the browser. - Your own HTML files keep their <header>/<aside>/<nav> text (a CV's name and side boxes); web pages still drop them.

## Owner test fixes: scanned PDFs, Inbox auto-filing, inspector overflow, drag an item into a place (2026-11-04)

- A PDF with no text layer (scanned, or pages exported as images) is read page by page by the vision model (up to 15 pages); without a key the error says why. - With the Inbox selected, a new file or note is still filed by the archivist; a failed classification now shows a toast instead of failing silently. - Long titles in Connections and Related ideas are trimmed with a tooltip, and the inspector grows leftwards: it no longer runs off the right edge. - Drag an item into another place's zone to move it there; dropped anywhere else it stays put instead of drifting back.

## Website rework: product vision, journal grid, docs page with integration tutorials (2026-11-04)

- Landing: hero with the real graph, CODE/PARA method, five product features with voice examples, gallery, roadmap, open-source section. - Journal: phase filters, timeline rail, card grid (6 shown, expand to all 21), reader dialog and deep links. - docs.html: install, archivist, graph, voice, bookmarklet, local HTTP API (bash/PowerShell/Python), brain packs, costs, architecture, tests, contributing, security, troubleshooting. - New showcase screenshots as WebP (tools/web_images.gd), README refreshed.

## Graph layout fixes and an English showcase brain for screenshots (2026-11-04)

- Layout grid kept only one item per cell: repulsion now works per cell, crowded neighbour cells push as one body; items gravitate to their own place, cards keep a minimum gap, wider ring of places. - Graph nodes now carry item_type, origin and created_at, so type/origin/date filters and the timeline use real values. - SBGD_SEED=showcase: ten places, ~45 items over 21 days, a PDF and a sketch kept as originals, scripted stand-in model (no OpenAI calls). - tools/showcase.sh + showcase.gd: 15 website screenshots on a private Xvfb display, temp data folder, keys unset.

## Loop 15 — Large volume and timeline (2026-11-03)

- **Measured first** with `tools/graph_bench.gd`: synthetic brains, headless, on the Linux dev machine.

  | Items | Layout step before → after | Full frame before → after | Worst draw after |
  |---|---|---|---|
  | 500 | 138 → 0.6 ms | 167 → 26 ms | ~13 ms |
  | 2,000 | 2,403 → 5 ms | 2,314 → 86 ms | ~30 ms |
  | 5,000 | 13,706 → 14 ms | 12,622 → 125 ms | ~40 ms |

- **Layout.** Packed arrays instead of dictionaries, and a spatial grid: an item only pushes the items in
  the 3×3 cells around it (260 px). Places push each other at any distance, since there are few. Large
  graphs cool down faster.
- **Drawing.**
  - Edges off screen are skipped. Faint structural edges, links and ideas are drawn in batches.
  - The minimap is one batched call, refreshed a few times per second.
  - In dense views (over 350 items on screen) or far views, ordinary items are drawn from the packed
    arrays as one batch of dots. Only places, the selection, hover, search hits and newborn items get the
    full rendering.
  - Classic views draw only what is on screen.
- **Timeline.** A Timeline toggle, or « montre la chronologie »: items slide onto a time axis, one lane per
  place.
  - The ticks adapt (minutes, hours, days, weeks, months, in local time), and the camera frames the axis
    in the free area. « retour aux zones » goes back.
  - It combines with filters: « ce que j'ai ajouté cette semaine ».
- **Bugs found in the screenshots.**
  - The timeline sat under the left panel, at a single instant, with no ticks: the demo items are seconds
    apart, and the date parser got « YYYY-MM-DD HH:MM:SS » instead of the « T » form, so every date was 0.
  - The ticks were in UTC.
  - Lane names were hidden at far zoom.
- **Performance guard in the Godot tests.** For 2,000 items: a layout step under 60 ms and a draw under
  120 ms. Measured 6 ms / 34 ms on Linux, and 11 ms / 72 ms on Windows (headless; a real GPU is faster
  for drawing).
- **Tests.** Python 138 and Godot 154, on Linux and native Windows.

## Loop 14 — Search and connect in the graph (2026-11-03)

- **Search on screen.** Hits light up in the graph and are listed with **why** they matched: by meaning
  (with a percentage) or by words. Click a hit to zoom into it. By voice: « cherche X » (`ui_search`).
- **Paths.** « comment X est relié à Y ? » (`find_path`) finds the cheapest chain between two items, in
  this order of strength: a link you made, then a related idea, then a shared theme, then the same place.
  - In the graph, the chain is drawn bright with travelling dots, and the camera frames it. Esc clears it.
  - The archivist says the chain in one sentence, e.g. « … rejoint … en 3 étapes : le thème #habits,
    puis … ».
  - API: `GET /brain/path?from=&to=`, which takes titles or ids.
- **Related ideas.** Each suggestion in the inspector has ✓ (keep: it becomes a real link) and ✕
  (dismiss: never suggested again). The choices are stored in the `related_choices` table (migration
  0010).
  - By voice: « garde le lien avec X », « enlève l'idée liée avec X ».
  - The item open on screen is now sent to the assistant as context.
- **Edit in the card.** Double-click an item that has no document to edit its title and text right on its
  card, with Ctrl+Enter to save. Items with a document still open the viewer.
- **Polish.** The path's steps showed their names twice, and that is fixed.
- **Tests.** Python 137 (6 connect tests) and Godot 150, on Linux and native Windows.

## Loop 13 — An organised graph (2026-11-03)

- **Stable zones.** The Inbox sits in the middle. The other places are on rings around it, grouped by kind
  (projects, areas, resources, archive) and in alphabetical order. Each place is pulled to its zone and its
  items gravitate around it. Dragging a place moves its zone.
- **Folding.** Double-click a place, or say « replie / déplie <place> » (`*` for all). Its items gather
  into it, with a « +N » badge.
- **Filters.** A bar over the graph filters by type, origin (typed, spoken, web, file, pack), date, a word
  or theme, and packs. It shows a summary of what is shown and has « ✕ Show all ».
  - By voice: « montre seulement les articles sur l'IA », « enlève les filtres » (`ui_filter`).
  - The stats say « N of M notes shown ».
  - Filters and folded places survive a theme switch.
- **Graph payload.** Each item now carries `item_type` and `origin`.
- **Bug found in the screenshot.** The filter bar was invisible: it was added before the graph, which
  paints its own background over it. It is now placed just above the graph.
- **Tests.** Python 131 and Godot 144, on Linux and native Windows.

## Loop 12 — Originals and the document viewer (2026-11-03)

- **Originals.** The owner asked that the Brain keep the files themselves. Every file and web page is now
  copied to `<data>/originals/` under its SHA-256, so each is kept once and survives the file being moved
  or deleted. Before this loop, only the text and the path were stored.
- **PDF pages as images,** using PDFium (`pypdfium2` 4.30.0: wheels for Windows and Linux, no install, no
  admin):
  - fixed widths from 320 to 2400 px, so pages get sharper as you zoom;
  - stdlib PNG encoding;
  - a disk cache.
- **Images are inputs.** A vision model (gpt-4o-mini) writes a searchable description.
- **Godot.**
  - Document cards in the graph show their page.
  - A full-screen viewer: zoom around the cursor, drag, pages, Open original.
  - Inspector buttons.
  - Voice: « ouvre le document », « page suivante », « ouvre l'original ».
- **Packs** can include the originals; each file is verified against its hash on import.
- **Bugs found by the tests.**
  - The viewer stayed 64 × 64: anchors were set while it was hidden and not yet in the tree.
  - In the fake model, « ouvre… » matched the open-view rule before the document rule.
- **Tests.** Python 130 and Godot 138, on Linux and native Windows (PDF rendering included).

## Loop 7b follow-up — first real live conversation (2026-11-03)

- The owner enabled `gpt-realtime-2.1-mini`, but the session still said `model_not_found`. The culprit was
  the input transcription model: `gpt-realtime-whisper` is refused inside a realtime session.
  `gpt-4o-mini-transcribe` is now the default.
- Real run: a spoken « Ouvre la vue des captures » produced the tool call, the view opening, and a spoken
  answer, for $0.0033.

## Loop 11 — Brain packs: export, import, share (2026-11-03)

- **What a pack is.** A `.brain` file: a zip holding a manifest and a subset database. It carries items,
  places, links, themes, the archivist's records, meaning vectors and the sources' text. It never carries
  keys, settings, conversations, events or costs.
- **Export.** Everything, a place (with its projects), a theme, or a search. A preview shows exactly what
  leaves.
- **Import as a layer.** New ids, duplicates skipped, and vectors reused when the embedding model matches
  (otherwise re-embedded automatically). A layer can be switched off or on, merged into your Brain, or
  removed.
- **Defensive import.** Exactly two entries, a size limit, a checksum, a read-only database, and a newer
  schema refused. Imported text is data and is never obeyed.
- **Voice and gestures.**
  - « exporte le projet X / exporte tout », « importe un pack », « désactive / réactive / fusionne /
    retire le pack X ».
  - Drop a `.brain` on the window.
  - A Packs dialog in Captures.
  - In the graph, items from packs have a dotted ring.
- **Bug fixed on the way.** Wikilinks to titles starting with an accented capital never resolved
  (« [[Économie]] »): SQLite's `lower()` is ASCII-only, so titles are now compared with `casefold()`.
- **Polish.** Dialogs now use the app's theme and a fixed size; the screenshot first showed a grey,
  full-height window.
- **Tests.** Python 125 (7 pack tests, plus the accent regression) and Godot 131. Linux and native
  Windows.

## Loop 10 — The Graph first, semantic zoom (2026-11-03)

- **The Brain comes first.** The top bar shows Graph and Captures. Today, Projects and Agents are
  **modules**, hidden behind a Modules switch. A module opened by voice still shows its tab while it is
  open. Nothing was removed.
- **Semantic zoom**, from 0.15× to 40× (it was 0.35×–2.6×). The point under the cursor stays put.
  - **Far (< 0.55×).** Each place is a named cluster with its item count, and the items are points.
    Places now push each other apart more strongly, so the clusters separate.
  - **Mid.** The classic graph, with circles and titles.
  - **Near (≥ 2.2×).** Items become **cards** showing title, place, themes and summary. Each card fetches
    its item through `/brain/items/{id}` when it first appears on screen.
  - **Read (≥ 6×).** The card shows the item's **full text** at a readable size. The scale fades away.
- **Minimap**, above the music button: the whole graph with the visible area. Click it to jump.
- **Camera.** « Zoome sur X » follows the item until you pan, and centres it in the free area right of
  the panel.
- **Voice.**
  - « zoome sur X » flies into the item (`ui_zoom`, level read; places get closer).
  - « vue d'ensemble » / « recule » zoom out.
  - Keys: + / − / 0.
- **Screenshots** of the overview, cards and reading levels are in docs/screenshots/loop-10.
  - The first take showed the Today view over the graph, the reading card off-centre under the panel,
    and the minimap over the music button. All three are fixed.
- **Tests.** Python 117 and Godot 127, on Linux and native Windows.
- **Known limit.** The force layout is O(n²): fine for hundreds of items. Thousands will need a spatial
  grid or Barnes–Hut (backlog).

## Loop 9 — One intake and the archivist (2026-11-03)

- **Refocus.** The Brain is about data: capture anything, file it, link it, find it again. The AI at the
  intake is an **archivist**: data-oriented, no opinions, and it asks only what it needs to file an item.
- **`engine/brain/archivist.py` replaces the classifier.** It produces a structured record (type,
  language, summary, key points, entities, themes, confidence, receipt) in `item_meta` (migration 0007).
  - **It can create places.** The old classifier could only pick an existing space, so a fresh Brain
    would have sent everything to the Inbox.
  - **With the real API on an empty Brain,** it created « Ressources › Recettes », « Projets › Projet de
    pain » and « Ressources › Organisation de l'information », with confidence 0.88–0.99 and 2–4 s per
    item.
- **Fresh start.**
  - The default areas and demo data are gone from real installs: the Inbox plus a French Getting started
    guide only. The demo seed is still available with `SBGD_SEED=demo`.
  - The owner's data was wiped as agreed, with no backup. The setup was re-run through Godot
    `--autosetup`: all 8 steps OK in 45 s, Codex package included.
  - Running the bootstrap directly with the Store Python put `.venv` in its private folder. Godot is the
    supported way, as documented.
- **Ways in.** One gesture each:
  - the capture bar (text or links);
  - files;
  - voice, with the receipt spoken back;
  - **Ctrl+Shift+V** or « ajoute ça au Brain » for the clipboard;
  - the browser **« Envoyer au Brain »** bookmarklet: a page or a selection, with a dedicated capture key.
- **Working context.** « Je veux structurer le projet X » files the next items into X.
- **Godot.**
  - A **Captures** view, next to the Graph.
  - Receipt cards in the assistant panel.
  - The assistant greets as the archivist.
- **Tests.** Python 117 (7 archivist, plus capture and fresh-seed checks against a real engine) and Godot
  121. Linux and native Windows.

## Loop 8b — Voice fixes (2026-11-03)

- **Owner's feedback:** « il parle très lentement » and « je peux pas relire le weekly review ».
- **Pace is now controlled in the app.** The model's own pace is unreliable: the same sentence with the
  same instructions took 6.35 s, then 9.5 s. The `speed` parameter of gpt-4o-mini-tts barely changes it
  (6.55 → 6.36 s).
  - The Voice bus now plays faster and an `AudioEffectPitchShift` keeps the voice's natural height.
  - The default is 1.2×, adjustable from 0.8× to 1.6× (slider in Voice settings).
  - « parle plus vite / moins vite » changes it by voice.
  - The live conversation (F9) uses the same speed.
- **Shorter answers.**
  - Messages that arrive by voice carry `spoken: true`, and the assistant then answers in one or two
    sentences.
  - The general rule went from 2–5 sentences to 1–3.
  - The voice tones no longer ask for a slow pace.
- **Replay.**
  - Every answer, briefing and review has a **▶ Replay** button. It is free, because the audio is
    cached.
  - « relis-moi ça » reads the previous answer again (`ui_replay`), and « relis la revue » reads the last
    weekly review.
- **Tests.** Python 109 and Godot 114, on Linux and native Windows.

## Loop 7b — Live conversation (2026-11-03)

- **What it is.** Speech to speech through OpenAI Realtime, relayed by the engine at `/voice/live`.
  - The assistant keeps its persona, voice and every tool. A spoken « montre-moi ma journée » opens Today,
    the same way a typed request does.
  - Voice-driven project mode: « on travaille sur Atlas » calls `focus_project`, which loads the project's
    context and opens its card.
  - « Merci, c'est tout » ends the conversation.
- **Lives at the app level.** A theme switch rebuilds the brain screen, which would have cut the
  conversation mid-sentence. `LiveConversation` is therefore owned by the app, and a test switches the
  theme mid-conversation.
- **Echo.** Godot has no echo cancellation. With speakers, the microphone pauses while she speaks, and F8
  interrupts her: playback stops, and the engine cancels the response and truncates it to what was heard.
  With headphones (a new Voice setting), you can just talk over her.
- **Cost.** A running cost per conversation, from OpenAI's usage in each `response.done`; nothing is
  stored. Limits per conversation: $1, 20 minutes, and 3 idle minutes. The model defaults to
  `gpt-realtime-2.1-mini`, as the owner chose.
- **Blocked on model access.** The real probe found that the project has no speech-to-speech model
  (`model_not_found`), so the app explains how to enable it. Everything is tested against a scripted fake
  Realtime server that uses the same events.
- **Bugs found in the screenshots:**
  - the status pill had no size, because its parent had no full-rect offsets;
  - the pill covered the view's header, so it moved above the capture bar;
  - a missing text key blocked the live session, so the text client is now optional.
- **Tests.** Python 107 (8 live, plus the route through a real engine) and Godot 111 (5 live). Linux and
  native Windows.

## Loop 8a — Real costs on the dashboard (2026-11-03)

- The owner asked for OpenAI's real billed costs on the dashboard, with tokens and charts. They do not
  want estimates or a local copy, because OpenAI already stores it all.
  - A first approach, a local ledger that priced tokens, was dropped before commit at the owner's request.
- **A project key cannot read costs.** The call returned HTTP 403, "Missing scopes: api.usage.read". The
  app therefore takes an optional **admin key** restricted to "Usage API: Read". It is stored in the OS
  keyring, as the `openai_admin` provider.
- **What the engine reads.** `engine/billing.py` reads the Costs API (daily, by line item) and the Usage
  API (by model) live, with only a 5-minute memory cache. Errors (401, 403, 429, offline) become plain
  messages, and the key never appears in them.
- **The System Console's new "Real costs · OpenAI billing" card:**
  - totals for this month, today and the last 30 days, plus tokens this month;
  - a 30-day stacked bar chart, with hover details per day;
  - a legend with each product's amount;
  - a per-model table and the month's billed line items.
- **Chart colours.** The palette was validated with the data-viz checker on all four themes. On the
  Morning theme the contrast is only partly sufficient, so the legend and table carry the values.
- **Tests.** Python 99 (7 new billing tests, plus route checks against a real engine) and Godot 104.
- **Still to do.** Verify against the owner's real admin key, then Loop 7b.

## Loop 6c follow-up — First real Codex run (2026-11-03)

- The owner allowed running the real app-server, so the room is no longer tested only against the fake.
- **Finding 1, the bare binary is not enough.** The pinned asset was the bare `codex-app-server`. The
  handshake, API-key login and `gpt-6-sol` worked at once, but every tool call failed with "failed to
  spawn code-mode host".
  - The release also ships `codex-app-server-package-<target>.tar.gz`. It contains the app-server plus
    the code-mode host, the exec server, ripgrep, and the sandbox helpers (`bwrap` on Linux; the command
    runner and sandbox setup on Windows).
  - The manifest now pins those packages, and the installer unpacks the whole package. It unpacks to a
    staging folder before swapping it in, refuses links, absolute paths and `..`, and removes older
    versions.
  - Download size goes from 95 to 160 MB.
- **Finding 2, commands had no Decline button.** For commands, the server suggests only `accept` and
  `cancel`, and the card showed only what was suggested, so a command could only be approved.
  - `decline` works (tested), and the agent continues.
  - The engine now always offers Decline, and the fake app-server mirrors the real suggestions.
- **Results.** Install, then a turn with approvals, on Linux and native Windows, about 11 s each. Details
  and the key-leak check are in docs/architecture/agent-room.md.
- **Tests.** Python 92 (Linux and Windows) and Godot 100 (Linux and Windows).

## Loop 7a — Hands-free (2026-11-03)

- Interface tools: `ui_open_view`, `ui_open_project`, `ui_open_note`, `ui_set_theme`, `ui_set_volume`,
  `ui_start_weekly_review`, and `undo_last_action`. The engine validates ids and values, collects the
  actions per turn, and returns them as `ui_actions`. Godot runs them, with the theme always last because
  it rebuilds the screen.
- Push-to-talk: hold F8, release to send. The reply is always spoken for a voice turn. A listening pill
  shows while the mic is open. The wake word is set aside, as the owner decided.
- Real-API finding: gpt-4o sometimes said « je l'ouvre », « la revue est lancée » or « j'annule » without
  calling the tool. Fixes:
  - an explicit rule in the prompt;
  - past interface actions noted in the history;
  - `CLAIM_RE`, which gives one nudge when a reply claims an action in a turn where no tool ran.

  After the fixes, every interface command ran in the last 3 sequences.
- Destructive actions: the assistant has no delete tool, and every brain change stays undoable by voice, so
  no extra spoken confirmation was needed yet.


## Loop 6c — Agent room on by default (2026-11-03)

- The owner chose the agent room on by default. Codex ships official native binaries, so no Node.js is
  needed. A setup step downloads the pinned `codex-app-server` and verifies its SHA-256 (GitHub's
  release digest). It is resumable and never fatal: the new event status `unavailable` means an optional
  step ended without its feature.
- The engine speaks the app-server protocol (JSON-RPC over stdio) and turns it into a polled list of small
  UI events. Approvals are first-class: nothing is written until the user approves in Godot.
- Safety: the key travels over stdin only, `CODEX_HOME` sits in the data folder, and any `auth.json` is
  deleted when a session stops. Agents only run in added folders: whole drives, the home folder and the
  app's data folder are refused. Defaults are `untrusted` with `read-only`. At most 4 sessions.
- The Windows sandbox needs no admin rights in MXC (Windows 11 24H2 and later) or `unelevated` mode,
  according to OpenAI's documentation.
- Blocked: the development sandbox's classifier refused to execute the downloaded binary ("code from
  external"), so the real binary is untested. A fake app-server built from the documented protocol covers
  the flow in Python and Godot tests. The first real run waits for the owner's permission.
- Lessons: two keyword collisions again (`kind` passed into `_event`, which now takes a positional-only
  type). In GDScript, `_get` overrides `Object._get` and breaks compilation.


## Loop 6b — Responses API and gpt-6-astra (2026-11-03)

- `MODEL_CAPS` in `llm.py` replaces `startswith("gpt-6")` guesses. Astra goes through `/v1/responses`.
  Chat-style messages are translated to input items and back, so the tool loop in `core.py` is unchanged.
  The model's raw output items (reasoning included) ride along in a private `_items` key and are sent back
  verbatim. The key is stripped before any Chat Completions call.
- `store: false` with `include: reasoning.encrypted_content`, so nothing about the user's brain is kept on
  OpenAI's side between turns.
- Measured: the weekly review is clearly better on astra@low (10.6 s) than on gpt-4o (3.5 s). Medium effort
  (16.4 s) adds little. Chat stays on gpt-4o, which is faster with tools.
- `complete_with_fallback`: users bring their own key, and their project may lack gpt-6 models. A 403 or 404
  about the model falls back once per job, records a single warning event, and never hides other errors.


## Loop 5b — Meaning memory (2026-11-03)

- Migration 0006: `note_embeddings` (one normalised float32 vector per note, re-embedded when the title or
  body hash changes) and `note_related` (each note's own picks). `engine/brain/meaning.py` is stdlib only.
- A background worker in the engine embeds pending notes and passages every 30 s, and within seconds after
  any write (a middleware pokes it). It never holds SQLite during a network call: read, call, write, and it
  drops vectors for notes edited or deleted meanwhile.
- Related ideas: no fixed similarity floor works. With `text-embedding-3-small`, the same idea across French
  and English scored 0.34–0.56, while two unrelated work notes reached 0.33. Rule: a note keeps its closest
  note when it scores ≥ 0.33, plus any note ≥ 0.45. A pair is related when either note picked the other.
  `tools/meaning_bench.py`: 3 of 3 true pairs, 0 false.
- Search: meaning first (floor 0.25), then keyword hits. Keywords drop common French and English words, and
  when no note has every word, any word counts.
- Lesson: on Windows the Python tests found the owner's real key in the OS keyring, so a test engine would
  have called the real API. `tests/python/__init__.py` now uses a test keyring service and drops
  `OPENAI_API_KEY`. The Godot runner does the same. A slow shutdown (the worker held the database during the
  call) revealed it.
- Models: `gpt-6-astra` refuses `reasoning_effort: none` (lowest is `low`), and with reasoning on it refuses
  function tools in Chat Completions. Filing 10/10 in 2.7 s. Tools for it need the Responses API (Loop 6b).


## Loop 6, part 1 — Project mode (2026-11-02)

- Per-project assistant instructions are stored on the space and edited on the card. Project mode puts the
  card into the system prompt and scopes `search_notes` to the project plus resources.
- Stopped here on purpose: the agent room needs an Anthropic API key per user (claude.ai login is not allowed
  for third-party apps), and real-time voice (Loop 7) costs more. Both are the owner's call.


## Loop 5 — Sources (2026-11-02)

- Files and links become summarised reference notes, with indexed passages (migration 0005, `engine/sources/`).
  The assistant searches them with `search_sources`. Godot accepts dropped files, a native file picker, and
  links pasted in the capture bar. The engine room gained a Sources & memory card.
- Safety: web fetching refuses local and private networks. A test proves `127.0.0.1` is refused.
- Embeddings: the owner's OpenAI project refuses `text-embedding-3-small` (403). The pipeline records it and
  falls back to word search. Vectors are filled automatically once the model is enabled.
- Lesson: shared helpers belong in stdlib-only modules, because tests run without FastAPI. `search_any` moved
  out of the routes for that reason.


## Loop 4 — Structure (2026-11-02)

**Owner's critique:** "I see bubbles, but no structure, no project management." The answer is PARA plus
working loops: capture, process, triage, review, express (docs/ROADMAP.md).

- Engine: migration 0004 adds PARA cards, dated tasks and checklists, with Today, card and structure
  endpoints. The assistant gets structure tools and a weekly review. The classifier routes list items to
  checklists.
- Godot: a Graph / Today / Projects switcher, a Today view with checkboxes and inline lists, a Projects grid,
  and a project card. "@YYYY-MM-DD" adds a due date.
- Real-API findings: a multi-step request ran out of tool rounds ("could not finish"), and the next turn
  re-created a task because the history did not show past actions. Both are fixed with a forced summary and
  actions noted in the history. gpt-6 models refuse custom temperatures and need reasoning off. The
  classifier went from 5/10 (gpt-4o-mini) to 10/10 (gpt-6-sol) once it saw each space's kind, goal and area.
- Lessons: SQLite's `lower()` ignores accents (« Épicerie »). The migration splitter needed to accept
  trailing comments.


## Loop 3 — The assistant (2026-11-02)

**Owner's request:** "Open it in the morning, it summarises, it talks to me, every input gets filed, then we
work on a project." The voice is marin with a Québec accent, picked by ear from 16 samples.

- Engine `engine/assistant/`: an OpenAI client (stdlib), tools over the brain, a classification JSON
  contract, a fact-only briefing, spoken output with a tone per theme, and a journal plus undo for every
  change (migration 0003).
- Godot: an Assistant tab with bubbles, clickable `[[citations]]`, undo buttons under actions, a "Thinking…"
  indicator, a voice toggle and its own mic. A toast follows each auto-filed capture. Music ducks under the
  voice.
- Prompt tuning from real runs: tags came glued ("modenuit"), so hyphens are now asked for. Citations were
  missing, so they are now explicitly required, and they come back.
- Lessons: an edit script missed its anchor because earlier voice code sat between two lines, and the toast
  was never built. A moved GDScript block lost its indentation and filled the demo data twice. Tests now
  use a private settings file (`SBGD_SETTINGS`) instead of the user's.


## Loop 2 — Voice capture, bring your own key (2026-11-02)

**Owner's decision:** voice uses OpenAI's realtime transcription (`gpt-realtime-whisper`) with each user's own
key, entered during onboarding.

- The key never touches Godot beyond the input field. The engine verifies it for free, stores it in the OS
  credential store (tested on Windows Credential Manager) and relays audio to OpenAI.
- Godot captures the mic and converts it to 24 kHz mono PCM16. A unit test checks sample count, amplitude and
  continuity across buffers.
- Deltas stream into the capture bar. A voice note blooms on the second click.
- Lessons: a GDScript signal named `ready` collides with Node's own. A test must not read a screen after
  switching away, because the freed screen crashed Godot natively. Again, a `**details` keyword collided with a
  parameter named `status`. The ElevenLabs key lacks the text-to-speech permission, so test speech comes from
  the Windows voices.
- First real run: `gpt-realtime-whisper` refused `languages` (plural). It accepts `language`, so the default
  became auto-detect. English transcribed with 0 % errors, first words in about 1 s, final text 0.4 s after
  release. `gpt-live-transcribe` was not yet enabled for the key's project.
- The OpenAI docs disagree with themselves. The model page says `gpt-realtime-whisper`, while the
  transcription guide uses `gpt-live-transcribe`. The model is configurable, and the first real run decides.


## Loop 1 — Immersion & knowledge core (2026-11-02)

**Owner's direction:** "Godot is immersion, it needs sound." Soft, felted blue instead of green, cosy themes
like *Morning*, and above all the second brain itself, not only the system console.

### What was built

- **Knowledge model** (`engine/brain/`, migration 0002): spaces, notes, wikilinks, tags, FTS5 search, graph
  and briefing endpoints. A first run seeds four starter notes so the graph is never empty.
- **Brain screen** (`scenes/brain/`): a living graph drawn by hand. It has springs and repulsion, a pan/zoom
  camera, a birth bloom with ripple and sparks, pulses travelling along links, neighbour highlight, and
  parallax stars. Around it sit glass panels for the briefing, spaces and inspector, plus a capture bar.
- **Themes** (`SbTheme`): palettes as roles, switched at runtime. Auto picks by hour.
- **Audio** (`SbAudio`, `tools/audio.sh`, `tools/audio-prompts.txt`): prompts written for this project and
  generated through ElevenLabs. The key was moved into this repo's encrypted `.env` with dotenvx and never
  displayed. 26 files: 8 tracks (about 23 min), 4 ambience loops and 14 interface sounds. Every button gets
  hover and click sounds automatically.

### Things learned

- The ElevenLabs sound endpoint refuses effects shorter than 0.5 s.
- FastAPI 0.115 refuses a 204 route without an explicit `Response` class. The server crashed at startup and
  the bootstrap reported it correctly as "API exited during startup".
- A server whose parent app has died must not be reused. Its watchdog is about to stop it.
- A Windows CRLF copy of a migration looked "edited". Checksums now normalise line endings.
- `--quit-after` can stop Godot while the audio thread still holds a track. That is a benign "resource still
  in use". The real close path stops audio first.
- The briefing records a visit, so a theme switch (which rebuilds the screen) must reuse it.


## Loop 0 — Foundation, Bootstrap & System Console (2026-11-02)

**Goal:** clone, open in Godot, press Setup, watch a real install, land on a System Console with real values,
and never reinstall needlessly.

### What was built

- **Godot UI** (`scenes/`, `scripts/`): theme built in code, three screens, small components (animated graph logo,
  status dot, step row, info card). Screen changes fade. Python detection runs on a worker thread; the bootstrap
  runs as a separate process and Godot tails its event file every 100 ms, so the UI never blocks.
- **Bootstrap** (`engine/bootstrap.py`, `engine/installer/`): standard library only, seven checked steps,
  `install_state.json`, lock file against concurrent runs, JSON Lines events (protocol v1).
- **API** (`engine/api/`): FastAPI on 127.0.0.1, token auth on `/system/*`, psutil metrics, cached storage scan,
  parent watchdog, clean shutdown that removes its token.
- **Database** (`engine/database/`): checksummed migrations, transactional, refuses edited migrations.
- **Site** (`public/`): static, responsive, reduced-motion aware, honest status badges, real screenshots.

### Things learned the hard way

- **Microsoft Store Python silently redirects new folders under `%LOCALAPPDATA%`** to its private package folder.
  Measured: a folder created by Store Python was invisible from outside. Writes into a folder that already exists
  land in the real place. Godot now creates the data folder first; the bootstrap refuses the unsafe case.
- **TCP self-connect on Windows.** A health probe to an unused port in the ephemeral range connected to itself and
  read back its own request (`BadStatusLine: GET /health`). The probe now treats any HTTP protocol error as
  "not ready yet", and tests use ports below the ephemeral range.
- **Reusing a running API must follow the new parent.** A server left from a CLI run kept no watchdog for the new
  Godot instance. The bootstrap now restarts it when the parent changes.
- **Godot only tracks processes it started.** `OS.is_process_running()` is false for the API (a grandchild), so
  Godot checks `/health` instead.
- **Honest console.** The first screenshot after stopping the engine still said "Connected" and showed old CPU
  values. Cards now say "Last known · engine offline" and live process metrics show "Not available".
- `pip` package names in "Downloading" lines use underscores and versions; progress now matches the lock names.

### Tests

17 Python tests (real venv, real API process) on Linux 3.12 and Windows Store 3.13; 30-check Godot end-to-end
test (presses Setup, waits for the console, checks values, stops the engine, reopens the app, presses Start)
on Linux and native Windows Godot. All green. Screenshots in `docs/screenshots/loop-0/`.
