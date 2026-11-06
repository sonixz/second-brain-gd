-- 0014_missions: an agent's mission (Loop 32): a real job carried out in the background ("this week's menu from
-- the grocery specials"), with a plan, findings, a question when it needs the user's choice, a draft to approve,
-- and the items it saved once approved. Survives a restart: a running mission resumes where it was.

CREATE TABLE IF NOT EXISTS missions (
    id            TEXT PRIMARY KEY,
    agent         TEXT NOT NULL,
    goal          TEXT NOT NULL,
    status        TEXT NOT NULL,          -- running, waiting, draft, saved, stopped, failed
    model         TEXT,
    plan          TEXT NOT NULL DEFAULT '[]',   -- [{title, status: todo|done|skipped, note}]
    findings      TEXT NOT NULL DEFAULT '{}',   -- {kind: [rows]}
    question      TEXT,                         -- {question, choices, multiple} while waiting
    draft         TEXT,                         -- {title, summary, place, items: [...]}
    feed          TEXT NOT NULL DEFAULT '[]',   -- what the agent did, newest last (kept short)
    messages      TEXT NOT NULL DEFAULT '[]',   -- the model conversation, to resume
    result        TEXT,                         -- {note_ids, place, action_id} once saved
    reason        TEXT,                         -- why it stopped or failed
    cost          REAL NOT NULL DEFAULT 0,
    rounds        INTEGER NOT NULL DEFAULT 0,
    elapsed_s     REAL NOT NULL DEFAULT 0,      -- working time only (not while waiting for the user)
    max_cost      REAL NOT NULL,
    max_minutes   REAL NOT NULL,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS missions_status ON missions (status, updated_at);
