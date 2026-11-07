"""Loop 37: a voice memo dropped on the Brain becomes ideas, tasks and notes linked to the memo."""
import os
import struct
import tempfile
import unittest
import wave
from datetime import datetime, timezone
from pathlib import Path

from engine import brain, database
from engine.assistant.llm import FakeChat
from engine.brain.seed import seed_all
from engine.sources import audio, extract


def make_wav(path: Path, seconds: float = 2.0, rate: int = 8000) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(seconds * rate))
    return path


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def make_m4a(path: Path, seconds: float, created: datetime | None, v1: bool = False) -> Path:
    """A minimal MP4: ftyp, then moov/mvhd with a timescale, a duration and a creation time (since 1904)."""
    stamp = int((created - datetime(1904, 1, 1, tzinfo=timezone.utc)).total_seconds()) if created else 0
    scale = 44100
    if v1:
        mvhd = bytes([1, 0, 0, 0]) + struct.pack(">QQIQ", stamp, stamp, scale, int(seconds * scale)) + b"\x00" * 80
    else:
        mvhd = bytes([0, 0, 0, 0]) + struct.pack(">IIII", stamp, stamp, scale, int(seconds * scale)) + b"\x00" * 80
    data = box(b"ftyp", b"M4A \x00\x00\x00\x00M4A mp42isom") + box(b"mdat", b"\x00" * 2000) + box(b"moov", box(b"mvhd", mvhd))
    path.write_bytes(data)
    return path


