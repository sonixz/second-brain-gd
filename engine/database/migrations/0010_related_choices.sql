-- 0010_related_choices: the user's answer to a "related idea" suggestion (Loop 14).
-- A dismissed pair is never suggested again; a kept pair became a real link.

CREATE TABLE IF NOT EXISTS related_choices (
    a           TEXT NOT NULL,      -- the smaller note id of the pair
    b           TEXT NOT NULL,
    choice      TEXT NOT NULL CHECK (choice IN ('kept', 'dismissed')),
    created_at  TEXT NOT NULL,
    PRIMARY KEY (a, b)
);
