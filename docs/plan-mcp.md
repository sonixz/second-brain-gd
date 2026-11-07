# Plan: MCP — the Brain as a server (in) and as a client (out)

Agreed with the owner on 2026-11-07 (« c'est quand même un must »). The owner paces each loop. Each loop ends like
the others: Python and Godot suites green, French for every new string, screenshots, docs, commit on loop-32,
fast-forward main, push.

- **MCP in**: the Brain is an MCP server. Claude Code (or Claude Desktop, any MCP client) connects and can read the
  graph, then, with permission, add to it and organise it, like the archivist.
- **MCP out**: the Brain is an MCP client. Remote MCP servers (Microsoft Learn first) become tools for the agents.
- The model on the other side decides when to call a tool; **the Brain decides what is allowed**. Permissions are
  checked here, never trusted to the client.

| Loop | Content | Size | Confidence |
|---|---|---|---|
| MCP-A | MCP in, read: the /mcp endpoint, a token per client, read tools, the lights, the guide, a real try from Claude Code | 1 | 80 % |
| MCP-B | MCP in, write: add and organise, draft-first approval, journal, undo of a whole session, rate limits | 1 | 80 % |
| MCP-C | MCP out: the Connections card, Microsoft Learn first, server tools as agent capabilities, lights per server, costs | 1 | 75 % |
| later | Servers that need a sign-in (OAuth: GitHub, Google), local stdio servers with approval, MCP resources and prompts | — | — |

## Decisions from the owner's review (2026-11-07)

- **A timeline to go back.** Every action is already journaled with its before and after. Restore points: one
  automatically when a client's session starts writing (plus a full backup before its first write), others by hand
  (« point de retour avant le grand ménage »). A timeline of changes (who: you, the archivist, Claude Code, an
  agent; what; when) and « Go back to this moment »: everything after it undone in reverse order, for everyone or
  for one author only; an action whose item was changed since is shown as a conflict, never overwritten silently.
- **Everything that comes in goes through the archivist.** « Add » from a client is a normal capture: the
  archivist files it with the owner's instructions and model (place, themes, links, duplicates); the client may
  suggest a place, the archivist decides. « Organise » actions are checked against the archivist's rules before
  they are applied or drafted. About one filing call per added item.
- **Context cost is a design rule, not a blocker.** Short answers by default (search: 10 hits, 200-character
  snippets; get_item: about 4,000 characters with « more »), lists paged by 25 with a cursor, and `overview`
  instead of « read the whole graph » (places with counts, main themes, recent additions); the client goes down
  where it needs.
- **Two writers at once** (the archivist and Claude Code, or two Claude Codes) is one problem: a single write queue
  in the engine; write tools carry the version of the item they read and get « changed since you read it » instead
  of overwriting; an item being filed by the archivist is held until it is done.
- **The archivist is the only door, told and enforced.** Told: the server's instructions at connection (the
  protocol, and the owner's archivist instructions: places, filing rules), every write tool's description, and
  refusals that explain the protocol (« refused: no source; a proposal needs … »). Enforced: there is no direct
  write tool at all. A client gets `propose_item` (title, content, source, suggested place, reason) and
  `propose_change` (move, link, unlink, field, trash: what and why); the engine checks the format, the archivist
  files or checks it with the owner's rules, then it is applied or drafted per the client's setting; the client
  gets a receipt (« filed in Cuisine, linked to Paella du samedi » / « refused: duplicate of X »). Whether Claude
  Code shows the server's instructions to its model is checked in MCP-A; the single door holds either way.
- **Security for now:** local only (127.0.0.1), a token per client. Endpoint hardening and token management are
  revisited later.

## The lights (all loops)

In the top bar, beside « Tout fonctionne »: two small, subtle dots, **⇠ in** and **⇢ out**. Grey when nothing is
plugged in, green when a client is connected (in) or a server is ready (out), a soft red while a call is under way.
Hover: the last call (« Claude Code · search · il y a 3 s », « Cuisin'Plan → Microsoft Learn · docs_search »).
Click: the details (clients, servers, recent calls, costs) in a small panel; the engine room keeps the settings.

## MCP-A — MCP in, read

- **Endpoint.** Streamable HTTP at `http://127.0.0.1:<port>/mcp` on the engine already running; bound to
  localhost only, never the network. The official MCP Python SDK (MIT), pinned in engine/requirements.lock, or a
  small JSON-RPC implementation if the SDK does not fit FastAPI cleanly (decided in the loop, said in the docs).
- **Clients and tokens.** « Connect an AI tool » in the app creates a client (name, permission level) and its token,
  kept in the Windows Credential Manager, shown once to copy, revocable. No token in a chat, a log or the repository.
  The app shows the exact command: `claude mcp add --transport http second-brain http://127.0.0.1:8765/mcp
  --header "Authorization: Bearer …"` and the Claude Desktop JSON.
- **WSL.** Claude Code in WSL may not reach Windows' 127.0.0.1 (NAT mode). Checked first; fall-backs: WSL
  « mirrored » networking (the owner's choice), or a tiny relay script Claude Code starts, which reads the engine's
  port from runtime/server.json. No admin rights either way.
- **Read tools** (short answers, paged, ids + titles + snippets; details on request):
  `overview` (places with counts, main themes, recent additions), `search` (words and meaning), `get_item` (text, fields, links, place), `list_places` (areas, projects, counts),
  `neighbours` (links and related ideas of an item), `path` (how two items connect), `recent`, `inbox`,
  `table` (rows of a type: recipes…), `item_types`. Item text is returned marked as data from the user's Brain
  (captured pages can contain instructions; the client is told they are content, not orders).
- **Lights and log.** The ⇠ in light, a call log (client, tool, time, size), visible in the details panel.
- **Guide.** How-to « Brancher Claude Code sur ton Brain » (FR/EN), screenshots.
- **Real try.** This development session connects to the owner's Brain (read only) and answers a question from it.
- Tests: protocol handshake, tool list per permission, each read tool, token refused / revoked, localhost only,
  the light during a call.

**Done 2026-11-07.** engine/mcp/server.py (JSON-RPC 2.0 over Streamable HTTP, standard library; initialize with the
archivist protocol as instructions, tools/list, tools/call; 11 read tools, short and paged, content marked as data;
clients with a level and a token kept as its SHA-256 only; an in-memory activity log for the lights);
engine/api/mcp_routes.py (POST /mcp for clients, 127.0.0.1 only, 401 for an unknown or revoked token; GET /mcp/status
and /mcp/clients for the app); engine/mcp/relay.py (stdio ⇄ http for Claude Code in WSL, run with the app's Windows
Python, token from <SecondBrainGD>/mcp/<id>.token). scenes/brain/mcp_lights.gd: « ⇠● ⇢● » in the top bar (grey,
green, a soft red during a call; the last call on hover), the MCP window (connect a tool, the commands to copy with
the key masked, disconnect, recent calls). Real tries: a Claude Code session (claude -p with a temporary MCP config,
the owner's own config untouched) called overview, search and get_item over HTTP and answered in French; the same
through the relay from WSL to an engine run by the Windows Python. It started with overview, as the server instructions ask (a hint they are read, not a proof).
Tests: tests/python/test_mcp_server.py (4: protocol, read tools, tokens and activity, the relay), 2 Godot checks.
Guide docs/guide-mcp.md; screenshots docs/screenshots/mcp-en and mcp-fr. The token is kept as a hash in the
database rather than in the Credential Manager (nothing to steal; the relay's token file lives in the user's folder).

## MCP-B — MCP in, write

- **Levels** per client: Read · Propose items (`propose_item`) · Propose changes (`propose_change`). No direct write
  tool exists; both go through the archivist (see « The archivist is the only door »).
- **Draft first (default).** Writes from a client wait in a card (« Claude Code propose 12 changements ») to approve
  all, some or none; a switch per client allows direct writes once trusted.
- **Through the archivist.** Added items are captures the archivist files with the owner's instructions;
  organise actions are checked against its rules.
- **Nothing is erased.** Trash only, undoable; every action journaled with its author; **« Undo everything Claude
  Code did in this session »** in one click; restore points and the timeline of changes (« go back to this moment »),
  a full backup before a session's first write.
- **One writer at a time.** A single write queue; version checks (« changed since you read it »); items being filed
  are held.
- **Rate limits** (e.g. 60 writes a minute, 500 a session) and a pause switch per client.
- **No double work.** The same journal as the archivist; an item already filed is not filed twice.
- Tests: each write tool at each level, refusals, drafts approved / rejected, session undo, rate limit.

**B1 done 2026-11-07.** Migration 0017 (mcp_proposals; mcp_clients.direct; assistant_actions.author).
engine/mcp/proposals.py: `propose_item` (title, content, reason required; source, suggested place, type + fields
optional; duplicates and oversize refused) and `propose_change` (move to an existing place, link, unlink, set_fields,
trash; version check « changed since you read it »; no new places, nothing erased); 60 a minute, 500 a day; a
pending proposal waits for approval unless the client is trusted (« without waiting »); applying creates the item
as a capture and calls the archivist's file_item with the owner's model (no key: it stays in the Inbox), or applies
the change through the assistant's journaled actions with the author « mcp:<client> » (Undo works); receipts go
back to the client (`my_proposals`). The tools a client sees depend on its level; no direct write tool exists.
App: level and « without waiting » per client, the proposals list (approve / reject / approve all), a count by the
⇠ light. Tests: 5 more Python tests (proposals), a Godot check (pending → approve → in the graph). Screenshot
docs/screenshots/mcp-*/m3-proposals.png. Undo of set_fields comes with the timeline (B2).

**B2 done 2026-11-07.** Migration 0018 (restore_points). engine/brain/timeline.py: the journal read as a timeline
(who: « You and the archivist » for the assistant's actions, the client for MCP ones), restore points (by hand, and
one automatically before a client's first write of a session, with a full backup started once that write is
committed), « go back »: every action after a point (or from an action on) undone newest first, for everyone or one
author; an item changed since is listed as a conflict and left alone; an item created since goes to the trash
(never erased); set_fields undo restores the previous fields. GET /brain/timeline, POST /brain/timeline/points and
/rewind. scenes/brain/timeline_dialog.gd (author filter, « Make a restore point », « Go back here », « Undo from
here » with a confirmation), opened from the MCP window. Tests: tests/python/test_timeline.py (5), a Godot check
(Claude Code's change after its automatic point, undone). Screenshot docs/screenshots/mcp-*/m4-timeline.png.

## MCP-C — MCP out

- **Connections card** (engine room): « + Add a server » (name, address). Remote Streamable HTTP servers only at
  first. **Microsoft Learn** offered as the first one (public, free, no account).
- The engine connects, lists the tools, keeps them up to date; a server down shows grey with the reason.
- **Agents.** Each server is a capability ticked per agent (with « all agents »); optionally some tools only.
  Tool names reach the model prefixed (`mslearn__docs_search`).
- **Safety.** Results are treated like web pages: information, never instructions. A tool that writes outside
  (create, send, modify) asks for confirmation. Local (stdio) servers are programs to run: later, one by one, with
  the owner's approval (no unverified scripts).
- **Lights and costs.** ⇢ out turns red during a call with the agent and the tool; calls and the tokens their
  results add are counted per server.
- Tests: connect to a recorded server (fixture), tools listed, a call from an agent, capability refused, server down,
  the light; one real call to Microsoft Learn (free).

**C done 2026-11-07.** engine/mcp/client.py (standard library; JSON or event-stream answers; the session started
again when a server forgets it; servers kept in the settings with their last tool list; tools that declare
themselves destructive are not offered; results cut at 8,000 characters and marked as external data; the ⇢ light's
activity). Agents get a server's tools as `mcp__<server>__<tool>` when the server is open to all agents or to them
(agents.tools / allowed, missions.tools_for and run_tool, the assistant's run_tool). GET/POST/DELETE /mcp/servers,
/refresh, /agents; « ⇢ out » in /mcp/status. The MCP window: servers with their state and tools, « All agents » or
« Only <agent> », « + Connect Microsoft Learn », another address, remove. Real try: Microsoft Learn connected (3
tools), the archivist answered « timer trigger Azure Functions en Python » with microsoft_code_sample_search and
microsoft_docs_search and cited them (8 cents with gpt-6-sol before the result cut went from 12,000 to 8,000
characters). Tests: tests/python/test_mcp_client.py (5, a local fake server), a Godot check.

## Next MCP loops (agreed 2026-11-07): the full client, so the Brain can use most servers listed in directories

MCP directories (mcpmarket.com and the like) are catalogues, not services: what is plugged in is the servers they
list. They come in four families: remote without an account (works since MCP-C), remote with an API key, remote
with an account sign-in (OAuth), local programs (stdio). One complete client serves them all; around it, the
Brain keeps what the protocol does not do: permissions, secrets, budget, trust, data guards, visibility.

| Loop | Content | Size | Confidence |
|---|---|---|---|
| MCP-D | API keys per server, the catalogue (a curated list + search in the official MCP registry), tool-by-tool permissions, a budget, the « Brain read + outside write » guard, protocol gaps (paging, listChanged, progress, cancel, the older SSE transport) | 1 | 80 % |
| MCP-E | Account sign-in (OAuth): discovery, browser sign-in back to 127.0.0.1, client registration, refresh, disconnect; server questions (elicitation) shown like mission questions; sampling refused by default | 1 | 65 % |
| MCP-F | Local servers (stdio) with the owner's approval: the exact command shown, version pinned, nothing downloaded or installed silently, a clean environment (no secrets inherited), start / stop / logs | 1 | 60 % |

### MCP-D — keys, catalogue, permissions, budget, guard

- **API keys.** A server can carry a key (header name and value, e.g. `Authorization: Bearer …` or `x-api-key`),
  kept in the Windows Credential Manager (engine/voice/secrets.py), never in the settings, a log or the repository;
  shown masked, replaceable, removed with the server.
- **Catalogue.** In the MCP window: a curated starter list (Microsoft Learn, Context7, DeepWiki…, each checked by
  hand: no account / key / sign-in / local), and a search in the official MCP registry (its API and format checked
  at the start of the loop; no scraping of directory sites). Each entry shows its family, publisher and source; an
  unknown publisher gets a warning. One click for « no account », a key field for « key ».
- **Tool by tool.** Per server and per agent, tools can be switched off (fewer tools: a sharper agent, fewer tokens
  each turn). The window shows how many tool descriptions each agent carries.
- **Budget.** Calls and the tokens their results add are counted per server, agent and mission; a monthly cap per
  server (default off) and the missions' own cost cap include MCP results.
- **Data guard.** A tool that writes outside (no readOnlyHint, or destructiveHint) asks the owner's confirmation at
  each call (a card like the mission questions); the window warns when an agent has both « Read the Brain » and a
  server that can write outside.
- **Protocol gaps.** tools/list paging (cursor), notifications/tools/list_changed (refresh), progress shown on the
  ⇢ light's hover, a Stop that cancels a long call (notifications/cancelled), the 2024-11-05 HTTP+SSE transport
  for older servers.
- Tests: a fake server with a key, paging and a write tool; the guard; the budget; one real call to a keyless
  catalogue server.

**D done 2026-11-07.** Migration 0019 (mcp_usage, mcp_confirms). engine/mcp/client.py: a key per server in the OS
credential store (provider « mcp-<id> »; « Bearer » added for Authorization), tools/list paging, every tool kept
with `write` (not declared read-only), tools switched off per server, monthly usage (calls, result characters ÷ 4)
and an optional cap, the outside-write guard (a pending confirmation per exact call, « Allow once » good for 15
minutes, a refusal remembered), `risks` (agents reading the Brain with a writing server), event streams read as
they come (progress on the ⇢ hover, « Stop the calls under way » cancels and tells the server), the 2024-11-05
HTTP+SSE transport (GET stream, « endpoint » event, answers on the stream); a 401 says « add the key ».
engine/mcp/catalog.py: the official registry (`/v0/servers?search=&version=latest`), each entry with its family
(open / key / local; « sign-in » is discovered on connect until MCP-E), publisher from its namespace, source.
Curated list checked by hand: Microsoft Learn, Context7, DeepWiki, Exa (all answered without an account). The MCP
window scrolls; per server: tools on/off (✎ for writing ones), key, monthly budget, usage; confirmations and risk
warnings; the catalogue (curated buttons, registry search, a pasted address). Not done: per-agent tool lists (per
server only), listChanged (no standing stream; « refresh » and a reconnect cover it). Real calls: DeepWiki and the
registry search, free. Tests: test_mcp_client.py (10: paging, guard, keys, off/agents/budget, progress and Stop,
session restart, the older transport, catalogue families). Screenshot docs/screenshots/mcp-*/m5-catalogue.png.

### MCP-E — account sign-in (OAuth), server questions

- **OAuth per the MCP spec.** Discovery (`/.well-known/oauth-protected-resource`, then the authorization server's
  metadata), dynamic client registration when offered, PKCE, the sign-in in the user's browser with a redirect to a
  one-time listener on 127.0.0.1, tokens in the Credential Manager, refresh before expiry, « Disconnect » revokes.
- First provider tried for real: one the owner uses (Notion or GitHub), chosen at the start of the loop.
- **Elicitation:** a server's question to the user (« which project? ») shown in the agent's panel like a mission
  question; the answer goes back. **Sampling:** a server asking the Brain's model to write is refused by default
  (it would spend the owner's key), allowed per server with a cap.
- Tests: a fake authorization server (discovery, registration, PKCE, refresh, expiry), an elicitation round trip.

**E done 2026-11-07.** engine/mcp/oauth.py: discovery (WWW-Authenticate resource_metadata, protected-resource
metadata, authorization-server metadata with OpenID fallback, S256 required), dynamic registration as a public
client, PKCE, a one-time listener on 127.0.0.1 (5 minutes), the code exchanged with the verifier and `resource`,
tokens in the OS credential store (« mcp-<id>-oauth »), refreshed when about to expire and once on a 401,
« Disconnect » revokes at the server. The client: a 401 with a Bearer challenge marks the server « needs an
account sign-in »; `elicitation` declared at initialize, the server's question shown in the MCP window (fields
from its flat schema) and the call waits up to 85 s for the answer (a chat waits 90 s); `sampling` declared only
when the user allows it for that server (off by default, 20 a month, gpt-4o-mini, counted); ping and roots
(none shared) answered. Migration 0020 (mcp_questions). Window: « Sign in » (opens the browser, waits),
« Disconnect the account », the sampling switch, questions with Answer / Decline. Real check: Notion's discovery
up to its sign-in URL (read only; nothing registered until the owner clicks). Tests: test_mcp_oauth.py (4: the
whole sign-in with a fake authorization server, refresh, revoke; a question answered; sampling refused then
allowed; challenge parsing). Screenshot docs/screenshots/mcp-*/m6-signin.png. The owner's first real sign-in is
theirs to do (Notion or GitHub).

### MCP-F — local servers (stdio), with approval

- Adding a local server shows the exact command (e.g. `npx -y @scope/server@1.2.3`), its publisher and source; the
  owner approves it once; the version is pinned (no « latest »). Required runtimes (Node, Python, Docker) are
  detected, never installed silently: the window says what is missing and how to get it.
- The process runs with a clean environment (no inherited secrets; only the variables the server declares, filled
  from the Credential Manager), stopped with the app, restarted on demand; its stderr kept as a short log.
- Same permissions, guard, budget and lights as remote servers.
- Tests: a tiny local stdio server written in the test (Python), start / list / call / stop, a crash, a refused
  unapproved command.

## Later

MCP resources and prompts (both directions; items as `brain://` resources), Claude Desktop extension packaging.
