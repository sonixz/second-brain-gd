# Plan: the website in Agent Manager's new format, and a film (CI-H to REL-P)

Asked by the owner on 2026-11-13, after the new website of Agent Manager GD: « Je pense qu'on pourrait faire un peu
le même format là, pour Second Brain. […] J'aime le site de Second Brain. […] j'aimerais ajouter les tags et tout
ça. […] ce qui est surtout nice, c'est le vidéo avec la voice, la musique, pense à ça », then « es-tu capable de
structurer les loops pour bien le cadencer avec tout ça ? ».

**Agreed by the owner on 2026-11-13:** « Parfait, passons les points de décision. […] La voix du narrateur, c'est
bon, on peut garder la même voix que l'autre. […] Ouais, on remplace le démo exactement. […] Structure ça. Puis,
écoute, on se lance, là. Let's go, là. Je suis à l'extérieur, fait que cadence-toi bien. » The loops run one after
the other while he is away (`/loop`); each firing reads « Where it stands » below first.

## Where it stands

| Loop | State | Commit | Note |
|---|---|---|---|
| CI-H | **done** 2026-11-13 | 19e8173, b33cbfe | the five jobs pass (run 43522978578) |
| FILM-I | **done** 2026-11-13 | on `site-film` | a 15-second clip of the opening scene, with the app's sound |
| SITE-J | **done** 2026-11-13 | on `site-film` | the page in the new format: menu, index, bar, sections 01 and 02 in full |
| FILM-K | to do | | |
| SITE-L | to do | | |
| SITE-M | to do | | |
| FILM-N | to do | | |
| SITE-O | to do | | prepared on the branch; the merge and the publication wait for the owner |
| REL-P | to do | | after SITE-O, with the owner |

**What waits for the owner's return, whatever the loops finish:** the film by ear (the agent cannot listen), the
rights on the ElevenLabs audio, the go to merge `site-film` into `main` and to publish, the first pre-release.
Nothing goes online before that go.

This plan changes one line of [plan-docs-site.md](plan-docs-site.md) (2026-11-07): « the website keeps its concept
and its look […] no feature list rolled out on the home page ». The owner now asks for Agent Manager's feature
format. What he likes stays: the living graph of the hero, the colours, the « say it » phrases under each feature,
the « How it thinks » page, the roadmap and the loops.

## State found (2026-11-13, `main` at 6eeaf2b)

- **This website** keeps the earlier format: nine menu entries, sections by component (Voice, Method, Product, MCP,
  Agents, Principles, Architecture, Roadmap, Journal), a « Product » section of about ten blocks in a row, small
  pictures by three, no index of features, no film, no sound.
- **The model** (agent-manager-gd, `public/`, 2026-11-13): a menu of four entries, the same on every page; the hero
  with a 48-second film of the real app, muted and looping, a Sound button; an index « Eleven things it does for
  you » and a bar that follows the reader; eleven numbered sections, each titled by what the user gets, with one
  large annotated picture; a Compare band, an « It's a lab » band, the loops. Its first website (2026-11-08) had
  been modelled on this one.
- **Its film** is remade by scripts (`video-production/` there): the real app filmed by Godot's film mode on a
  private virtual display, cut with ffmpeg, a narration (ElevenLabs, voice « Eric »), music and effects. Two of its
  scripts already film a copy of Second Brain.
- **Here:** the capture tools exist (`tools/showcase.sh`, `tools/howto.sh`, a showcase Brain), not the film mode.
  The app has its own sound in the repository: 8 music tracks, 4 ambiences, 14 effects (`assets/audio`), and the
  assistant's voice (marin, OpenAI).
- **GitHub CI, cause found:** `ci.yml` installs nothing, so the runner's Python has no `fastapi`; four tests that
  load the engine's routes end in error (353 tests run, 4 errors, 8 skipped) and the Godot job stops at the same
  place, before Godot starts. Read in the logs of run 43134631800.
- **The repository's page:** description, website link and twenty topics set on 2026-11-13 (owner's request, his
  token). Still no tag and no release.
- **Publication:** the site goes online through gd-project's Pages workflow, which takes `public/` from `main` at
  its next run. A half-rebuilt home page on `main` could go online by accident, so the site is rebuilt on a branch.

## How it is paced

