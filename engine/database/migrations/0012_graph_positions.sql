-- 0012_graph_positions: where the user put things in the graph (edit mode). Node ids as the graph sends them:
-- an item's id, or "space:<id>" for a place (its whole zone). « Tidy » clears them and the layout takes over again.

CREATE TABLE IF NOT EXISTS graph_positions (
    node_id     TEXT PRIMARY KEY,
    x           REAL NOT NULL,
    y           REAL NOT NULL,
    updated_at  TEXT NOT NULL
);
