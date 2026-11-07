-- 0015_item_props: typed items (Loop 37B). A type names the fields an item of that kind carries (a recipe:
-- servings, times, ingredients, steps…); an item of that type keeps its values here, as JSON the engine reads
-- (table view, grocery totals, export). An item without a row is a plain item, as before.

CREATE TABLE IF NOT EXISTS item_types (
    id          TEXT PRIMARY KEY,            -- recipe, book, … (lowercase, no spaces)
    name_en     TEXT NOT NULL,
    name_fr     TEXT NOT NULL,
    fields      TEXT NOT NULL DEFAULT '[]',  -- JSON [{key, en, fr, kind, unit?, choices?}]
    builtin     INTEGER NOT NULL DEFAULT 0,
    created_by  TEXT NOT NULL DEFAULT 'app', -- app, or the agent that defined it
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS item_props (
    note_id     TEXT PRIMARY KEY REFERENCES notes (id) ON DELETE CASCADE,
    type        TEXT NOT NULL,
    props       TEXT NOT NULL DEFAULT '{}',  -- JSON {field key: value}
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_item_props_type ON item_props (type);
