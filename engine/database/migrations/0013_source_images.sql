-- 0013_source_images: the images worth keeping from a web page (Loop 25): its main picture and its figures
-- (diagrams, charts, tables shown as pictures), at most a few per page. Logos, icons and ads are never kept.
-- idx 0 is the page's main image, shown on its card. Each image is a kept original (originals/), and what it
-- says (caption, text read in it, the vision model's description) is indexed with the page's passages.

CREATE TABLE IF NOT EXISTS source_images (
    source_id    TEXT NOT NULL REFERENCES sources (id) ON DELETE CASCADE,
    idx          INTEGER NOT NULL,
    original     TEXT NOT NULL,           -- originals/<xx>/<sha256>.<ext>
    mime         TEXT NOT NULL,
    bytes        INTEGER NOT NULL,
    width        INTEGER,
    height       INTEGER,
    url          TEXT,                    -- where it came from on the page
    alt          TEXT,
    caption      TEXT,
    description  TEXT,                    -- the vision model's, only for images with text or data in them
    seen_text    TEXT,                    -- text read in the image on this computer (local OCR)
    created_at   TEXT NOT NULL,
    PRIMARY KEY (source_id, idx)
);
