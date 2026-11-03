import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engine.paths import Layout
from engine.voice import secrets


class SecretFallbackTests(unittest.TestCase):
    """Without a usable OS credential store, secrets go to a private file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.layout = Layout(Path(self.tmp.name))
        self.no_store = mock.patch.object(secrets, "_keyring", return_value=(None, "none"))
        self.no_store.start()
        self.env = mock.patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("OPENAI_API_KEY", None)

    def tearDown(self):
        self.no_store.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_store_get_delete_file(self):
        self.assertEqual(secrets.info(self.layout, "openai").configured, False)
        self.assertEqual(secrets.store(self.layout, "openai", "  sk-abcdefghijkl1234  "), "file")
        value, source = secrets.get(self.layout, "openai")
        self.assertEqual((value, source), ("sk-abcdefghijkl1234", "file"))
        info = secrets.info(self.layout, "openai")
        self.assertEqual(info.hint, "••••1234")
        self.assertNotIn("abcdefgh", info.hint)
        if os.name == "posix":
            mode = (self.layout.root / "secrets" / "openai.key").stat().st_mode & 0o777
            self.assertEqual(mode, 0o600)
        secrets.delete(self.layout, "openai")
        self.assertEqual(secrets.get(self.layout, "openai"), (None, "none"))

    def test_env_is_last_resort(self):
        os.environ["OPENAI_API_KEY"] = "sk-from-env-000000000"
        self.assertEqual(secrets.get(self.layout, "openai")[1], "env")
        secrets.store(self.layout, "openai", "sk-stored-1111111111")
        self.assertEqual(secrets.get(self.layout, "openai"), ("sk-stored-1111111111", "file"))

    def test_empty_secret_refused(self):
        with self.assertRaises(ValueError):
            secrets.store(self.layout, "openai", "   ")


if __name__ == "__main__":
    unittest.main()
