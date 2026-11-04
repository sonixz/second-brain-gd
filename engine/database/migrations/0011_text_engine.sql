-- 0011_text_engine: how a source's text was obtained, shown on its card and used to offer « re-read with AI ».
-- NULL or 'text': the file's own text. 'ocr-windows' / 'ocr-tesseract': read locally from page images.
-- 'ocr-ai': read by the vision model.

ALTER TABLE sources ADD COLUMN text_engine TEXT;
