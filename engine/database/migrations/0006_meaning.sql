-- 0006_meaning: one embedding per note, and the "related ideas" between notes.
-- Vectors are float32 little-endian, normalised to length 1 (cosine = dot product).

CREATE TABLE IF NOT EXISTS note_embeddings (
    note_id       TEXT PRIMARY KEY REFERENCES notes (id) ON DELETE CASCADE,
    model         TEXT NOT NULL,
    content_hash  TEXT NOT NULL,     -- hash of title + body when embedded; a change re-embeds
    embedding     BLOB NOT NULL,
    updated_at    TEXT NOT NULL
);

-- Each note's own picks: its closest note, plus any strongly similar ones.
-- A pair is "related" when either note picked the other.
CREATE TABLE IF NOT EXISTS note_related (
    owner  TEXT NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    other  TEXT NOT NULL REFERENCES notes (id) ON DELETE CASCADE,
    score  REAL NOT NULL,
    PRIMARY KEY (owner, other)
);
CREATE INDEX IF NOT EXISTS idx_note_related_other ON note_related (other);
