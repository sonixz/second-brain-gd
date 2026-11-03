# Agent room

Agents (Codex first) work in folders the user chose. The Python engine drives them; Godot only shows what
happens and collects decisions.

## Install (setup step "agents", on by default)

- `engine/agents/manifest.json` pins one official `codex-app-server-package-<target>.tar.gz` per platform:
  the URL on `github.com/openai/codex/releases`, its size and its SHA-256 (from the GitHub release API).
  It must be the **package**, not the bare `codex-app-server` asset. The app-server looks for companion
  binaries next to itself, and without them every tool call fails with "failed to spawn code-mode host".
  The companions are `bin/codex-code-mode-host` and `bin/codex-exec-server`, ripgrep in `codex-path/`, and
  in `codex-resources/` `bwrap` on Linux, or the command runner and sandbox setup on Windows.
- `engine/agents/install.py` (stdlib only) downloads it into `<data>/agents/downloads/*.part`. HTTP Range
  resumes an interrupted download. It checks the fingerprint and unpacks the whole package
  into `<data>/agents/codex/<version>/`. It unpacks to a staging folder first, then swaps it in, and only
  accepts plain files and folders with relative paths. Then it writes `installed.json` and removes older
  versions. No admin rights, nothing outside the user
  data folder, and nothing is executed during install.
- The step is never fatal. Offline or on a failed check, it ends with status `unavailable`, setup succeeds,
  and the agent room offers **Install agents** (`POST /agents/install`, progress in `/agents/status`).
- Test hook: `SBGD_AGENTS_MANIFEST` points to `tests/fixtures/agents/manifest.json`, a tiny archive holding
  a fake app-server script (`tools/make-agent-fixture.py` rebuilds it). `SBGD_AGENTS=off` skips the step.

## Sessions (`engine/agents/session.py`)

Protocol: Codex app-server, newline-delimited JSON-RPC over stdio (documented at
learn.chatgpt.com/docs/app-server). Lifecycle:

1. Start the binary with `CODEX_HOME=<data>/agents/home`, so the user's own `~/.codex` is never touched. The
   working directory is the chosen folder. `OPENAI_API_KEY` is removed from its environment.
2. `initialize` with `clientInfo`, then the `initialized` notification.
3. `account/login/start` with `{type: "apiKey", apiKey}`: the user's key travels over stdin only, never in
   argv, env or logs. When the session stops, any `auth.json` the agent wrote in `CODEX_HOME` is deleted.
4. `thread/start` with `cwd`, `model` (default `gpt-6-sol`), `approvalPolicy` (default `untrusted`) and
   `sandbox` (default `read-only`). Writes and untrusted commands therefore ask first.
5. Each user message is a `turn/start`. Notifications become small UI events: `delta`, `item` (agent
   message, command with trimmed output, file change with trimmed diffs), `turn_started`, `turn_completed`.
6. `item/fileChange/requestApproval` and `item/commandExecution/requestApproval` become `approval` events
   and wait for the user (`accept`, `acceptForSession`, `decline`, `cancel`). The engine refuses other server
   requests: permission escalations, user-input prompts and MCP elicitations.

Routes: `/agents/status`, `/agents/install`, `/agents/settings`, `/agents/folders` (add or remove; whole
drives, the home folder and the app's data folder are refused), `/agents/sessions` (at most 4 live),
`/agents/sessions/{id}?after=N` (polling), `/messages`, `/approvals/{request_id}`, `/interrupt`, and DELETE.

## Windows sandbox

Per OpenAI's docs, the MXC sandbox (Windows 11 24H2 and later) needs no admin setup, and the `unelevated`
fallback avoids admin too. Only the `elevated` mode needs a one-time admin setup. Second Brain GD never asks
for admin rights.

## Verified with the real Codex (2026-11-03, rust-v0.166.0)

The run was approved by the owner. It used the real package, the owner's key (from dotenvx, over stdin),
`gpt-6-sol`, `untrusted` and `read-only`. The prompt was « crée notes.txt et dis-moi ce que contient
readme.txt ».

| | Linux (WSL) | Windows 11 native |
|---|---|---|
| Install (download, SHA-256, unpack) | 14 s, 398 MB on disk | 13 s, 458 MB on disk |
| Thread ready | 1.2 to 2.2 s | 2.5 s |
| Full turn with 3 or 4 approvals | 11 s | 11.6 s |
| Shell used by the agent | bash, with the bundled `rg` and `bwrap` | PowerShell, no admin |

- **Approvals.** Every command (even `cat`) and every file change asked first.
  - Decline: nothing ran or changed, and the agent explained that access was refused.
  - Accept: the file was created and read back.
- **Decisions.** For commands, the server suggests only `accept` and `cancel`, while file changes offer
  all four.
  - `decline` is accepted for commands too and lets the agent carry on. `cancel` would end the turn.
  - So the engine always adds Decline to the card. Without it, a command could only be approved.
- **Model.** `gpt-6-sol` is accepted as the Codex model.
- **Secrets.** No file under `CODEX_HOME` contains the key, and `auth.json` is absent after the session.
- **Warnings seen.**
  - Linux: "bubblewrap not on PATH", after which Codex uses the bundled copy.
  - Windows: under a temporary folder, Codex declines to create PATH aliases. The app's data folder is not
    temporary.
