-- 0017_mcp_proposals: what MCP clients propose (Loop MCP-B1). A client never writes: it proposes an item to add or a
-- change to make; the archivist files or checks it with the user's rules; it is applied at once (a trusted client)
-- or waits for the user's approval. Every applied action is journaled with its author (for the timeline, MCP-B2).

CREATE TABLE IF NOT EXISTS mcp_proposals (
    id          TEXT PRIMARY KEY,
    client_id   TEXT NOT NULL,
    client_name TEXT NOT NULL,
    kind        TEXT NOT NULL,                  -- item, change
    payload     TEXT NOT NULL,                  -- JSON, as proposed (after the format check)
    status      TEXT NOT NULL DEFAULT 'pending', -- pending, applied, rejected, failed
    receipt     TEXT,                           -- what happened, in one sentence (sent back to the client)
    note_id     TEXT,
    created_at  TEXT NOT NULL,
    decided_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_mcp_proposals_status ON mcp_proposals (status, created_at);

ALTER TABLE mcp_clients ADD COLUMN direct INTEGER NOT NULL DEFAULT 0;   -- 1: proposals applied without waiting
ALTER TABLE assistant_actions ADD COLUMN author TEXT;                   -- who did it: assistant, archivist, a client…
