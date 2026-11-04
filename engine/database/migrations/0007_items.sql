-- 0007_items: what the archivist understood about each item (Loop 9, "one intake").
-- Every input (typed, spoken, URL, file) is a note in the graph; this is its structured record.

CREATE TABLE IF NOT EXISTS item_meta (
    note_id      TEXT PRIMARY KEY REFERENCES notes (id) ON DELETE CASCADE,
    item_type    TEXT NOT NULL DEFAULT 'note',   -- note, idea, article, document, reference, quote, list, journal
    origin       TEXT NOT NULL DEFAULT 'typed',  -- typed, voice, url, file, import, seed
    origin_uri   TEXT,
    language     TEXT,
    summary      TEXT,
    key_points   TEXT,                           -- JSON list
    entities     TEXT,                           -- JSON {people, organizations, concepts, places, dates}
    themes       TEXT,                           -- JSON list
    confidence   REAL,
    filed        INTEGER NOT NULL DEFAULT 0,     -- 1 once placed by the archivist (or the user)
    question     TEXT,                           -- what the archivist needs to know, when unsure
    receipt      TEXT,                           -- one factual sentence: what it is and where it went
    proposal     TEXT,                           -- JSON, the archivist's raw proposal
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_item_meta_created ON item_meta (created_at);
