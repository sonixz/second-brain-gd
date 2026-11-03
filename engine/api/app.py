from __future__ import annotations

import platform
import secrets
import sys
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from fastapi import Depends, FastAPI, HTTPException, Query, Request

from engine import VERSION, database
from engine.events import utc_now
from engine.installer.state import load_state
from engine.monitoring.metrics import ProcessSampler, StorageScanner, system_snapshot
from engine.paths import Layout


def create_app(layout: Layout, token: str, instance_id: str, port: int,
               request_shutdown: Callable[[], None] | None = None,
               on_started: Callable[[], None] | None = None) -> FastAPI:
    if len(token) < 16:
        raise ValueError("API token too short")
    started_monotonic = time.monotonic()
    started_at = utc_now()
    sampler = ProcessSampler()
    storage = StorageScanner(layout)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if on_started is not None:
            on_started()
        yield

    app = FastAPI(title="Second Brain GD engine", version=VERSION, docs_url=None, redoc_url=None,
                  openapi_url=None, lifespan=lifespan)

    def require_token(request: Request) -> None:
        header = request.headers.get("authorization", "")
        scheme, _, given = header.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(given.strip(), token):
            raise HTTPException(status_code=401, detail="missing or invalid local API token",
                                headers={"WWW-Authenticate": "Bearer"})

    def db_check() -> tuple[str, int]:
        try:
            with database.session(layout.database) as conn:
                conn.execute("SELECT 1").fetchone()
                version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0
                database.upsert_service_status(conn, "api", status="running", last_check_at=utc_now())
            return "ok", version
        except Exception:
            return "error", 0

    @app.get("/health")
    def health() -> dict[str, Any]:
        # Public on purpose: tells nothing private, lets the UI detect the service.
        db_status, _ = db_check()
        return {
            "status": "ok" if db_status == "ok" else "degraded",
            "database": db_status,
            "version": VERSION,
            "instance_id": instance_id,
            "uptime_s": round(time.monotonic() - started_monotonic, 1),
            "time": utc_now(),
        }

    @app.get("/system/status", dependencies=[Depends(require_token)])
    def system_status() -> dict[str, Any]:
        db_status, schema_version = db_check()
        with database.session(layout.database) as conn:
            services = database.service_statuses(conn)
            installed_at = database.get_setting(conn, "installed_at")
        state = load_state(layout)
        return {
            "version": VERSION,
            "time": utc_now(),
            "api": {"host": "127.0.0.1", "port": port, "started_at": started_at,
                    "uptime_s": round(time.monotonic() - started_monotonic, 1)},
            "process": sampler.snapshot(),
            "system": system_snapshot(),
            "python": {"version": platform.python_version(), "executable": sys.executable,
                       "prefix": sys.prefix, "base_prefix": sys.base_prefix,
                       "in_venv": sys.prefix != sys.base_prefix, "implementation": sys.implementation.name},
            "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
            "database": {"status": db_status, "path": str(layout.database), "schema_version": schema_version,
                         "installed_at": installed_at},
            "services": services,
            "install": {"installed": state.get("installed", False), "last_success_at": state.get("last_success_at"),
                        "steps": state.get("steps", {})},
        }

    @app.get("/system/storage", dependencies=[Depends(require_token)])
    def system_storage() -> dict[str, Any]:
        return storage.scan()

    @app.get("/system/events", dependencies=[Depends(require_token)])
    def system_events(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
        with database.session(layout.database) as conn:
            return {"events": database.recent_events(conn, limit)}

    @app.post("/system/shutdown", dependencies=[Depends(require_token)])
    def shutdown() -> dict[str, Any]:
        if request_shutdown is None:
            raise HTTPException(status_code=501, detail="shutdown not available")
        request_shutdown()
        return {"status": "stopping"}

    return app
