# Plan: importing a folder (Obsidian and other note apps)

Agreed with the owner on 2026-11-06. Planned after Loop 37; the order with routines and @ mentions is the
owner's call. Today a `.md` file goes through the archivist as plain text: front matter and `[[links]]` are
read as text, folders are ignored, a whole folder cannot be dropped, and each note costs a model call.

**Principle: one generic gesture, the source is detected, never put forward.** The button says « Import a
folder… » (and a folder can be dropped on the window). The app recognises what it is given and says so in the
preview (« Obsidian vault detected »). Other apps are named only in that detection line and in the docs
(« Compatible with Obsidian, Logseq… »), never as the interface.

## Import A — Import a folder (about one loop)

- **Entry points.** « Import a folder… » next to adding files; dropping a folder on the window; by voice
  « importe mon vault Obsidian », « importe le dossier Documents/Notes ».
- **Detection.** `.obsidian/` → Obsidian vault. `.md` with `[[links]]`, no `.obsidian/` → linked notes.
  Plain `.md` → Markdown folder. Mixed PDF, Word, text → documents folder (each file through the archivist,
  as today).
- **Mapping, read without a model.** Each note becomes an item with its text. Front matter → type, themes,
  date, source and extra properties. `[[Note]]`, `[[Note|alias]]`, `[[Note#heading]]` → explicit links (the
  author's). A link to a missing note → a « to create » node. `#tags` → themes. Folders → PARA places,
  kept as they are by default. `.obsidian/`, `.trash/` and hidden folders are skipped.
- **Preview before anything enters**: the detected source, counts (notes, links, attachments, folders,
  unresolved links), organisation (keep your folders, by default, or let the archivist re-file), estimated
  cost (meaning vectors; structure is free), missing summaries (generate now or later).
- **A layer, like packs**: switch on or off, remove; nothing is lost if the result is not liked.
  Re-importing the same folder adds only new or changed notes (content hash).
- **The archivist only fills gaps**: a summary when there is none, a place for notes at the root, then links
  by meaning on top of the manual links.
- **Tests** on a small synthetic vault written for the tests (front matter, aliases, headings, missing
  links, tags, nested folders, odd Windows names).

## Import B — Attachments, other apps and real vaults (about one loop)

- **Attachments.** `![[image.png]]`, `![[file.pdf]]` and Markdown images → originals attached to their note.
- **Logseq** (`logseq/` folder, `pages/` and `journals/`): outline blocks, `key:: value` properties, journal
  pages by date.
- **Notion export** (Markdown + CSV, file names ending with a 32-hex id): ids stripped from titles and links,
  each CSV database row → an item.
- **Real vaults.** The owner imports public vaults locally to try it. Only permissively licensed ones may
  become repo fixtures or screenshots (kepano/kepano-obsidian, MIT; SoRobby/ObsidianStarterVault, MIT;
  logseq/docs, MIT). obsidianmd/obsidian-help has no licence: local tests only, never in the repo or on the
  site.
- **A How-to guide** « Bring your Obsidian vault » and a showcase capture.

## Later — more sources, and the way out

- Other detections, one at a time, by demand: Evernote `.enex`, Bear (TextBundle), Joplin export, Day One
  JSON, Google Keep (Takeout), Roam JSON, Dendron (`dendron.yml`), Foam.
- **Markdown mirror** (the way out): the Brain written as a Markdown folder that opens in Obsidian, then the
  watched folder for edits made there, then possibly files as the source of truth with SQLite as a
  rebuildable index (see the roadmap).
