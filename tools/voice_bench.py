"""Voice benchmark against the real OpenAI Realtime API, through the same relay
class the app uses (engine/voice/realtime.py).

    tools/voice-bench.sh [--models gpt-realtime-whisper,gpt-live-transcribe] [clips...]

Clips: 24 kHz mono 16-bit WAV in tests/fixtures/voice (or your own), with the
expected text in expected.json. Audio is streamed in real time (100 ms chunks).
Reports word error rate (WER), time to first words, and time to final text.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from engine.voice.realtime import OpenAIRelay, PRICE_PER_MINUTE_USD  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "voice"


def words(text: str) -> list[str]:
    return re.findall(r"[\w']+", text.lower(), re.UNICODE)


def wer(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r)][len(h)] / max(1, len(r))


async def run_clip(key: str, model: str, path: Path, languages: list[str]) -> dict:
    with wave.open(str(path)) as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1 and w.getsampwidth() == 2, f"{path}: need 24 kHz mono 16-bit"
        pcm = w.readframes(w.getnframes())
    got = {"deltas": "", "final": None, "error": None, "first_delta": None}
    done = asyncio.Event()
    t0 = time.monotonic()

    async def send(msg: dict) -> None:
        if msg["type"] == "delta":
            if got["first_delta"] is None:
                got["first_delta"] = time.monotonic() - t0
            got["deltas"] += msg["text"]
        elif msg["type"] == "final":
            got["final"] = msg["text"]
            done.set()
        elif msg["type"] == "error":
            got["error"] = msg["message"]
            done.set()

    relay = OpenAIRelay(key, model, languages, "low", None)
    await relay.open(send)
    step = 24000 * 2 // 10
    for i in range(0, len(pcm), step):
        await relay.append(pcm[i:i + step])
        await asyncio.sleep(0.1)
        if got["error"]:
            break
    committed = time.monotonic()
    if not got["error"]:
        await relay.commit()
        try:
            await asyncio.wait_for(done.wait(), 30)
        except asyncio.TimeoutError:
            got["error"] = "timeout waiting for the final transcript"
    final_after = time.monotonic() - committed
    await relay.close()
    return {**got, "audio_s": len(pcm) / 48000, "final_after_commit_s": final_after}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="gpt-realtime-whisper")
    ap.add_argument("--languages", default="fr,en")
    ap.add_argument("clips", nargs="*")
    args = ap.parse_args()
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        print("OPENAI_API_KEY is not set. Run through dotenvx: tools/voice-bench.sh", file=sys.stderr)
        return 2
    expected = json.loads((FIXTURES / "expected.json").read_text(encoding="utf-8"))
    clips = [Path(c) for c in args.clips] or sorted(FIXTURES.glob("*.wav"))
    languages = [x for x in args.languages.split(",") if x]
    total_audio = 0.0
    print(f"{'model':<24} {'clip':<16} {'WER':>5} {'first words':>12} {'final':>7}  transcript")
    for model in args.models.split(","):
        for clip in clips:
            res = await run_clip(key, model, clip, languages)
            total_audio += res["audio_s"]
            if res["error"]:
                print(f"{model:<24} {clip.stem:<16} {'-':>5} {'-':>12} {'-':>7}  ERROR: {res['error']}")
                continue
            ref = expected.get(clip.stem, "")
            score = f"{wer(ref, res['final'] or '') * 100:.0f}%" if ref else "n/a"
            first = f"{res['first_delta']:.2f} s" if res["first_delta"] is not None else "none"
            print(f"{model:<24} {clip.stem:<16} {score:>5} {first:>12} {res['final_after_commit_s']:>6.2f}s  {res['final']!r}")
    print(f"\naudio sent: {total_audio:.1f} s ≈ ${total_audio / 60 * PRICE_PER_MINUTE_USD:.4f} at list price")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
