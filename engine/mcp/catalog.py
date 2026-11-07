"""The MCP catalogue (Loop MCP-D): a curated starter list, and a search in the official MCP registry
(https://registry.modelcontextprotocol.io, API v0: /v0/servers?search=…&version=latest). Directory websites are
not scraped. Each entry says its family — open (no account), key, sign-in (MCP-E), local (MCP-F) — its publisher
and where it comes from, so the user knows what they connect.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"


def publisher_of(name: str) -> str:
    """« io.github.upstash/context7 » → « github.com/upstash »; « com.example/x » → « example.com »."""
    ns = name.split("/", 1)[0]
    parts = ns.split(".")
    if len(parts) >= 3 and parts[0] == "io" and parts[1] == "github":
        return "github.com/" + ".".join(parts[2:])
    return ".".join(reversed(parts)) if len(parts) > 1 else ns


def normalize(entry: dict[str, Any]) -> dict[str, Any] | None:
    s = entry.get("server") or {}
    meta = (entry.get("_meta") or {}).get("io.modelcontextprotocol.registry/official") or {}
    if meta.get("status") not in (None, "active"):
        return None
    remotes = [r for r in (s.get("remotes") or []) if r.get("type") in ("streamable-http", "sse") and str(r.get("url", "")).startswith("https://")]
    packages = s.get("packages") or []
    out: dict[str, Any] = {"name": s.get("title") or s.get("name", ""), "id": s.get("name", ""), "about": str(s.get("description", ""))[:300],
                           "version": s.get("version", ""), "publisher": publisher_of(s.get("name", "")),
                           "source": (s.get("repository") or {}).get("url", "") or s.get("websiteUrl", ""), "official_registry": True}
    if remotes:
        r = remotes[0]
        headers = r.get("headers") or []
        secret = next((h for h in headers if h.get("isSecret") or str(h.get("name", "")).lower() in ("authorization", "x-api-key")), None)
        required = bool(secret) and secret.get("isRequired", True) and "optional" not in str(secret.get("description", "")).lower()
        out.update(url=r["url"], transport="sse" if r.get("type") == "sse" else "http",
                   family="key" if required else "open", key_header=(secret or {}).get("name", "Authorization"),
                   key_optional=bool(secret) and not required, key_about=str((secret or {}).get("description", ""))[:200])
    elif packages:
        p = packages[0]
        out.update(family="local", package=f"{p.get('registryType', '')}:{p.get('identifier', '')}@{p.get('version', s.get('version', ''))}")
    else:
        return None
    return out


def search(query: str, limit: int = 20, timeout: float = 15.0) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({"search": query.strip()[:80], "version": "latest", "limit": max(1, min(50, limit))})
    req = urllib.request.Request(f"{REGISTRY}?{q}", headers={"Accept": "application/json", "User-Agent": "SecondBrain-MCP/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read(3_000_000))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError(f"the MCP registry cannot be reached ({exc.__class__.__name__})") from exc
    out, seen = [], set()
    for e in data.get("servers", []):
        n = normalize(e)
        if n and n["id"] not in seen:
            seen.add(n["id"])
            out.append(n)
    return out
