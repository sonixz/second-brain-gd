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
  `search` (words and meaning), `get_item` (text, fields, links, place), `list_places` (areas, projects, counts),
  `neighbours` (links and related ideas of an item), `path` (how two items connect), `recent`, `inbox`,
  `table` (rows of a type: recipes…), `item_types`. Item text is returned marked as data from the user's Brain
  (captured pages can contain instructions; the client is told they are content, not orders).
- **Lights and log.** The ⇠ in light, a call log (client, tool, time, size), visible in the details panel.
- **Guide.** How-to « Brancher Claude Code sur ton Brain » (FR/EN), screenshots.
- **Real try.** This development session connects to the owner's Brain (read only) and answers a question from it.
- Tests: protocol handshake, tool list per permission, each read tool, token refused / revoked, localhost only,
  the light during a call.

## MCP-B — MCP in, write

- **Levels** per client, like the agents' capabilities: Read · Add (notes, typed items, links, to the Inbox) ·
  Organise (move, link, unlink, file the Inbox, edit fields, create a project, trash).
- **Draft first (default).** Writes from a client wait in a card (« Claude Code propose 12 changements ») to approve
  all, some or none; a switch per client allows direct writes once trusted.
- **Nothing is erased.** Trash only, undoable; every action journaled with its author; **« Undo everything Claude
  Code did in this session »** in one click.
- **Rate limits** (e.g. 60 writes a minute, 500 a session) and a pause switch per client.
- **No double work.** The same journal as the archivist; an item already filed is not filed twice.
- Tests: each write tool at each level, refusals, drafts approved / rejected, session undo, rate limit.

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
