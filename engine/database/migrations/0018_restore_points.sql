-- 0018_restore_points: named moments to come back to (Loop MCP-B2). A point remembers the last journaled action at
-- that moment; « go back to this moment » undoes, newest first, every action after it (for everyone or one author).

CREATE TABLE IF NOT EXISTS restore_points (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    action_id   INTEGER NOT NULL DEFAULT 0,   -- the last assistant_actions.id when the point was made
    auto        INTEGER NOT NULL DEFAULT 0,   -- 1: made by the app (a client's session starting to write)
    author      TEXT,                         -- the client whose session it opens, for an automatic point
    created_at  TEXT NOT NULL
);
