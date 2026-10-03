"""Read-only Vercel entrypoint for the dashboard.

Vercel cannot run the 24/7 trading loop. This WSGI app only serves the HTML
dashboards and a latest.json feed. Start/Stop is disabled (no control token).

Live ticks: set LATEST_GIST_ID (preferred) or LATEST_JSON_URL. The local
`jevloop publish --forever` process pushes ~/.jev-loop/latest.json to that gist.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
EMPTY_FEED = b'{"ticks": [], "stats": {}, "note": "loop runs locally, not on Vercel"}'
TOKEN_PLACEHOLDER = b"__JEV_CONTROL_TOKEN__"

_cache_body: bytes | None = None
_cache_at = 0.0
_CACHE_S = 2.0


def _send(start_response, status: str, body: bytes, content_type: str):
    start_response(
        status,
        [
            ("Content-Type", content_type),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def _html(name: str) -> bytes:
    page = (DASHBOARD_DIR / name).read_bytes()
    return page.replace(TOKEN_PLACEHOLDER, b"public-read-only")


def _from_gist(gist_id: str) -> bytes:
    req = Request(
        f"https://api.github.com/gists/{gist_id}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "btc-hft-jev-vercel",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urlopen(req, timeout=4) as resp:
        data = json.loads(resp.read().decode())
    files = data.get("files") or {}
    file = files.get("latest.json") or next(iter(files.values()), None)
    if not file or not file.get("content"):
        raise RuntimeError("gist has no latest.json content")
    return file["content"].encode()


def _from_url(url: str) -> bytes:
    req = Request(
        url,
        headers={
            "User-Agent": "btc-hft-jev-vercel",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )
    with urlopen(req, timeout=4) as resp:
        return resp.read()


def _latest() -> bytes:
    global _cache_body, _cache_at
    now = time.time()
    if _cache_body is not None and (now - _cache_at) < _CACHE_S:
        return _cache_body

    gist_id = (os.environ.get("LATEST_GIST_ID") or "").strip()
    url = (os.environ.get("LATEST_JSON_URL") or "").strip()
    if not gist_id and not url:
        return EMPTY_FEED

    body = _from_gist(gist_id) if gist_id else _from_url(url)
    _cache_body = body
    _cache_at = now
    return body


def app(environ, start_response):
    path = environ.get("PATH_INFO", "/") or "/"
    method = environ.get("REQUEST_METHOD", "GET")

    if method == "POST" and path.rstrip("/") == "/control":
        body = json.dumps(
            {"error": "read-only on Vercel; Start/Stop stays on the local loop"}
        ).encode()
        return _send(start_response, "403 Forbidden", body, "application/json")

    if path in ("/", "/index.html"):
        return _send(start_response, "200 OK", _html("index.html"), "text/html; charset=utf-8")
    if path in ("/wall.html", "/wall"):
        return _send(start_response, "200 OK", _html("wall.html"), "text/html; charset=utf-8")
    if path == "/latest.json":
        try:
            return _send(start_response, "200 OK", _latest(), "application/json")
        except Exception as exc:
            err = json.dumps({"ticks": [], "stats": {}, "error": str(exc)}).encode()
            return _send(start_response, "200 OK", err, "application/json")
    if path == "/control":
        body = json.dumps({"state": "RUNNING", "readonly": True}).encode()
        return _send(start_response, "200 OK", body, "application/json")

    return _send(start_response, "404 Not Found", b'{"error":"not found"}', "application/json")