- **One short loop on `main` first** (CI): it depends on nothing and a release needs it.
- **Then one branch, `site-film`**, where film and site alternate so that each loop feeds the next:
  the page's template before the ten sections; the scenes filmed before the sections' pictures (one capture, two
  uses); the sections' headlines before the narration (the same words on the page and in the voice). The branch
  lives in its own folder (`../second-brain-gd-worktrees/site-film`), so the folder the owner's app starts from
  stays on `main`.
- **Each loop ends with something to look at** (a page served on this computer only, 127.0.0.1, or a film file) and
  the owner's decisions sit just before the loop that needs them.
- **Nothing goes online before SITE-O's go.** The release comes last, on `main`.

| Loop | Content | Where | Size | Confidence | The owner looks at / decides |
|---|---|---|---|---|---|
| CI-H | GitHub CI green: the engine's locked packages installed in both jobs | `main` | ¼ | 80 % | a green run |
| FILM-I | Film tools: Godot's film mode in the capture tools, film steps with frame marks, one scene filmed with the app's own sound | branch | 1 | 75 % | a ten-second clip |
| SITE-J | The page's skeleton: menu, feature index and its bar, the section template, two sections written in full | branch | 1 | 85 % | the template on two sections; the list of features |
| FILM-K | Storyboard and narration text; every scene filmed; a silent rough cut | branch | 1 | 70 % | the storyboard, the words, the rough cut |
| SITE-L | Sections 03 to 07, their pictures taken from the films | branch | 1 | 85 % | five sections |
| SITE-M | Sections 08 to the last, the Compare and « It's a lab » bands, what moves to the Docs | branch | 1 | 85 % | the whole page, without the film |
| FILM-N | Voice, music, effects, the cut, the web file and its report | branch | 1 | 70 % | the film, by ear |
| SITE-O | The film in the hero, README, the three other pages, the checks, merge and publication | branch → `main` | ½ | 85 % | the go to merge and publish |
| REL-P | A version number, the package rebuilt, the first pre-release with its tag | `main` | ½ | 75 % | the version's name |

About 7¼ loops.

## CI-H — GitHub CI green

- A step that installs `engine/requirements.lock` (hash-locked) before the tests, in the Python jobs and in the
  Godot job; pip's cache.
- The eight tests skipped on the runner (one here): say which and why.
- A second failure may hide behind the first: the Godot job never reached Godot, and Windows was never seen past
  the same error. The loop ends on a green run or on the next cause written down.

