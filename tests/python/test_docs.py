"""Documentation is part of the work (AGENTS.md, owner 2026-11-11): the website's links, pictures and anchors, the
documents' relative links, and every How-to guide present on its page."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class DocumentationTests(unittest.TestCase):
    def test_links_pictures_and_guides_hold_together(self):
        res = subprocess.run([sys.executable, str(ROOT / "tools" / "check_docs.py")], capture_output=True, text=True,
                             encoding="utf-8")
        self.assertEqual(res.returncode, 0, res.stderr[-3000:] + res.stdout[-3000:])
