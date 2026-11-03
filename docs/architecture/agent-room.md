# Agent room

Agents (Codex first) work in folders the user chose. The Python engine drives them; Godot only shows what
happens and collects decisions.

## Install (setup step "agents", on by default)

- `engine/agents/manifest.json` pins one official release of `codex-app-server` per platform: the URL on
  `github.com/openai/codex/releases`, its size and its SHA-256 (from the GitHub release API).
- `engine/agents/install.py` (stdlib only) downloads it into `<data>/agents/downloads/*.part`. HTTP Range
  resumes an interrupted download. It checks the fingerprint, extracts the single executable to
  `<data>/agents/codex/<version>/`, and writes `installed.json`. No admin rights, nothing outside the user
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

## Not yet verified

The real `codex-app-server` binary has not run in development yet. The download and fingerprint were
checked by hand for the Linux asset. Running a freshly downloaded binary was blocked by the development
sandbox's safety classifier, and needs the owner's permission. The protocol code follows the official docs
and is tested against `tests/fixtures/agents/fake_codex.py`. Still to confirm with the real binary:
- the exact approval flow under `untrusted` with `read-only`;
- whether `gpt-6-sol` is accepted as the Codex model;
- MXC on the owner's Windows build.
