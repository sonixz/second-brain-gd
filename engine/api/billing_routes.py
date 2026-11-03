"""Routes for the real-costs dashboard: the admin key and the live OpenAI figures."""
from __future__ import annotations

import datetime as dt
import os
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from engine import billing, database
from engine.events import utc_now
from engine.paths import Layout
from engine.voice import secrets

PROVIDER = "openai_admin"


class AdminKeyIn(BaseModel):
    api_key: str = Field(min_length=20, max_length=400)


def make_router(layout: Layout, auth: Callable[..., None]) -> APIRouter:
    r = APIRouter(prefix="/billing")
    store = billing.Billing(lambda: secrets.get(layout, PROVIDER)[0])

    def record(status: str, message: str) -> None:
        with database.session(layout.database) as conn:
            database.record_event(conn, {"timestamp": utc_now(), "component": "billing", "stage": "key",
                                         "status": status, "message": message, "details": None})

    def status_payload() -> dict[str, Any]:
        info = secrets.info(layout, PROVIDER)
        fake = os.environ.get("SBGD_BILLING_PROVIDER") == "fake"
        return {"configured": info.configured or fake, "source": "fake" if fake and not info.configured else info.source,
                "hint": info.hint, "backend": info.backend}

    @r.get("/status", dependencies=[Depends(auth)])
    def get_status() -> dict[str, Any]:
        return status_payload()

    @r.get("", dependencies=[Depends(auth)])
    def get_billing(days: int = Query(30, ge=7, le=90), refresh: bool = False) -> dict[str, Any]:
        try:
            return store.get(days, refresh)
        except billing.BillingError as exc:
            return {"configured": True, "error": str(exc), "status": exc.status}

    @r.put("/key", dependencies=[Depends(auth)])
    def put_key(body: AdminKeyIn) -> dict[str, Any]:
        key = body.api_key.strip()
        try:  # one cheap request proves the key can read costs
            start = int(dt.datetime.combine(dt.date.today(), dt.time(), dt.timezone.utc).timestamp())
            billing.http_fetch(key)("/costs", {"start_time": start, "limit": 1})
        except billing.BillingError as exc:
            if exc.status in (401, 403):
                record("error", f"Admin key rejected (HTTP {exc.status})")
                raise HTTPException(status_code=422, detail=str(exc))
        where = secrets.store(layout, PROVIDER, key)
        store.clear()
        record("ok", f"OpenAI admin key saved ({where}); it can read usage only")
        return status_payload()

    @r.delete("/key", dependencies=[Depends(auth)])
    def delete_key() -> dict[str, Any]:
        secrets.delete(layout, PROVIDER)
        store.clear()
        record("ok", "OpenAI admin key removed")
        return status_payload()

    return r
