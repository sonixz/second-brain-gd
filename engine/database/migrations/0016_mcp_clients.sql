-- 0016_mcp_clients: AI tools connected to the Brain over MCP (Loop MCP-A). Each client has its own token (only its
-- SHA-256 is kept here) and a permission level; the Brain checks every call against it.

CREATE TABLE IF NOT EXISTS mcp_clients (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    level       TEXT NOT NULL DEFAULT 'read',   -- read, propose_items, propose_changes
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    last_seen   TEXT,
    calls       INTEGER NOT NULL DEFAULT 0,
    revoked_at  TEXT
);
