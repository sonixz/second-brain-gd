-- 0004_structure: PARA structure. Spaces become real cards (areas own projects),
-- tasks get due dates, and checklists (groceries, packing lists...) appear.

ALTER TABLE spaces ADD COLUMN goal TEXT;
ALTER TABLE spaces ADD COLUMN why TEXT;
ALTER TABLE spaces ADD COLUMN due_date TEXT;            -- YYYY-MM-DD, projects only
ALTER TABLE spaces ADD COLUMN status TEXT NOT NULL DEFAULT 'active';  -- active | waiting | someday | done
ALTER TABLE spaces ADD COLUMN area_id TEXT;             -- a project's parent area
ALTER TABLE spaces ADD COLUMN instructions TEXT;        -- per-space guidance for the assistant

ALTER TABLE notes ADD COLUMN due_date TEXT;             -- YYYY-MM-DD, tasks
ALTER TABLE notes ADD COLUMN done_at TEXT;

CREATE TABLE IF NOT EXISTS checklists (
    id          TEXT PRIMARY KEY,
    space_id    TEXT NOT NULL REFERENCES spaces (id),
    name        TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS checklist_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    checklist_id  TEXT NOT NULL REFERENCES checklists (id) ON DELETE CASCADE,
    text          TEXT NOT NULL,
    done          INTEGER NOT NULL DEFAULT 0,
    position      INTEGER NOT NULL DEFAULT 0,
    source        TEXT NOT NULL DEFAULT 'typed',
    created_at    TEXT NOT NULL,
    done_at       TEXT
);
CREATE INDEX IF NOT EXISTS idx_checklist_items_list ON checklist_items (checklist_id, done, position);