def make_mp3(path: Path, frames: int | None, kbps_index: int = 9) -> Path:
    """MPEG-1 layer III frames at 44.1 kHz (index 9 = 128 kbit/s); with a Xing header when frames is given."""
    header = bytes([0xFF, 0xFB, (kbps_index << 4) | 0x00, 0x00])
    frame_len = 144 * 128000 // 44100
    first = bytearray(header + b"\x00" * (frame_len - 4))
    if frames is not None:
        first[36:40] = b"Xing"
        first[40:44] = struct.pack(">I", 1)  # flags: frame count present
        first[44:48] = struct.pack(">I", frames)
    body = bytes(first) + (header + b"\x00" * (frame_len - 4)) * 40
    path.write_bytes(b"ID3\x03\x00\x00\x00\x00\x00\x0a" + b"\x00" * 10 + body)
    return path


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "data" / "second_brain.sqlite3"
        self.db.parent.mkdir()
        database.migrate(self.db)
        self.conn = database.connect(self.db)
        seed_all(self.conn)
        self.memos = self.dir / "memos"
        self.memos.mkdir()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_length_and_recording_date_are_read_from_the_file(self):
        when = datetime(2026, 11, 5, 14, 32, tzinfo=timezone.utc)
        for v1 in (False, True):
            m = audio.probe(make_m4a(self.memos / f"Nouvel enregistrement {int(v1)}.m4a", 95.5, when, v1))
            self.assertTrue(m["ok"], m["why"])
            self.assertAlmostEqual(m["seconds"], 95.5, places=1)
            self.assertTrue(m["exact"])
            self.assertEqual((m["recorded_at"], m["date_from"]), ("2026-11-05T14:32:00Z", "recording"))
            self.assertAlmostEqual(m["cost_usd"], 95.5 / 60 * 0.0045 + audio.STRUCTURE_COST, places=4)
        w = audio.probe(make_wav(self.memos / "memo.wav", 2.0))
        self.assertEqual((w["seconds"], w["exact"]), (2.0, True))
        x = audio.probe(make_mp3(self.memos / "xing.mp3", 1000))
        self.assertAlmostEqual(x["seconds"], 1000 * 1152 / 44100, places=1)
        self.assertTrue(x["exact"])
        c = audio.probe(make_mp3(self.memos / "cbr.mp3", None))
        self.assertFalse(c["exact"])
        self.assertGreater(c["seconds"], 0.5)
        # a date in the name (Android, WhatsApp) wins: it is the phone's local time
        a = audio.probe(make_wav(self.memos / "Recording_20261103_081500.wav"))
        self.assertEqual(a["date_from"], "name")
        self.assertEqual(a["recorded_at"],
                         datetime(2026, 11, 3, 8, 15).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        f = make_wav(self.memos / "sans date.wav")
        os.utime(f, (1_700_000_000, 1_700_000_000))
        self.assertEqual(audio.probe(f)["date_from"], "file")

    def test_what_cannot_go_is_said_never_sent(self):
        (self.memos / "note.opus").write_bytes(b"OggS" + b"\x00" * 100)
        big = self.memos / "long.m4a"
        with big.open("wb") as fh:
            fh.truncate(audio.MAX_BYTES + 1)
        (self.memos / "list.txt").write_text("x")
        o, b, t = (audio.probe(self.memos / n) for n in ("note.opus", "long.m4a", "list.txt"))
        self.assertFalse(o["ok"])
        self.assertIn("m4a or mp3", o["why"])
        self.assertIn("25 MB", b["why"])
        self.assertEqual(t["why"], "not an audio recording")
        prev = audio.preview([str(self.memos)], True)
        self.assertEqual([f["name"] for f in prev["files"]], ["long.m4a", "note.opus"], "a folder lists its recordings")
        self.assertEqual(prev["ready"], 0)
        with self.assertRaisesRegex(extract.ExtractError, "m4a or mp3"):
            audio.ingest_audio(self.conn, FakeChat(), str(self.memos / "note.opus"))

    def test_a_memo_becomes_ideas_linked_to_it_and_dated_when_recorded(self):
        when = datetime(2026, 11, 5, 14, 32, tzinfo=timezone.utc)
        m = make_m4a(self.memos / "Nouvel enregistrement.m4a", 62.0, when)
        res = audio.ingest_audio(self.conn, FakeChat(), str(m))
        self.assertFalse(res["duplicate"])
        self.assertEqual([i["kind"] for i in res["items"]], ["task", "idea", "idea"])
        memo = brain.get_note(self.conn, res["memo_id"])
        self.assertTrue(memo["title"].startswith("Mémo vocal du "))
        self.assertIn("Pneus, paella et site du studio", memo["title"])
        self.assertIn("Transcription :", memo["body"])
        self.assertIn("paella aux fruits de mer", memo["body"])
        self.assertEqual(memo["source"], "voice")
        for item in res["items"]:
            note = brain.get_note(self.conn, item["id"])
            self.assertEqual(note["created_at"], "2026-11-05T14:32:00Z", "dated when the memo was recorded")
            linked = self.conn.execute("SELECT 1 FROM links WHERE from_note = ? AND to_note = ?",
                                       (item["id"], res["memo_id"])).fetchone()
            self.assertIsNotNone(linked, f"{note['title']} links to its memo")
        self.assertEqual(self.conn.execute("SELECT created_at FROM notes WHERE id = ?", (res["memo_id"],)).fetchone()[0],
                         "2026-11-05T14:32:00Z")
        paella = brain.get_note(self.conn, res["items"][1]["id"])
        self.assertRegex(paella["body"], r"vers 0:\d\d")
        self.assertIn("#cuisine", paella["body"])
        self.assertIsNotNone(res["items"][1]["at"])
        self.assertLess(res["items"][0]["at"], res["items"][1]["at"], "ideas keep their order in the recording")
        src = self.conn.execute("SELECT * FROM sources WHERE id = ?", (res["id"],)).fetchone()
        self.assertEqual((src["mime"], src["note_id"], src["text_engine"]), ("audio/mp4", res["memo_id"], "gpt-transcribe"))
        self.assertTrue((self.dir / "data" / src["original"]).exists() or src["original"], "the audio is kept")
        self.assertGreater(src["chunks"], 0, "the transcript is searchable")
        again = audio.ingest_audio(self.conn, FakeChat(), str(m))
        self.assertTrue(again["duplicate"], "the same recording twice is added once")
        stages = [r[0] for r in self.conn.execute("SELECT stage FROM system_events WHERE stage IN ('transcribe_audio', 'structure_memo')")]
        self.assertEqual(sorted(set(stages)), ["structure_memo", "transcribe_audio"])

    def test_places_chosen_by_the_model_and_silence(self):
        space = brain.create_space(self.conn, "Cuisine", "area")
        res = audio.ingest_audio(self.conn, _PlaceChat(), str(make_wav(self.memos / "souper.wav", 30)))
        paella = brain.get_note(self.conn, res["items"][1]["id"])
        self.assertEqual(paella["space_id"], space["id"], "an idea goes to the place the model named")
        task = brain.get_note(self.conn, res["items"][0]["id"])
        self.assertEqual(task["space_id"], brain.INBOX_ID, "no place named: the Inbox")
        with self.assertRaisesRegex(extract.ExtractError, "no speech"):
            audio.ingest_audio(self.conn, FakeChat(), str(make_wav(self.memos / "silence.wav", 3)))
        with self.assertRaisesRegex(extract.ExtractError, "OpenAI key"):
            audio.ingest_audio(self.conn, None, str(make_wav(self.memos / "x.wav", 3)))

    def test_a_refused_model_falls_back_and_is_remembered(self):
        from engine.assistant.llm import LLMError
        tried = []

        class Picky(FakeChat):
            provider = "openai"
            allowed = {"gpt-4o-transcribe"}

            def transcribe(self, model, path, languages=None, prompt=""):
                tried.append(model)
                if model not in self.allowed:
                    raise LLMError(f"OpenAI HTTP 403: Project `p` does not have access to model `{model}`")
                return super().transcribe(model, path, languages, prompt)
        res = audio.ingest_audio(self.conn, Picky(), str(make_wav(self.memos / "a.wav", 60)))
        self.assertEqual(tried, ["gpt-transcribe", "gpt-4o-transcribe"])
        self.assertEqual(database.get_setting(self.conn, "audio_transcribe_model", ""), "gpt-4o-transcribe")
        self.assertAlmostEqual(res["transcribe_cost_usd"], 0.006, places=4)
        tried.clear()
        audio.ingest_audio(self.conn, Picky(), str(make_wav(self.memos / "b.wav", 61)))
        self.assertEqual(tried, ["gpt-4o-transcribe"], "the next memo goes straight to the model that worked")
        Picky.allowed = set()
        with self.assertRaisesRegex(extract.ExtractError, "Settings → Project → Limits"):
            audio.ingest_audio(self.conn, Picky(), str(make_wav(self.memos / "c.wav", 62)))

    def test_the_preview_knows_before_anything_is_sent(self):
        class Listing(FakeChat):
            def __init__(self, ids):
                self.ids = ids

            def models(self):
                return self.ids
        self.assertEqual(audio.usable_model(Listing(["gpt-4o-mini-tts", "gpt-4o-transcribe"])), "gpt-4o-transcribe")
        self.assertIsNone(audio.usable_model(Listing(["gpt-4o-mini-tts", "gpt-realtime-whisper"])))
        self.assertEqual(audio.usable_model(FakeChat()), "?", "a client that cannot list models: try in order")
        prev = audio.preview([str(make_wav(self.memos / "m.wav", 5))], True, None)
        self.assertEqual((prev["ready"], prev["model_ok"]), (1, False))

    def test_where_an_idea_starts(self):
        t = "un deux trois quatre cinq six sept huit neuf dix"
        self.assertAlmostEqual(audio.where_in(t, "Six, sept huit", 100.0), 100.0 * t.index("six") / len(t), places=3)
        self.assertIsNone(audio.where_in(t, "rien de tel", 100.0))
        self.assertEqual(audio._clock(3725), "1:02:05")
        self.assertEqual(audio._clock(65), "1:05")


class _PlaceChat(FakeChat):
    def complete(self, model, messages, tools=None, json_mode=False, temperature=0.4, effort=None):
        res = super().complete(model, messages, tools, json_mode, temperature, effort)
        import json
        out = json.loads(res["message"]["content"])
        if out.get("ideas"):
            out["ideas"][1]["place"] = "cuisine"
        res["message"]["content"] = json.dumps(out, ensure_ascii=False)
        return res


if __name__ == "__main__":
    unittest.main()
