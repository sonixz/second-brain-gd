from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any

import psutil

from engine.paths import Layout


class ProcessSampler:
    """CPU percent needs two samples; the first call only primes the counter."""

    def __init__(self) -> None:
        self.proc = psutil.Process(os.getpid())
        self._lock = threading.Lock()
        self._last_sample = time.monotonic()
        self.proc.cpu_percent(None)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            cpu = None
            if now - self._last_sample >= 0.2:
                try:
                    cpu = round(self.proc.cpu_percent(None), 1)
                    self._last_sample = now
                except psutil.Error:
                    cpu = None
        out: dict[str, Any] = {"pid": self.proc.pid, "cpu_percent": cpu, "rss_bytes": None, "threads": None}
        try:
            out["rss_bytes"] = self.proc.memory_info().rss
            out["threads"] = self.proc.num_threads()
        except psutil.Error:
            pass
        return out


def system_snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {"cpu_count": psutil.cpu_count(), "memory_total_bytes": None,
                           "memory_available_bytes": None}
    try:
        vm = psutil.virtual_memory()
        out["memory_total_bytes"] = vm.total
        out["memory_available_bytes"] = vm.available
    except (psutil.Error, OSError):
        pass
    return out


def dir_size(path: Path) -> tuple[int, int]:
    total, files = 0, 0
    for root, _dirs, names in os.walk(path):
        for n in names:
            try:
                total += os.lstat(os.path.join(root, n)).st_size
                files += 1
            except OSError:
                pass
    return total, files


class StorageScanner:
    """Walking the venv costs ~100 ms on Windows; cache for a short time."""

    def __init__(self, layout: Layout, ttl_s: float = 15.0) -> None:
        self.layout = layout
        self.ttl_s = ttl_s
        self._cache: tuple[float, dict[str, Any]] | None = None
        self._lock = threading.Lock()

    def scan(self) -> dict[str, Any]:
        with self._lock:
            if self._cache and time.monotonic() - self._cache[0] < self.ttl_s:
                return self._cache[1]
            entries = {}
            for name, path in (("database", self.layout.database), ("notes", self.layout.notes),
                               ("logs", self.layout.logs), ("venv", self.layout.venv),
                               ("runtime", self.layout.runtime)):
                if path.is_file():
                    size, files = path.stat().st_size, 1
                    for suffix in ("-wal", "-shm"):
                        extra = path.with_name(path.name + suffix)
                        if extra.exists():
                            size += extra.stat().st_size
                elif path.is_dir():
                    size, files = dir_size(path)
                else:
                    size, files = None, 0
                entries[name] = {"path": str(path), "bytes": size, "files": files}
            disk: dict[str, Any] = {"total_bytes": None, "free_bytes": None}
            try:
                du = shutil.disk_usage(self.layout.root)
                disk = {"total_bytes": du.total, "free_bytes": du.free}
            except OSError:
                pass
            result = {"data_dir": str(self.layout.root), "entries": entries, "disk": disk,
                      "scanned_at": time.time(), "platform": sys.platform}
            self._cache = (time.monotonic(), result)
            return result