**CI-H done 2026-11-13.** Both jobs install `engine/requirements.lock` (hash-checked wheels, pip's cache): the four
Python jobs passed at once, on Ubuntu and on Windows (353 tests; skipped: on Ubuntu the two real OCR tests,
Tesseract not installed and Windows' OCR being Windows only; on Windows the Tesseract one). A second failure did hide behind the first: one Godot check of 287, « "merci,
c'est tout" ends the conversation », ended as « closed ». A real fault of the app: the engine closed the socket
right behind « ended », and Godot could receive both in one read. Fixed in `engine/voice/routes.py` (the engine
lets Godot close first, two seconds at most), with a check in the integration test that fails without the fix.
Run 43522978578 (b33cbfe): five jobs green. Tests here: Python OK, Godot 287 passed.

## FILM-I — film tools

- `tools/showcase.sh` learns the film mode (frames at 1920×1080, thirty a second), the way Agent Manager's does.
- A film script with steps and frame marks (`mark <name> <frame>`), so the cut follows the app when a screen moves.
- A film Brain: the showcase Brain, with what the scenes need. Never the owner's data.
- `video-production/` with its README and its status file, the scripts ported from agent-manager-gd (cut, web
  encode, voice and music calls).
- **To prove in this loop (a hypothesis today):** Godot's film mode writes the app's own sound beside the frames, so
  the capture sounds and the themes' music come from the app itself, in time with the picture.

**FILM-I done 2026-11-13.** `tools/film.sh <step>` films a step of `tools/film.gd` (the `film_*` functions) on a
private virtual display: frames at 1920×1080, thirty a second, the marks in `marks.txt`, and **the app's own sound
in `frame.wav`: proven** (the first scene's file is not silent: the theme's music and the capture's effects, in
time with the picture). What was learnt and built on the way:

- The app is installed once, without filming, in a base home; each step films a copy. A scene of 25 seconds takes
  about four minutes and a half to film (software rendering, a PNG per frame) and 220 MB, kept outside the
  repository (`~/.cache/sbgd-film`).
- The interface is drawn one and a half times larger (`FILM_SCALE`): at 1920×1080 its text was too small for a
  film watched at a third of that size on the page. The window is then laid out as at 1280×720, so each scene sets
  its own framing.
- `FILM_STILLS=1`: no film, one picture per mark, in real time (a minute and a half): the way to set a framing
  before filming.
- `video-production/`: README, `scripts/clip.sh` (a piece of a step as an MP4 with its sound), `scripts/render.sh`
  (the web file and the poster) and `scripts/elevenlabs.py` (voice, music, effects), after agent-manager-gd's. The
  cut itself (`compose.py`) is written with the storyboard, in FILM-N.
- First scene filmed, `open`: the whole Brain beside the Archivist's panel with a slow push, a thought typed, its
  receipt (« A note on electrical work, filed in Projects › Kitchen renovation, linked to 1 item »). The clip:
  `video-production/output/film-i-open.mp4` (15.5 s, 2 MB, not in git).
- Scripted archivist, no key, no cost. Nothing a user sees changed: Docs, How-to, home page and README are
  untouched by this loop.
- For FILM-K: after a filing the graph moves to the new item, partly under the Archivist's panel (the scene will
  move or fold the panel); three themes borrow another's music (see scene 8).

## SITE-J — the skeleton

- **Menu:** four entries (Features, How-to, Docs, Loops) and GitHub, the same on the four pages (`index`, `docs`,
  `howto` built by `tools/howto/build_page.py`, `semantic`).
- **Index:** « Eleven things it does for you », one tile per feature, and the bar that follows the reader.
- **A section's template:** number and family, a headline that says what the user gets, two lines, one large
  annotated picture (numbered points), the « say it » phrases, « Whole picture ».
- **Two sections written in full** as the model: 01 and 02. The owner corrects the template here, before eight more
  are written on it.
- `tools/check_docs.py` learns: the same menu on every page, as many tiles as sections.

The list of features, to settle in this loop (working titles):

| # | Feature | Today's section |
|---|---|---|
| 01 | Capture anything: text, voice, files, the page in your browser, a folder of notes, a voice memo | Product, Method |
| 02 | The Archivist keeps the door: an agent with directives files whatever comes in; a receipt, Undo, every original kept | Product |
| 03 | A graph with no bottom: from the zones down to the text | Product |
| 04 | Five views and time: Timeline, Focus, Meaning map, Layers; the Brain growing | (Docs only) |
| 05 | Find, ask, connect: by meaning, with sources, the path between two ideas, the web | Product, « How it thinks » |
| 06 | Everything you can click, you can say | Voice |
| 07 | Several minds: Sparring, your own agents, missions | Agents |
| 08 | Every AI tool, your rules: MCP in and out, approvals, Go back | MCP |
| 09 | Recipes, tables, paper: typed items, the table, the grocery list, printing | Product |
| 10 | Alive: seven themes, four sound worlds | Product, Principles |
| 11 | Yours: on your disk, backups, packs, export, open source | Principles, Open source |

**SITE-J done 2026-11-13.** The home page is rebuilt on the branch:

- **Menu:** Features, How-to, Docs, Loops and GitHub, the same on the four pages (the How-to generator too). The
  « How it thinks » page, which had a menu of its own sections, lists them under its hero instead; the home page
  links to it from section 05's band and from its footer.
- **Index** « Eleven things it does for you »: eleven tiles, the Archivist's set apart; **the bar** that follows the
  reader (the eleven, Roadmap, Loops) with its progress line.
- **The template** (`public/css/features.css`, `public/js/features.js`): number and family, headline, two lines,
  a picture with numbered points and a card per point (lines drawn from card to point; under 960 px the cards go
  under the picture), « Whole picture », the « say it » phrases.
- **01 Capture** « Type it, say it, drop it, send it », written in full on a picture of the Captures view: typed,
  spoken, a file, a web page, where it went, what waits for you; the folder of notes in a sentence.
- **02 The Archivist** « One door into your Brain. The Archivist keeps it. », written in full: the door (three ways
  in, one door, the Brain), a filing with its four points, the five directives, and the limit said as it is.
  The earlier block « Drop it in. It is filed before you look up. » is replaced by it.
- **03 to 11** carry today's content under their new numbered heads (Graph, Views and time, Find, Voice, Agents,
  MCP, Recipes-tables-paper, Alive, Yours); 04 and 09, which had no section, show the Docs' pictures for now.
  SITE-L and SITE-M rewrite them on the template. The method (CODE, PARA) and the architecture follow section 11
  until SITE-M places them.
