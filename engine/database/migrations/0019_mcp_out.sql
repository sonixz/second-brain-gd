-- 0019_mcp_out: MCP servers used by the agents (Loop MCP-D): what each server costs this month (calls and the size
-- of its answers, read by the agents' model), and the confirmations a tool that writes outside waits for.

CREATE TABLE IF NOT EXISTS mcp_usage (
    month   TEXT NOT NULL,              -- YYYY-MM
    server  TEXT NOT NULL,
    agent   TEXT NOT NULL,
    calls   INTEGER NOT NULL DEFAULT 0,
    chars   INTEGER NOT NULL DEFAULT 0,  -- characters of results handed to the model (about 4 per token)
    PRIMARY KEY (month, server, agent)
);

CREATE TABLE IF NOT EXISTS mcp_confirms (
    id          TEXT PRIMARY KEY,
    server      TEXT NOT NULL,
    server_name TEXT NOT NULL,
    tool        TEXT NOT NULL,
    args        TEXT NOT NULL,              -- JSON, as the agent asked
    args_hash   TEXT NOT NULL,
    agent       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending, approved, refused, used
    created_at  TEXT NOT NULL,
    decided_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_mcp_confirms ON mcp_confirms (status, args_hash);
