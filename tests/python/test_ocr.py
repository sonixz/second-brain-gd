"""The real local OCR engines, where they exist (Windows built-in OCR on Windows, Tesseract when installed)."""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.sources import ocr

SAMPLE = Path(__file__).resolve().parent.parent / "fixtures" / "docs" / "sample.pdf"
try:
    import pypdfium2  # noqa: F401
    HAS_RENDER = True
except ImportError:
    HAS_RENDER = False


class RealOcrTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32" and HAS_RENDER, "Windows OCR runs on Windows only")
    def test_windows_ocr_reads_a_rendered_page(self):
        with mock.patch.dict(os.environ, {"SBGD_OCR": ""}):
            self.assertEqual(ocr.engine_name(), "windows")
            text = ocr.read_pdf(SAMPLE, 2)
        self.assertIn("compost", text.lower())
        self.assertIn("deux semaines", text.lower())

    @unittest.skipUnless(sys.platform != "win32" and shutil.which("tesseract") and HAS_RENDER, "Tesseract not installed")
    def test_tesseract_reads_a_rendered_page(self):
        with mock.patch.dict(os.environ, {"SBGD_OCR": ""}):
            self.assertEqual(ocr.engine_name(), "tesseract")
            text = ocr.read_pdf(SAMPLE, 2)
        self.assertIn("compost", text.lower())

    def test_off_and_fake_modes(self):
        with mock.patch.dict(os.environ, {"SBGD_OCR": "off"}):
            self.assertIsNone(ocr.engine_name())
            with self.assertRaises(ocr.OcrError):
                ocr.read_images([Path("x.png")])
        with mock.patch.dict(os.environ, {"SBGD_OCR": "fake"}):
            self.assertEqual(len(ocr.read_images([Path("a.png"), Path("b.png")])), 2)


if __name__ == "__main__":
    unittest.main()
