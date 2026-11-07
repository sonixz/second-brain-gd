"""Voice memos (Loop 37): an audio file recorded anywhere, offline, dropped on the Brain at home.

The recording is transcribed by OpenAI (gpt-transcribe, the user's own key), then cut into ideas by the chat model:
each idea becomes an item (an idea, a task or a note) linked to the memo, and the memo keeps the full transcript and
the original audio. Items are dated when the memo was recorded, not when it was dropped.

Nothing here needs a system tool: the length and the recording date are read from the file itself (MP4/M4A boxes,
MP3 frames, WAV headers), so the preview can say what it will cost before anything is sent.
"""
from __future__ import annotations

import hashlib
import json
import re
import struct
import uuid
import wave
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# What OpenAI's transcription accepts (developers.openai.com, speech-to-text guide, read 2026-11-07).
AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".mp4", ".mpeg", ".mpga", ".webm"}
# Recordings it does not take as they are: shown in the preview with a way out, never sent.
OTHER_AUDIO = {".ogg", ".opus", ".oga", ".aac", ".amr", ".3gp", ".flac", ".wma", ".caf", ".aiff", ".aif"}
MIME = {".m4a": "audio/mp4", ".mp4": "audio/mp4", ".mp3": "audio/mpeg", ".mpeg": "audio/mpeg", ".mpga": "audio/mpeg",
        ".wav": "audio/wav", ".webm": "audio/webm"}
MAX_BYTES = 25 * 1024 * 1024
MODEL = "gpt-transcribe"
# Tried in order when a project has no access to one (a 403/404 names the model): the first that answers is kept in
# the settings, so the next memo goes straight to it. gpt-4o-transcribe and the mini stay until 2027-02-26.
MODELS = ["gpt-transcribe", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"]
# Estimated USD per minute (OpenAI pricing page, read 2026-11-07); shown as an estimate, never as a bill.
PRICE_PER_MIN = {"gpt-transcribe": 0.0045, "gpt-4o-transcribe": 0.006, "gpt-4o-mini-transcribe": 0.003, "whisper-1": 0.006}
STRUCTURE_COST = 0.004  # one chat call to cut a memo into ideas, rough upper estimate for a few minutes of speech
MAX_IDEAS = 12
BODY_TRANSCRIPT = 20_000  # characters of transcript kept in the memo's text; the whole is searchable in its document

STRUCTURE_PROMPT = (
    "Tu reçois la transcription d'un mémo vocal : quelqu'un a enregistré ses idées à voix haute. "
    "Découpe-le en idées distinctes pour son second cerveau. Réponds en JSON : "
    '{"title": "titre court du mémo (4 à 8 mots)", "summary": "une ou deux phrases", '
    '"ideas": [{"title": "titre court et précis", "text": "l\'idée en 1 à 4 phrases, avec ses mots à lui, nettoyée '
    'des hésitations", "kind": "idea | task | note", "quote": "les 6 à 10 premiers mots exacts de la transcription '
    'où l\'idée commence", "tags": ["un ou deux thèmes en minuscules"], "place": "un des lieux donnés, ou vide"}]}. '
    "kind = task quand c'est une chose à faire (appeler, acheter, réserver…), idea pour une idée ou un projet, note "
    "pour un fait ou un souvenir. Pas plus de 12 idées ; un mémo d'une seule idée en donne une seule. N'invente rien "
    "qui n'est pas dans la transcription. Garde la langue du mémo.")


class AudioError(ValueError):
    pass


# ------------------------------------------------------------------ reading the file (no tool, no network)
def _mp4_header(path: Path) -> tuple[float | None, datetime | None]:
    """Duration and creation time from the MP4/M4A « mvhd » box (Voice Memos, Android recorders)."""
    def boxes(fh, start: int, end: int):
        pos = start
        while pos + 8 <= end:
            fh.seek(pos)
            head = fh.read(8)
            if len(head) < 8:
                return
            size, kind = struct.unpack(">I4s", head)
            hdr = 8
            if size == 1:
                size = struct.unpack(">Q", fh.read(8))[0]
                hdr = 16
            elif size == 0:
                size = end - pos
            if size < hdr:
                return
            yield kind, pos + hdr, pos + size
            pos += size

    with path.open("rb") as fh:
        end = path.stat().st_size
        for kind, a, b in boxes(fh, 0, end):
            if kind != b"moov":
                continue
            for k2, a2, _b2 in boxes(fh, a, b):
                if k2 != b"mvhd":
                    continue
                fh.seek(a2)
                version = fh.read(4)[0]
                if version == 1:
                    created, _mod, scale, dur = struct.unpack(">QQIQ", fh.read(28))
                else:
                    created, _mod, scale, dur = struct.unpack(">IIII", fh.read(16))
                seconds = dur / scale if scale else None
                when = None
                if created:
                    when = datetime(1904, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=created)
                return seconds, when
    return None, None


_MP3_BITRATES = {  # kbps, MPEG-1 layer III, then MPEG-2/2.5 layer III
    1: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320],
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160]}
_MP3_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def _mp3_seconds(path: Path) -> tuple[float | None, bool]:
    """(seconds, exact): exact from a Xing/Info header, else from the first frame's bitrate (constant bitrate)."""
    with path.open("rb") as fh:
        data = fh.read(256 * 1024)
    size = path.stat().st_size
    start = 0
    if data[:3] == b"ID3" and len(data) >= 10:
        start = 10 + ((data[6] & 0x7F) << 21 | (data[7] & 0x7F) << 14 | (data[8] & 0x7F) << 7 | (data[9] & 0x7F))
    i = start
    while i + 4 <= len(data):
        if data[i] == 0xFF and data[i + 1] & 0xE0 == 0xE0:
            ver = (data[i + 1] >> 3) & 3
            layer = (data[i + 1] >> 1) & 3
            bi = data[i + 2] >> 4
            ri = (data[i + 2] >> 2) & 3
            if ver != 1 and layer == 1 and 0 < bi < 15 and ri < 3:  # layer III
                kbps = _MP3_BITRATES[1 if ver == 3 else 2][bi]
                rate = _MP3_RATES[ver][ri]
                per_frame = 1152 if ver == 3 else 576
                tag = data.find(b"Xing", i, i + 64)
                if tag < 0:
                    tag = data.find(b"Info", i, i + 64)
                if tag >= 0 and tag + 12 <= len(data) and data[tag + 7] & 1:
                    frames = struct.unpack(">I", data[tag + 8:tag + 12])[0]
                    return frames * per_frame / rate, True
                return (size - i) * 8 / (kbps * 1000), False
        i += 1
    return None, False


