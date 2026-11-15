"""The How-to page (tools/howto/build_page.py): a step done outside the app carries the lines to paste, shown as
they are. The ChatGPT guide depends on it: its PowerShell lines hold quotes and backslashes."""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load():
    spec = importlib.util.spec_from_file_location("build_page", ROOT / "tools" / "howto" / "build_page.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


class HowtoPage(unittest.TestCase):
    def test_a_step_with_lines_to_paste_shows_them_as_they_are(self) -> None:
        bp = load()
        guide = {"id": "x", "title": "T", "kind": "scripted", "minutes": 1, "goal": "g", "needs": [], "trouble": [],
                 "docs": [], "group": "G",
                 "steps": [("Do this", "See that"),
                           ("Paste", "It runs", "$env:A = ('\"C:\\x\" <y>').Replace('\\', '/')\n.\\run.exe")]}
        page = bp.section(guide)
        self.assertEqual(page.count('<pre class="guide-paste">'), 1)  # the step without lines has no block
        self.assertIn("&quot;C:\\x&quot; &lt;y&gt;", page)  # escaped for the page, backslashes kept
        self.assertIn(".Replace(&#x27;\\&#x27;, &#x27;/&#x27;)\n.\\run.exe", page)  # two lines stay two lines
        self.assertEqual(page.count("<figure"), 2)  # every step keeps its picture

    def test_the_chatgpt_guide_keeps_the_fix_for_windows_paths(self) -> None:
        """tunnel-client splits its command the POSIX way: without .Replace('\\', '/') the app's line loses its
        backslashes (« C:Users… was not found », seen on 2026-11-14)."""
        bp = load()
        paste = [s[2] for s in bp.guides.by_id("chatgpt")["steps"] if len(s) > 2]
        self.assertEqual(len(paste), 1)
        self.assertIn("$env:MCP_COMMAND = ('", paste[0])
        self.assertIn("').Replace('\\', '/')", paste[0])
        self.assertNotIn("sk-", paste[0])  # the key is typed at a prompt, never written in the lines


if __name__ == "__main__":
    unittest.main()
