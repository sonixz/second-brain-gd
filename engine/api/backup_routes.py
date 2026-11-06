"""Your data (Loop 29): backups, restore, start fresh. The engine room shows them (Loop 30).

  GET  /data/backups                    status: last backup, destination, schedule, the list
  POST /data/backups                    back up now
  PUT  /data/backups/settings           {destination?, every_hours?, enabled?}
  POST /data/backups/{id}/verify        reopen and check one backup (files included)
  POST /data/backups/{id}/restore       {"confirm": "RESTORE"}: a verified safety copy first, then replace
  POST /data/fresh                      {"confirm": "START FRESH"}: a verified safety copy first, then a new Brain

Restoring and starting fresh need the confirmation word: the app asks the user to type it. Nothing here is
reachable by voice except backing up and reading the status.
"""
from __future__ import annotations

from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from engine import backups
from engine.paths import Layout


class SettingsIn(BaseModel):
    destination: str | None = Field(default=None, max_length=1000)
    every_hours: int | None = Field(default=None, ge=1, le=720)
    enabled: bool | None = None


class ConfirmIn(BaseModel):
    confirm: str = Field(default="", max_length=40)


def make_router(layout: Layout, auth: Callable[..., None]) -> APIRouter:
    r = APIRouter(prefix="/data", dependencies=[Depends(auth)])

    def guarded(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except backups.BackupError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=507, detail=f"Could not write the backup: {exc}") from exc

    @r.get("/backups")
    def get_status() -> dict[str, Any]:
        return backups.status(layout)

    @r.post("/backups")
    def post_backup() -> dict[str, Any]:
        return guarded(lambda: backups.backup(layout, "manual"))

    @r.put("/backups/settings")
    def put_settings(body: SettingsIn) -> dict[str, Any]:
        changes = {k: v for k, v in body.model_dump().items() if v is not None}
        return guarded(lambda: backups.save_settings(layout, **changes))

    @r.post("/backups/{snap_id}/verify")
    def post_verify(snap_id: str) -> dict[str, Any]:
        problems = guarded(lambda: backups.verify(layout, snap_id, deep=True))
        return {"id": snap_id, "ok": not problems, "problems": problems}

    @r.post("/backups/{snap_id}/restore")
    def post_restore(snap_id: str, body: ConfirmIn) -> dict[str, Any]:
        if body.confirm != "RESTORE":
            raise HTTPException(status_code=400, detail="Type RESTORE to confirm.")
        return guarded(lambda: backups.restore(layout, snap_id))

    @r.post("/fresh")
    def post_fresh(body: ConfirmIn) -> dict[str, Any]:
        if body.confirm != "START FRESH":
            raise HTTPException(status_code=400, detail="Type START FRESH to confirm.")
        return guarded(lambda: backups.start_fresh(layout))

    return r