def probe(path: str | Path) -> dict[str, Any]:
    """What the preview shows for one file: length, recording date, cost estimate, or why it cannot go."""
    p = Path(path)
    out: dict[str, Any] = {"path": str(p), "name": p.name, "ok": False, "why": "", "seconds": None, "exact": False,
                           "bytes": 0, "recorded_at": None, "date_from": "", "cost_usd": 0.0}
    suffix = p.suffix.lower()
    if not p.is_file():
        out["why"] = "this file does not exist"
        return out
    out["bytes"] = size = p.stat().st_size
    if suffix in OTHER_AUDIO:
        out["why"] = (f"{suffix} recordings are not accepted by the transcription: export or share the memo as "
                      "m4a or mp3 (WhatsApp: share the voice message by e-mail gives an .opus; a recorder app can "
                      "save m4a)")
        return out
    if suffix not in AUDIO_SUFFIXES:
        out["why"] = "not an audio recording"
        return out
    if size > MAX_BYTES:
        out["why"] = f"over 25 MB ({size / 1048576:.0f} MB): about 45 minutes of memo at most per file"
        return out
    created = None
    seconds: float | None = None
    try:
        if suffix in (".m4a", ".mp4"):
            seconds, created = _mp4_header(p)
            out["exact"] = seconds is not None
        elif suffix in (".mp3", ".mpeg", ".mpga"):
            seconds, out["exact"] = _mp3_seconds(p)
        elif suffix == ".wav":
            with wave.open(str(p), "rb") as w:
                seconds = w.getnframes() / float(w.getframerate())
                out["exact"] = True
    except (OSError, EOFError, struct.error, wave.Error, IndexError, ValueError):
        seconds = None
    if seconds is None:  # webm or an unusual file: about 32 kbit/s of speech
        seconds = size / 4000.0
        out["exact"] = False
    out["seconds"] = round(seconds, 1)
    when, out["date_from"] = recorded_at(p, created)
    out["recorded_at"] = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out["cost_usd"] = round(seconds / 60.0 * PRICE_PER_MIN[MODEL] + STRUCTURE_COST, 4)
    out["ok"] = True
    return out


