-- 0003_assistant: the assistant's conversation and a journal of everything it changed.

CREATE TABLE IF NOT EXISTS assistant_messages (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation  TEXT NOT NULL,             -- 'daily-YYYY-MM-DD' or 'space-<id>'
    role          TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'tool', 'briefing')),
    content       TEXT NOT NULL,
    meta          TEXT,                      -- JSON: tool calls, cited notes, usage
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assistant_messages_conv ON assistant_messages (conversation, id);

-- Every change the assistant makes is recorded with the state before it, so it can be undone.
CREATE TABLE IF NOT EXISTS assistant_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,               -- classify | create_note | update_note
    note_id     TEXT,
    before      TEXT,                        -- JSON
    after       TEXT,                        -- JSON
    reason      TEXT,
    created_at  TEXT NOT NULL,
    undone_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_assistant_actions_note ON assistant_actions (note_id);
