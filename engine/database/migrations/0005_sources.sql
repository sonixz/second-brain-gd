-- 0005_sources: files and web pages given to the brain, split into chunks for search.
-- Embeddings are optional (filled when an embeddings model is available).

CREATE TABLE IF NOT EXISTS sources (
    id            TEXT PRIMARY KEY,
    kind          TEXT NOT NULL CHECK (kind IN ('file', 'url')),
    uri           TEXT NOT NULL,
    title         TEXT NOT NULL,
    mime          TEXT,
    bytes         INTEGER,
    content_hash  TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',   -- pending | ready | error
    error         TEXT,
    note_id       TEXT REFERENCES notes (id) ON DELETE SET NULL,   -- the summary note in the graph
    chunks        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources (content_hash);

CREATE TABLE IF NOT EXISTS source_chunks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id  TEXT NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    idx        INTEGER NOT NULL,
    text       TEXT NOT NULL,
    embedding  BLOB,                 -- float32 little-endian, NULL until embedded
    model      TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_source ON source_chunks (source_id, idx);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5 (
    text, content = 'source_chunks', content_rowid = 'id', tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON source_chunks BEGIN
    INSERT INTO chunks_fts (rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_fts_delete AFTER DELETE ON source_chunks BEGIN
    INSERT INTO chunks_fts (chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