def usable_model(client: Any) -> str | None:
    """The first transcription model this key may use, asked for free before anything is sent; « ? » when it cannot
    be known (offline, or a test client): the memo then tries them in order."""
    if client is None or not hasattr(client, "models"):
        return "?" if client is not None else None
    try:
        allowed = set(client.models())
    except Exception:
        return "?"
    return next((m for m in MODELS if m in allowed), None)


def preview(paths: list[str], has_key: bool, model: str | None = "?") -> dict[str, Any]:
    """Probes the dropped files; a dropped folder gives the recordings inside it (subfolders too, 200 at most)."""
    files: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            found = sorted((f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in AUDIO_SUFFIXES | OTHER_AUDIO),
                           key=lambda f: str(f).casefold())
            files.extend(found)
        else:
            files.append(p)
    files = files[:200]
    items = [probe(f) for f in files]
    ok = [i for i in items if i["ok"]]
    return {"files": items, "ready": len(ok), "seconds": round(sum(i["seconds"] or 0 for i in ok), 1),
            "cost_usd": round(sum(i["cost_usd"] for i in ok), 4), "model": model, "has_key": has_key,
            "model_ok": model is not None}


_NAME_DATE = re.compile(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])"
                        r"(?:[ _T.-]*([01]\d|2[0-3])[-_.:h]?([0-5]\d)(?:[-_.:]?([0-5]\d))?)?")


def recorded_at(p: Path, created: datetime | None = None) -> tuple[datetime, str]:
    """When the memo was recorded: a date in its name (Android, WhatsApp), the recorder's own stamp inside the file
    (iPhone Voice Memos), else the file's date."""
    now = datetime.now(timezone.utc)
    m = _NAME_DATE.search(p.stem)
    if m:
        try:
            local = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4] or 12), int(m[5] or 0), int(m[6] or 0))
            when = local.astimezone(timezone.utc)  # a name carries the phone's local time
            if when <= now + timedelta(days=1):
                return when, "name"
        except ValueError:
            pass
    if created is not None and datetime(2005, 1, 1, tzinfo=timezone.utc) < created <= now + timedelta(days=1):
        return created, "recording"
    return datetime.fromtimestamp(p.stat().st_mtime, timezone.utc), "file"


# ------------------------------------------------------------------ from speech to items
def _clock(seconds: float) -> str:
    s = int(round(seconds))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _fold(s: str) -> str:
    return re.sub(r"\W+", " ", s.casefold()).strip()


def where_in(transcript: str, quote: str, seconds: float | None) -> float | None:
    """About when an idea starts: where its first words sit in the transcript, as a share of the memo's length."""
    if not quote or not seconds:
        return None
    hay = _fold(transcript)
    words = _fold(quote).split()
    for n in (len(words), 6, 4):
        if n <= 0 or n > len(words):
            continue
        at = hay.find(" ".join(words[:n]))
        if at >= 0:
            return seconds * at / max(1, len(hay))
    return None


def _date(when: datetime, lang: str) -> str:
    local = when.astimezone()
    if lang == "fr":
        months = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
        return f"{local.day} {months[local.month - 1]} {local.year}, {local.hour}h{local.minute:02d}"
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{months[local.month - 1]} {local.day}, {local.year}, {local.hour}:{local.minute:02d}"


# The memo's own words follow the interface language (the ideas keep the memo's language).
LABELS = {"fr": {"memo": "Mémo vocal du {date} — {title}", "recorded": "Enregistré le {date}", "ideas": "Idées :",
                 "transcript": "Transcription :", "from": "Du [[{memo}]]", "at": " · vers {clock}",
                 "more": "… (suite dans l'audio)"},
          "en": {"memo": "Voice memo, {date} — {title}", "recorded": "Recorded {date}", "ideas": "Ideas:",
                 "transcript": "Transcript:", "from": "From [[{memo}]]", "at": " · at about {clock}",
                 "more": "… (more in the audio)"}}


