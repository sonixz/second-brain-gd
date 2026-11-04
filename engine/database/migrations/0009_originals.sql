-- 0009_originals: every source keeps its original (Loop 12). The file itself lives in
-- <data>/originals/<2 hex>/<sha256>.<ext>; the database keeps the relative path.

ALTER TABLE sources ADD COLUMN original TEXT;        -- e.g. originals/3f/3fa4….pdf
ALTER TABLE sources ADD COLUMN original_bytes INTEGER;
ALTER TABLE sources ADD COLUMN pages INTEGER;        -- PDF page count (1 for an image)
