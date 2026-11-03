"""Helper run with the engine's venv Python (it has websockets/keyring).

  voice_client.py stream <port> <token> <pcm file> [chunk_ms]
  voice_client.py live <port> <token> <seconds of speech>
  voice_client.py keyring-roundtrip
Prints one JSON line with the result.
"""
import asyncio
import json
import sys
import time


async def stream(port: int, token: str, pcm_path: str, chunk_ms: int = 100) -> dict:
    import websockets

    pcm = open(pcm_path, "rb").read() if pcm_path != "-" else b"\x00\x00" * 24000
    out = {"messages": [], "deltas": "", "finals": [], "first_delta_ms": None}
    t0 = time.monotonic()
    async with websockets.connect(f"ws://127.0.0.1:{port}/voice/stream",
                                  additional_headers={"Authorization": f"Bearer {token}"}) as ws:
        ready = json.loads(await asyncio.wait_for(ws.recv(), 15))
        out["messages"].append(ready)
        if ready.get("type") != "ready":
            return out

        async def reader():
            async for raw in ws:
                m = json.loads(raw)
                out["messages"].append(m)
                if m["type"] == "delta":
                    if out["first_delta_ms"] is None:
                        out["first_delta_ms"] = round((time.monotonic() - t0) * 1000)
                    out["deltas"] += m.get("text", "")
                elif m["type"] == "final":
                    out["finals"].append(m.get("text", ""))
                    return
                elif m["type"] == "error":
                    return

        task = asyncio.create_task(reader())
        step = 24000 * 2 * chunk_ms // 1000
        for i in range(0, len(pcm), step):
            await ws.send(pcm[i:i + step])
            await asyncio.sleep(chunk_ms / 1000 * 0.5)  # faster than real time, still chunked
        sent_at = time.monotonic()
        await ws.send(json.dumps({"type": "commit"}))
        try:
            await asyncio.wait_for(task, 30)
        except asyncio.TimeoutError:
            out["timeout"] = True
        out["final_after_commit_ms"] = round((time.monotonic() - sent_at) * 1000)
        await ws.send(json.dumps({"type": "stop"}))
    return out


async def live(port: int, token: str, seconds: int) -> dict:
    """A live conversation: N one-second bursts of audio, then waits for the end (fake upstream)."""
    import websockets

    out = {"types": [], "audio_bytes": 0, "ui_actions": [], "user_text": [], "assistant_text": [], "ended": None,
           "cost": None}
    async with websockets.connect(f"ws://127.0.0.1:{port}/voice/live",
                                  additional_headers={"Authorization": f"Bearer {token}"}) as ws:
        ready = json.loads(await asyncio.wait_for(ws.recv(), 15))
        out["types"].append(ready["type"])
        if ready["type"] != "ready":
            out["error"] = ready.get("message")
            return out

        async def reader():
            async for raw in ws:
                if isinstance(raw, bytes):
                    out["audio_bytes"] += len(raw)
                    continue
                m = json.loads(raw)
                out["types"].append(m["type"])
                if m["type"] == "ui_actions":
                    out["ui_actions"] += m["actions"]
                elif m["type"] in ("user_text", "assistant_text"):
                    out[m["type"]].append(m["text"])
                elif m["type"] == "cost":
                    out["cost"] = m["usd"]
                elif m["type"] == "ended":
                    out["ended"] = m["reason"]
                    return

        task = asyncio.create_task(reader())
        for _ in range(seconds):
            for _ in range(10):
                await ws.send(b"\x10\x00" * 2400)
            await asyncio.sleep(0.3)
        try:
            await asyncio.wait_for(task, 15)
        except asyncio.TimeoutError:
            out["timeout"] = True
    return out


def keyring_roundtrip() -> dict:
    import os

    os.environ["SBGD_KEYRING_SERVICE"] = "SecondBrainGD-test"
    from engine.paths import Layout
    from engine.voice import secrets
    import tempfile
    from pathlib import Path

    layout = Layout(Path(tempfile.mkdtemp()))
    where = secrets.store(layout, "openai", "sk-test-0123456789abcdef")
    got, source = secrets.get(layout, "openai")
    info = secrets.info(layout, "openai")
    secrets.delete(layout, "openai")
    after, _ = secrets.get(layout, "openai")
    return {"where": where, "source": source, "match": got == "sk-test-0123456789abcdef", "hint": info.hint,
            "backend": info.backend, "deleted": after is None or source == "env"}


if __name__ == "__main__":
    sys.path.insert(0, __file__.rsplit("tests", 1)[0])
    if sys.argv[1] == "stream":
        res = asyncio.run(stream(int(sys.argv[2]), sys.argv[3], sys.argv[4], int(sys.argv[5]) if len(sys.argv) > 5 else 100))
    elif sys.argv[1] == "live":
        res = asyncio.run(live(int(sys.argv[2]), sys.argv[3], int(sys.argv[4])))
    else:
        res = keyring_roundtrip()
    print(json.dumps(res))