def _transcribe(conn, client: Any, p: Path, langs: list[str]) -> tuple[dict[str, Any], str]:
    """The memo's text and the model that gave it: the remembered model first, then the others when refused."""
    from engine import database
    from engine.assistant.llm import LLMError

    known = str(database.get_setting(conn, "audio_transcribe_model", "") or "")
    order = ([known] if known in MODELS else []) + [m for m in MODELS if m != known]
    prompt = "Mémo vocal : quelqu'un dit ses idées, ses projets et ses choses à faire."
    last: Exception | None = None
    for model in order:
        try:
            heard = client.transcribe(model, p, langs, prompt)
        except LLMError as exc:
            text = str(exc)
            if ("HTTP 403" in text or "HTTP 404" in text) and ("model" in text.lower()):
                last = exc  # this project cannot use that model: the next one
                continue
            raise
        if model != known:
            database.set_setting(conn, "audio_transcribe_model", model)
        return heard, model
    from engine.sources import extract
    if last is not None:  # every model refused: the project's model list leaves them out
        raise extract.ExtractError(
            "your OpenAI project does not allow a transcription model yet: on platform.openai.com, Settings → "
            "Project → Limits, allow gpt-transcribe (or gpt-4o-transcribe), then drop the memo again")
    raise LLMError("no transcription model is available to this key")


def structure(client: Any, model: str, transcript: str, places: list[str]) -> dict[str, Any]:
    user = json.dumps({"lieux": places[:40], "transcription": transcript[:60_000]}, ensure_ascii=False)
    res = client.complete(model, [{"role": "system", "content": STRUCTURE_PROMPT}, {"role": "user", "content": user}],
                          json_mode=True, temperature=0.2)
    try:
        out = json.loads(res["message"].get("content") or "{}")
    except ValueError:
        out = {}
    return {"out": out if isinstance(out, dict) else {}, "usage": res.get("usage", {}), "model": res.get("model", model)}


