-- 0008_packs: Brain packs (Loop 11). An imported pack is a layer: its places and items carry
-- the layer's id, so the layer can be switched off, merged into your own Brain, or removed.

CREATE TABLE IF NOT EXISTS pack_layers (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    author       TEXT,
    licence      TEXT,
    description  TEXT,
    manifest     TEXT NOT NULL,              -- JSON, as found in the pack
    counts       TEXT,                       -- JSON {items, places, links, vectors_copied, duplicates}
    enabled      INTEGER NOT NULL DEFAULT 1,
    hidden       TEXT,                       -- JSON {note_id: status} while switched off
    imported_at  TEXT NOT NULL
);

ALTER TABLE notes ADD COLUMN layer_id TEXT REFERENCES pack_layers (id);
ALTER TABLE spaces ADD COLUMN layer_id TEXT REFERENCES pack_layers (id);
CREATE INDEX IF NOT EXISTS idx_notes_layer ON notes (layer_id);
