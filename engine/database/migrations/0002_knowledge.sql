-- 0002_knowledge: the second brain itself.
-- spaces  = projects / areas / resources (PARA-style), each note lives in one.
-- notes   = every piece of knowledge: ideas, notes, tasks, journal entries.
-- links   = edges of the knowledge graph ([[wikilinks]] today; agents later).
-- tags    = #hashtags parsed from note bodies.

CREATE TABLE IF NOT EXISTS spaces (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'project' CHECK (kind IN ('inbox', 'project', 'area', 'resource', 'archive')),
    color       TEXT,
    icon        TEXT,
    position    INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    archived_at TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id          TEXT PRIMARY KEY,
    space_id    TEXT NOT NULL REFERENCES spaces (id),
    title       TEXT NOT NULL,
    body        TEXT NOT NULL DEFAULT '',
    kind        TEXT NOT NULL DEFAULT 'note' CHECK (kind IN ('note', 'idea', 'task', 'journal', 'reference')),
    source      TEXT NOT NULL DEFAULT 'typed' CHECK (source IN ('typed', 'voice', 'import', 'agent', 'seed')),
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'done', 'archived')),
    pinned      INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_notes_space ON notes (space_id);
CREATE INDEX IF NOT EXISTS idx_notes_updated ON notes (updated_at);
CREATE INDEX IF NOT EXISTS idx_notes_title ON notes (title COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS links (
    from_note   TEXT NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    to_note     TEXT NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    kind        TEXT NOT NULL DEFAULT 'wikilink',
    created_by  TEXT NOT NULL DEFAULT 'user',
    created_at  TEXT NOT NULL,
    PRIMARY KEY (from_note, to_note, kind)
);
CREATE INDEX IF NOT EXISTS idx_links_to ON links (to_note);

CREATE TABLE IF NOT EXISTS tags (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS note_tags (
    note_id TEXT NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    tag_id  INTEGER NOT NULL REFERENCES tags (id) ON DELETE CASCADE,
    PRIMARY KEY (note_id, tag_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5 (
    title, body, content = 'notes', content_rowid = 'rowid', tokenize = 'unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS notes_fts_insert AFTER INSERT ON notes BEGIN
    INSERT INTO notes_fts (rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;

CREATE TRIGGER IF NOT EXISTS notes_fts_delete AFTER DELETE ON notes BEGIN
    INSERT INTO notes_fts (notes_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body);
END;

CREATE TRIGGER IF NOT EXISTS notes_fts_update AFTER UPDATE OF title, body ON notes BEGIN
    INSERT INTO notes_fts (notes_fts, rowid, title, body) VALUES ('delete', old.rowid, old.title, old.body);
    INSERT INTO notes_fts (rowid, title, body) VALUES (new.rowid, new.title, new.body);
END;