def ingest_audio(conn, client: Any | None, path: str, space_id: str | None = None) -> dict[str, Any]:
    """Transcribes a memo, cuts it into ideas and adds them, linked to the memo. Returns the source plus the items."""
    from engine import brain, database
    from engine.assistant.core import _usage_event
    from engine.events import utc_now
    from engine.sources import core, extract, originals, progress

    if client is None or not hasattr(client, "transcribe"):
        raise extract.ExtractError("a voice memo needs your OpenAI key to be transcribed (Settings → Keys)")
    p = Path(path).expanduser()
    info = probe(p)
    if not info["ok"]:
        raise extract.ExtractError(info["why"])
    root = originals.data_root(conn)
    kept = originals.keep_file(root, p)
    dup = conn.execute("SELECT id FROM sources WHERE original = ? AND status = 'ready'", (kept[0],)).fetchone()
    if dup:
        return {**core.get_source(conn, dup["id"]), "duplicate": True, "items": []}
    progress.report("transcribe")
    langs = [str(x) for x in database.get_setting(conn, "voice_languages", []) or [] if str(x)][:4]
    heard, used = _transcribe(conn, client, p, langs)
    transcript = str(heard.get("text", "")).strip()
    seconds = float(heard.get("seconds") or info["seconds"] or 0.0)
    cost = round(seconds / 60.0 * PRICE_PER_MIN.get(used, 0.006), 6) if client.provider == "openai" else 0.0
    database.record_event(conn, {"timestamp": utc_now(), "component": "sources", "stage": "transcribe_audio", "status": "ok",
                                 "message": f"transcribe_audio: {used}, {seconds / 60.0:.1f} min, ≈ ${cost:.4f}",
                                 "details": {"model": used, "seconds": seconds, "estimated_cost_usd": cost}})
    if len(transcript) < 8:
        raise extract.ExtractError("no speech was heard in this recording")
    places = [r["name"] for r in conn.execute("SELECT name FROM spaces WHERE kind != 'archive' AND layer_id IS NULL"
                                              " ORDER BY name")]
    progress.report("structure")
    model = database.get_setting(conn, "assistant_chat_model", "gpt-4o")
    s = structure(client, model, transcript, places)
    _usage_event(conn, "structure_memo", s["model"], s["usage"], client.provider)
    out = s["out"]
    from engine.assistant.core import ui_language
    lang = "fr" if ui_language(conn) == "fr" else "en"
    L = LABELS[lang]
    when = datetime.strptime(info["recorded_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    stamp = info["recorded_at"]
    memo_title = L["memo"].format(date=_date(when, lang), title=str(out.get("title") or p.stem).strip()[:80])
    ideas = [i for i in (out.get("ideas") or []) if isinstance(i, dict) and str(i.get("title", "")).strip()][:MAX_IDEAS]
    by_name = {r["name"].casefold(): r["id"] for r in conn.execute("SELECT id, name FROM spaces")}

    def place_of(idea: dict[str, Any]) -> str | None:
        if space_id:
            return space_id
        return by_name.get(str(idea.get("place") or "").strip().casefold())

    lines = []
    if out.get("summary"):
        lines.append(str(out["summary"]).strip())
    lines.append(L["recorded"].format(date=_date(when, lang)) + f" · {_clock(seconds)} · {p.name}")
    if ideas:
        lines.append(L["ideas"] + "\n" + "\n".join(f"- {str(i['title']).strip()[:120]}" for i in ideas))
    shown = transcript if len(transcript) <= BODY_TRANSCRIPT else transcript[:BODY_TRANSCRIPT] + L["more"]
    lines.append(L["transcript"] + "\n" + shown)
    memo = brain.create_note(conn, memo_title, "\n\n".join(lines), space_id, kind="reference", source="voice")
    items = []
    for idea in ideas:
        kind = str(idea.get("kind", "idea")).strip().lower()
        kind = kind if kind in ("idea", "task", "note") else "idea"
        at = where_in(transcript, str(idea.get("quote", "")), seconds)
        tags = [re.sub(r"[^\w/-]", "", str(t).strip().lower().replace(" ", "-"))[:40] for t in (idea.get("tags") or [])][:2]
        body = [str(idea.get("text") or idea["title"]).strip()]
        body.append(L["from"].format(memo=memo_title) + (L["at"].format(clock=_clock(at)) if at is not None else ""))
        if any(tags):
            body.append(" ".join("#" + t for t in tags if t))
        note = brain.create_note(conn, str(idea["title"]).strip()[:200], "\n\n".join(body), place_of(idea), kind=kind,
                                 source="voice")
        items.append({"id": note["id"], "title": note["title"], "kind": kind, "at": at})
    ids = [memo["id"]] + [i["id"] for i in items]
    conn.executemany("UPDATE notes SET created_at = ? WHERE id = ?", [(stamp, i) for i in ids])
    sid = uuid.uuid4().hex[:16]
    now = utc_now()
    digest = hashlib.sha256(transcript.encode("utf-8")).hexdigest()
    conn.execute("INSERT INTO sources (id, kind, uri, title, mime, bytes, content_hash, status, note_id, chunks, created_at,"
                 " updated_at, original, original_bytes, text_engine) VALUES (?, 'file', ?, ?, ?, ?, ?, 'ready', ?, ?, ?, ?, ?, ?, ?)",
                 (sid, str(p), memo_title[:300], MIME.get(p.suffix.lower(), "audio/mpeg"), info["bytes"], digest, memo["id"],
                  0, now, now, kept[0], kept[1], used))
    pieces = extract.chunk(transcript)
    for i, piece in enumerate(pieces):
        conn.execute("INSERT INTO source_chunks (source_id, idx, text) VALUES (?, ?, ?)", (sid, i, piece))
    conn.execute("UPDATE sources SET chunks = ? WHERE id = ?", (len(pieces), sid))
    core._record(conn, "ok", f"Voice memo added: {memo_title} ({len(items)} ideas, {_clock(seconds)})", source_id=sid,
                 kind="file")
    return {**core.get_source(conn, sid), "duplicate": False, "memo_id": memo["id"], "items": items,
            "seconds": seconds, "recorded_at": stamp, "date_from": info["date_from"],
            "transcribe_cost_usd": cost, "summary": {"title": memo_title}}
