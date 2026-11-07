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

## Later

OAuth servers (GitHub, Google…), local stdio servers with approval, MCP resources (items as `brain://` resources)
and prompts, Claude Desktop extension packaging.
