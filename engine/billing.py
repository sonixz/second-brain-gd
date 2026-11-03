"""What OpenAI actually bills, read live from OpenAI. Nothing is stored locally.

OpenAI already keeps every request, token and dollar. The app asks for them when the
dashboard opens: the Costs API (billed amounts, one bucket per UTC day, by line item)
and the Usage API (tokens and requests per model). Both need an **admin key** with
"Usage API: Read" (a project key gets HTTP 403 whatever its permissions). That key is
read-only for usage, cannot call models, and is kept in the OS keyring like the
regular key (provider "openai_admin", or OPENAI_ADMIN_KEY for developers).

The only state is an in-memory cache of a few minutes, so reopening the dashboard does
not hammer the API. Costs are daily: today's amount fills in as OpenAI updates it.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

ADMIN_API = "https://api.openai.com/v1/organization"
CACHE_SECONDS = 300
MAX_GROUPS = 5  # line items shown separately in the chart; the rest folds into "Other"
USAGE_KINDS = ("completions", "embeddings", "audio_speeches", "audio_transcriptions")

Fetch = Callable[[str, dict[str, Any]], dict[str, Any]]


class BillingError(RuntimeError):
    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.status = status


MESSAGES = {
    401: "OpenAI rejected the admin key (401). Check that it was copied entirely.",
    403: "This key cannot read usage (403). It must be an admin key with \"Usage API: Read\".",
    429: "OpenAI is rate limiting usage requests (429). Try again in a minute.",
}


def http_fetch(key: str) -> Fetch:
    def fetch(path: str, params: dict[str, Any]) -> dict[str, Any]:
        query = urllib.parse.urlencode(params, doseq=True)
        req = urllib.request.Request(f"{ADMIN_API}{path}?{query}", headers={"Authorization": f"Bearer {key}"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise BillingError(MESSAGES.get(exc.code, f"OpenAI answered HTTP {exc.code}."), exc.code) from None
        except OSError as exc:
            raise BillingError(f"Cannot reach OpenAI: {exc.__class__.__name__}.") from None
    return fetch


def _pages(fetch: Fetch, path: str, params: dict[str, Any], max_pages: int = 20) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    params = dict(params)
    for _ in range(max_pages):
        page = fetch(path, params)
        buckets.extend(page.get("data") or [])
        if not page.get("has_more") or not page.get("next_page"):
            break
        params["page"] = page["next_page"]
    return buckets


def _day(ts: int) -> str:
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc).date().isoformat()


def _line_group(item: str | None) -> str:
    """'gpt-4o-2024-08-06, input' and '…, output' are one product on the chart."""
    name = (item or "Other").split(",")[0].strip()
    return name or "Other"


def fetch_billing(fetch: Fetch, days: int = 30, now: dt.datetime | None = None) -> dict[str, Any]:
    now = now or dt.datetime.now(dt.timezone.utc)
    today = now.date()
    first = today - dt.timedelta(days=days - 1)
    month_first = today.replace(day=1)
    start = min(first, month_first)
    start_ts = int(dt.datetime.combine(start, dt.time(), dt.timezone.utc).timestamp())
    n_days = (today - start).days + 1

    cost_buckets = _pages(fetch, "/costs", {"start_time": start_ts, "bucket_width": "1d", "limit": min(180, n_days),
                                           "group_by": ["line_item"]})
    per_day: dict[str, dict[str, float]] = {}
    currency = "usd"
    for b in cost_buckets:
        day = _day(b.get("start_time", 0))
        for r in b.get("results") or []:
            amount = r.get("amount") or {}
            value = float(amount.get("value") or 0)
            currency = amount.get("currency") or currency
            name = r.get("line_item") or "Other"
            per_day.setdefault(day, {})
            per_day[day][name] = per_day[day].get(name, 0.0) + value

    # Chart groups: products ranked by spend over the period, top ones kept, the rest "Other".
    by_product: dict[str, float] = {}
    for day, items in per_day.items():
        if day >= first.isoformat():
            for name, v in items.items():
                g = _line_group(name)
                by_product[g] = by_product.get(g, 0.0) + v
    ranked = [g for g, _ in sorted(by_product.items(), key=lambda kv: -kv[1]) if g != "Other"]
    kept = ranked[:MAX_GROUPS]
    groups = kept + (["Other"] if len(ranked) > MAX_GROUPS or "Other" in by_product else [])

    day_list = []
    for i in range(days):
        day = (first + dt.timedelta(days=i)).isoformat()
        split = {g: 0.0 for g in groups}
        for name, v in per_day.get(day, {}).items():
            g = _line_group(name)
            split[g if g in kept else "Other"] = split.get(g if g in kept else "Other", 0.0) + v
        day_list.append({"day": day, "cost": round(sum(split.values()), 6),
                         "by_group": {g: round(v, 6) for g, v in split.items()}})

    def total_since(since: dt.date) -> float:
        return round(sum(v for d, items in per_day.items() if d >= since.isoformat() for v in items.values()), 6)

    models: dict[str, dict[str, Any]] = {}
    for kind in USAGE_KINDS:
        try:
            buckets = _pages(fetch, f"/usage/{kind}", {"start_time": int(dt.datetime.combine(
                month_first, dt.time(), dt.timezone.utc).timestamp()), "bucket_width": "1d",
                "limit": min(31, (today - month_first).days + 1), "group_by": ["model"]})
        except BillingError as exc:
            if exc.status in (401, 403):
                raise
            continue
        for b in buckets:
            for r in b.get("results") or []:
                m = models.setdefault(r.get("model") or "?", {"model": r.get("model") or "?", "kind": kind,
                                                               "requests": 0, "input_tokens": 0,
                                                               "cached_tokens": 0, "output_tokens": 0,
                                                               "audio_in_tokens": 0, "audio_out_tokens": 0,
                                                               "characters": 0, "seconds": 0})
                m["requests"] += int(r.get("num_model_requests") or 0)
                m["input_tokens"] += int(r.get("input_tokens") or 0)
                m["cached_tokens"] += int(r.get("input_cached_tokens") or 0)
                m["output_tokens"] += int(r.get("output_tokens") or 0)
                m["audio_in_tokens"] += int(r.get("input_audio_tokens") or 0)
                m["audio_out_tokens"] += int(r.get("output_audio_tokens") or 0)
                m["characters"] += int(r.get("characters") or 0)
                m["seconds"] += int(r.get("seconds") or 0)

    month_items = {}
    for d, items in per_day.items():
        if d >= month_first.isoformat():
            for name, v in items.items():
                month_items[name] = month_items.get(name, 0.0) + v
    return {
        "currency": currency,
        "days": day_list,
        "groups": groups,
        "today": total_since(today),
        "month": total_since(month_first),
        "period": total_since(first),
        "month_start": month_first.isoformat(),
        "line_items": [{"name": k, "cost": round(v, 6)} for k, v in sorted(month_items.items(), key=lambda kv: -kv[1])],
        "models": sorted(models.values(), key=lambda m: -(m["input_tokens"] + m["output_tokens"] + m["requests"])),
        "tokens": {k: sum(m[k] for m in models.values()) for k in
                   ("requests", "input_tokens", "cached_tokens", "output_tokens", "audio_in_tokens", "audio_out_tokens")},
        "fetched_at": now.replace(microsecond=0).isoformat(),
        "source": "OpenAI Costs and Usage APIs (billed amounts; daily, UTC)",
    }


def fake_fetch() -> Fetch:
    """Deterministic pages in OpenAI's shapes, for tests and screenshots (SBGD_BILLING_PROVIDER=fake)."""
    def fetch(path: str, params: dict[str, Any]) -> dict[str, Any]:
        start = int(params["start_time"])
        n = int(params.get("limit", 7))
        data = []
        for i in range(n):
            t0 = start + i * 86400
            if path == "/costs":
                results = [
                    {"object": "organization.costs.result", "amount": {"value": 0.05 + 0.01 * (i % 5), "currency": "usd"},
                     "line_item": "gpt-4o-2024-08-06, input"},
                    {"object": "organization.costs.result", "amount": {"value": 0.03 + 0.004 * (i % 3), "currency": "usd"},
                     "line_item": "gpt-4o-2024-08-06, output"},
                    {"object": "organization.costs.result", "amount": {"value": 0.02 * (i % 4), "currency": "usd"},
                     "line_item": "gpt-6-astra, output"},
                    {"object": "organization.costs.result", "amount": {"value": 0.0004, "currency": "usd"},
                     "line_item": "text-embedding-3-small"},
                    {"object": "organization.costs.result", "amount": {"value": 0.01 * (i % 2), "currency": "usd"},
                     "line_item": "gpt-realtime-whisper, audio"},
                ]
            elif path == "/usage/completions":
                results = [{"object": "organization.usage.completions.result", "model": "gpt-4o-2024-08-06",
                            "input_tokens": 12000, "input_cached_tokens": 3000, "output_tokens": 900,
                            "num_model_requests": 14},
                           {"object": "organization.usage.completions.result", "model": "gpt-6-astra",
                            "input_tokens": 4000, "output_tokens": 1500, "num_model_requests": 1}]
            elif path == "/usage/embeddings":
                results = [{"object": "organization.usage.embeddings.result", "model": "text-embedding-3-small",
                            "input_tokens": 2500, "num_model_requests": 6}]
            elif path == "/usage/audio_transcriptions":
                results = [{"object": "organization.usage.audio_transcriptions.result", "model": "gpt-realtime-whisper",
                            "seconds": 40, "num_model_requests": 3}]
            else:
                results = [{"object": "organization.usage.audio_speeches.result", "model": "gpt-4o-mini-tts",
                            "characters": 1800, "num_model_requests": 5}]
            data.append({"object": "bucket", "start_time": t0, "end_time": t0 + 86400, "results": results})
        return {"object": "page", "data": data, "has_more": False, "next_page": None}
    return fetch


class Billing:
    """Cached front door used by the routes."""

    def __init__(self, get_key: Callable[[], str | None]):
        self.get_key = get_key
        self._lock = threading.Lock()
        self._cache: dict[int, tuple[float, dict[str, Any]]] = {}

    def fetcher(self) -> Fetch | None:
        if os.environ.get("SBGD_BILLING_PROVIDER") == "fake":
            return fake_fetch()
        key = self.get_key()
        return http_fetch(key) if key else None

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def get(self, days: int = 30, refresh: bool = False) -> dict[str, Any]:
        with self._lock:
            hit = self._cache.get(days)
            if hit and not refresh and time.monotonic() - hit[0] < CACHE_SECONDS:
                return {**hit[1], "cached": True}
        fetch = self.fetcher()
        if fetch is None:
            return {"configured": False, "message": "Add an OpenAI admin key with \"Usage API: Read\" to see your real costs."}
        data = {"configured": True, **fetch_billing(fetch, days), "cached": False}
        with self._lock:
            self._cache[days] = (time.monotonic(), data)
        return data