- **Pictures:** `feat-captures.webp` and `feat-receipt.webp`, taken with `FILM_STILLS=1 tools/film.sh open captures`
  at 1920×1080 (the film's own framing and scale).
- **Anchors kept:** `#loops` is the loops' section, `#journal`, `#product` and `#principles` still land.
- **`tools/check_docs.py`** now fails when a page's menu is not the home page's, when the index does not have a
  tile per numbered section in order, when the bar does not follow them, or when the title's count is wrong; both
  were tried on a broken copy. AGENTS.md says so.
- Every new sentence checked against the code or STATUS. Looked at rendered at 1440 px and 480 px.
- The hero is unchanged but for its sentence (« One agent keeps the door… ») and a third button; the film takes the
  demonstration's place at SITE-O.

Old section → new section, so far: Voice → 06; Method → after 11 (to place); Product: intake → 01 and 02, zoom and
originals → 03, paths and web → 05, packs → 11, the gallery → 10; « How it thinks » band → after 05; MCP → 08;
Agents → 07; Principles → 11 (its « Alive » card says what 10 says); Architecture → after 11 (to the Docs at
SITE-M); Roadmap, Loops, Open source: as they were.

## The Archivist, keeper of the door (owner, 2026-11-13)

The owner: « J'aimerais ça mettre de l'avant l'archiviste en tant que gardien des portes. Lui, c'est un agent qui a
des directives, qui va s'assurer que les données sont structurées. […] on peut travailler un peu de texte. »

It becomes the thread of the page and of the film: section 02 is its section, the hero's sentence names it,
sections 07 (agents) and 08 (MCP) come back to « the same door », and scenes 3 and 7 of the film show the same
gesture twice (a receipt after a capture, a receipt after a tool's proposal).

What the code says today (checked 2026-11-13: `engine/brain/archivist.py`, `engine/mcp/proposals.py`,
`engine/assistant/agents.py`), so the text stays true:

- **What comes in goes through it:** anything typed, spoken, dropped or sent is filed by the Archivist; Sparring
  never changes the Brain, its synthesis is filed by the Archivist; an outside AI tool never writes, it proposes.
- **Its directives:** collect and organise, no opinion; file in a project, an area or a resource; use a place that
  fits, create one when none does; under its confidence threshold, ask one short question instead of filing.
- **What it holds a tool's proposal to:** a reason, no duplicate, existing places only, nothing erased, the item
  not changed since it was read; it waits for the user's OK unless the tool is trusted.
- **Every time:** a receipt (where it went and why), the journal with its author, Undo, Go back.
- **The limit, to say as it is:** an agent of the user's own that was given « Organise the graph » moves and links
  by itself (journaled, undoable), and the user changes anything by hand. So the page says « everything that comes
  in », not « nothing else ever writes ».

Words to work with the owner (drafts):

- Headline of section 02: « One door into your Brain. The Archivist keeps it. », or « Nothing comes in unfiled ».
- Two lines: « Whatever comes in, typed, spoken, dropped, or proposed by one of your AI tools, stops at the same
  door. The Archivist is an agent with directives: understand it, file it, link it, and ask when it is not sure. »
- The picture: three ways in (you, your agents, your AI tools), one door, the Brain behind it.
- The hero's sentence: « … One agent keeps the door: the Archivist files whatever comes in, from you or from any
  AI tool, under your rules. »
- The film: « One agent keeps the door. » then « Your AI tools propose. The Archivist decides, under your rules. »
- « Gatekeeper » is the dictionary's word but it often means someone who keeps people out; « keeps the door »
  says the same without it.

## FILM-K — storyboard and scenes

About sixty seconds. A first cut of the story, to settle with the owner before anything is filmed:

1. The graph alive, a slow push. « Meet Second Brain G.D. »
2. Capture: a thought typed, a PDF dropped, a page sent from the browser.
3. The Archivist keeps the door: it files what came in; the receipt, the place that lights up.
4. The zoom, from the zones down to a page of the PDF.
5. The views: Timeline, Focus, Meaning map; ▶ and the Brain grows; Layers (3D).
6. A question, its answer with sources; the path between two ideas.
7. The same door, for an AI tool: it proposes over MCP, « 1 proposal waits », Approve, filed. The scene of Agent
   Manager's film, seen from the Brain's side.
8. The seven themes on the beat, with the app's music changing under them (four sound worlds for seven themes:
   Terminal plays Focus's music, Paper plays Morning's, Neon plays Evening's).
9. The closing card: the logo, « Your second brain. Every AI agent. Your rules. », open source, MIT, the site.

The loop gives the storyboard second by second, the narration's text, every scene filmed and a silent rough cut.
The words are agreed before any voice is generated.

## SITE-L and SITE-M — the sections

- Each section on the template of SITE-J; its picture is a frame of the films (1920×1080) with its numbered points.
- Every claim checked against the code, as in DOC-B. What is planned and not built carries a « Planned » mark.
- **Compare:** the same ground as other note tools, and where this one goes further; no names, no score.
- **« It's a lab »:** the AI notice, your own key, local-first, alpha.
- The roadmap and the loops stay. The architecture goes to the Docs, with a link.
- A table old section → new section in this plan's « Done » note, so nothing is lost without being decided.

## FILM-N — sound and cut

- Narration: one take per line, the storyboard's words.
- Music: one bed composed on the cut, and the app's own tracks in the themes scene. Effects from the app.
- The assistant's own voice (marin) heard once, reading the briefing.
- Master, web file (about 4 MB), poster, and a report as Agent Manager's: what is the real app, what is a stand-in,
  what is illustration, sources and licences, loudness.
- The agent cannot listen: pronunciation (« G.D. ») and the mix are checked by the owner's ear.

## SITE-O — the film on the page, and publication

- The hero: the living graph stays behind; the film takes the place of the scripted demonstration, muted, looping,
  with Sound and pause, a still picture for reduced motion and data saving, a text description. The demonstration
  moves into section 02. (The owner's choice: see below.)
- README: the film's poster and the new list of features. Docs and How-to: the menu, links to the new anchors.
- Phone width (480 px), the pages' weight, `tools/check_docs.py`, the tests, the list of AGENTS.md.
- Merge into `main`, push, then gd-project's publication (its workflow, started by hand or by a dispatch).

## REL-P — the first pre-release

- A version number (see below), the package rebuilt (`tools/package`), its `SHA256SUMS`.
- `tools/release.sh` after Agent Manager's; the tag and the pre-release on GitHub; Docs › Install links to it.

## The film's rules

The real app only, on a private virtual display, with the film Brain. What is not real is named in the report
(a recorded phrase in place of a microphone, a stand-in for an outside service). No secret on screen. Real calls
(the archivist, the voices, the music) cost a little and are counted in the report.

## Decisions for the owner

| Before | Decision | Decided (owner, 2026-11-13) |
|---|---|---|
| SITE-J | Ten or eleven features, and their order | eleven numbered features, as Agent Manager's; the list above as working titles |
| SITE-J | The page's thread | the Archivist as the keeper of the door (section above) |
| FILM-K | The story of the film | the nine scenes above (« parfait, montre-moi ça »): the storyboard is shown to him |
| FILM-N | The narrator's voice | the same as Agent Manager's film (« Eric ») |
| FILM-N | The rights on the ElevenLabs audio (the plan of the account), not confirmed since the audit | **open**: to confirm before anything is published |
| SITE-O | The hero: the film in place of the demonstration, or under an unchanged hero | the film replaces the demonstration (« on remplace le démo exactement ») |
| REL-P | The version's name | an alpha, named by Agent Manager's rule: the number of loops (`v0.50.0-alpha` today) |

## Risks

- The film mode runs slower than real time: what happens outside Godot (the archivist's calls) looks faster in the
  film. Nothing on screen may depend on it.
- The voice scenes need a microphone that a virtual display does not have: a recorded phrase, named as such, or the
  scene is left out.
- A flaky Godot check (« the Captures view lists what came in, newest first ») may fail a loop's tests for no
  reason of its own.
- The terms of synthetic voices (ElevenLabs, OpenAI) on saying that a voice is generated: to read before FILM-N.
- gd-project's own page has no description or topics either: its session's to do.

Each loop ends as usual: tests where code changes, the list of [AGENTS.md](../../AGENTS.md), a « Done » note here,
a commit, an entry in the Brain's journal.
