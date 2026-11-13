# Agents

Read AI-NOTICE.md first: this is a lab, run on one person's computer. Never expose an engine, an MCP server or their
ports beyond the local machine unless the owner asks for it explicitly (owner, 2026-11-10).

## Documentation is part of the work (owner, 2026-11-11)

The repository is public: what a visitor reads must match what the app does, every time, not when someone thinks of
it. A loop, or any change a user can see, is done only when each line below is either up to date in the same branch,
or written in BACKLOG.md as left to do, with the reason. Go through the list before merging into `main`, against the
whole branch and not only its last commit, and say in your report what was updated and what was left.

- **DEVLOG.md:** an entry for the loop, newest first; its plan in `docs/plans/` gets a « Done » note.
- **STATUS.md and BACKLOG.md:** what works today, the tests' numbers and their date, what is next.
- **Docs** (`public/docs.html`): the feature's section says what it does now, and what to say to drive it by voice.
- **How-to** (`public/howto.html`): a feature that is a task gets a guide (`tools/howto/guides.py`,
  `tools/howto.gd`); a guide whose screens changed is captured again with `tools/howto.sh <guide>`, words and
  pictures together.
- **The website's home page** (`public/index.html`): a card in the loops list when the loop changes what a user
  sees; no sentence left that has stopped being true.
- **README.md and `docs/architecture/`:** when the feature list or the way the pieces talk changed.

`python3 tools/check_docs.py` (the tests run it) fails on a dead link, a missing picture, an anchor that no longer
exists, a guide that never reached the How-to page, a loop count gone stale on the home page, a page whose menu
is not the home page's, or an index of features that no longer matches the numbered sections. It cannot tell
whether a sentence is still true: that part is yours. The catch-up of 2026-11-11 shows the work one loop's
documentation takes: [docs/plans/plan-docs-catchup.md](docs/plans/plan-docs-catchup.md).

The other rules every change follows (tests, English and French, no secrets, real screenshots) are in
CONTRIBUTING.md.
