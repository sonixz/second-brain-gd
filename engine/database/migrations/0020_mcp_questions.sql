-- 0020_mcp_questions: a question an MCP server asks the user during a call (elicitation, Loop MCP-E): shown in the
-- MCP window, answered (or declined) by the user; the waiting call then goes on with the answer.

CREATE TABLE IF NOT EXISTS mcp_questions (
    id          TEXT PRIMARY KEY,
    server      TEXT NOT NULL,
    server_name TEXT NOT NULL,
    agent       TEXT NOT NULL,
    message     TEXT NOT NULL,
    schema      TEXT NOT NULL DEFAULT '{}',     -- JSON schema of the fields asked (flat: strings, numbers, booleans, choices)
    status      TEXT NOT NULL DEFAULT 'pending', -- pending, answered, declined, cancelled, expired
    answer      TEXT,
    created_at  TEXT NOT NULL,
    answered_at TEXT
);
