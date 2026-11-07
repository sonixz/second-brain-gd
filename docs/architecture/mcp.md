# MCP: the Brain as a server and as a client

The Model Context Protocol (MCP) is a standard plug between AI tools and the tools they use. The Brain speaks it in
both directions, with the standard library only (JSON-RPC 2.0).

## In: AI tools read the Brain and propose (engine/mcp/server.py, proposals.py, relay.py)

- **Endpoint.** `POST /mcp` on the engine (Streamable HTTP, plain JSON answers), **127.0.0.1 only**. `GET` answers
  405 (no standing stream). `initialize` returns the server's instructions: the archivist protocol below.
- **Clients and tokens.** « Connect (read only) » (tab « Who may read your Brain ») creates a client with a level; its token is shown once and only its
  SHA-256 is kept (`mcp_clients`). Unknown or revoked tokens get 401.
- **WSL relay.** Claude Code in WSL starts `engine/mcp/relay.py` with the app's Windows Python: stdio on one side,
  `http://127.0.0.1:<port>/mcp` on the other (port from `runtime/server.json`, token from `<data>/mcp/<id>.token`).
- **Read tools** (short and paged): overview, search, get_item (4,000 characters at a time), list_places,
  list_items, neighbours, path, recent, inbox, item_types, table. Item text is returned marked as the user's data,
  never as instructions.
- **The archivist is the only door.** There is no direct write tool. By level a client gets `propose_item` and
  `propose_change` (move to an existing place, link, unlink, set fields, trash). The engine checks the format, a
  reason, duplicates, and the item's version (« changed since you read it »); proposals wait for the owner's
  approval (`mcp_proposals`) unless the client is trusted; applying goes through the archivist (filing) or the
  assistant's journaled actions, with the author « mcp:<client> ». 60 proposals a minute, 500 a day.
- **Timeline** (`engine/brain/timeline.py`): the journal (`assistant_actions`, with `author`) read as who did what;
  restore points (`restore_points`), one automatic before a client's first write of a session plus a full backup;
  « go back » undoes later actions newest first, for everyone or one author; an item changed since is a conflict,
  left alone; created items go to the trash.
- **Lights.** An in-memory activity log feeds « ⇠ in » (grey, green, red during a call) in the top bar.

## Out: agents use MCP servers (engine/mcp/client.py, catalog.py, oauth.py, local.py)

- **Transports.** Streamable HTTP (JSON or an event stream read as it comes: progress, Stop), the older HTTP+SSE
  (2024-11-05: GET stream, `endpoint` event), and stdio for local programs. Sessions are started again when a
  server forgets them; tool lists are followed through their cursor.
- **Servers** live in the setting `mcp_servers` (name, address or command, agents allowed, tools switched off,
  monthly cap, state). Their tools reach an agent's model as `mcp__<server>__<tool>`; results are cut at 8,000
  characters and marked as external data.
- **Keys** per server and **OAuth tokens** live in the OS credential store (`mcp-<id>`, `mcp-<id>-oauth`), never in
  the settings. OAuth follows the MCP spec: WWW-Authenticate → protected-resource metadata → authorization-server
  metadata, dynamic registration as a public client, PKCE S256, a one-time listener on 127.0.0.1, refresh, revoke.
- **Guard.** A tool not declared read-only waits for the owner's « Allow once » at each call (`mcp_confirms`, 15
  minutes for that exact call); agents that read the Brain and may write outside are flagged. Usage per server and
  agent is counted (`mcp_usage`).
- **Server requests.** ping and roots (none shared) are answered; a question (elicitation) is shown to the owner
  (`mcp_questions`) and the call waits up to 85 s; sampling (the server asking the Brain's model) is refused unless
  allowed for that server (20 a month, gpt-4o-mini).
- **Local programs.** One program with its arguments, version pinned, approved by its exact command (a changed
  command needs a new approval); the runtime (Node, uv, Docker) is detected, never installed; a clean environment
  (paths and user folders, plus only the variables the server declares); no window; stopped with the app; a log.
- **Catalogue.** A hand-checked list and the official registry (`registry.modelcontextprotocol.io/v0/servers`), each
  entry with its family (open, key, local; sign-in discovered on connect), publisher and source.
- **Lights.** « ⇢ out » turns green when a server is ready, red during a call (progress on hover).
