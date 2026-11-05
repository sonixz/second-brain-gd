"""The app's two languages (Loop 26): every interface text written in I18n.t("...") has its French, with the same
placeholders, and no French entry is left behind when a text changes."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class TranslationTests(unittest.TestCase):
    def test_every_interface_text_has_its_french(self):
        res = subprocess.run([sys.executable, str(ROOT / "tools" / "i18n.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr[-3000:] + res.stdout)
