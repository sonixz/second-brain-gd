"""Progress of a long document read (OCR pages, AI pages, summary), polled by the interface.

The request that reads a document sets a job id; every stage reports into it, and
GET /sources/progress/{job} returns the latest state. Jobs live in memory only and are forgotten
a few minutes after they finish.
"""
from __future__ import annotations

import contextvars
import threading
import time
from typing import Any

_current: contextvars.ContextVar[str | None] = contextvars.ContextVar("sbgd_progress_job", default=None)
_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
KEEP_S = 300


def start(job: str | None) -> contextvars.Token | None:
    if not job:
        return None
    with _lock:
        _prune()
        _jobs[job] = {"job": job, "stage": "reading", "done": 0, "total": 0, "finished": False, "at": time.time()}
    return _current.set(job)


def report(stage: str, done: int = 0, total: int = 0) -> None:
    """stage: reading | render | ocr | ai | summary | indexing."""
    job = _current.get()
    if not job:
        return
    with _lock:
        if job in _jobs:
            _jobs[job].update(stage=stage, done=done, total=total, at=time.time())


def finish(token: contextvars.Token | None) -> None:
    job = _current.get()
    if job:
        with _lock:
            if job in _jobs:
                _jobs[job].update(finished=True, at=time.time())
    if token is not None:
        _current.reset(token)


def get(job: str) -> dict[str, Any] | None:
    with _lock:
        j = _jobs.get(job)
        return dict(j) if j else None


def _prune() -> None:
    now = time.time()
    for k in [k for k, v in _jobs.items() if v["finished"] and now - v["at"] > KEEP_S]:
        del _jobs[k]
