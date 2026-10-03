"""Read-only Vercel entrypoint for the dashboard.

Vercel cannot run the 24/7 trading loop. This WSGI app only serves the HTML
dashboards and a latest.json feed. Start/Stop is disabled (no control token).
If LATEST_JSON_URL is set, /latest.json is proxied from that URL so friends
can watch a live feed you publish separately.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"
EMPTY_FEED = b'{"ticks": [], "stats": {}, "note": "loop runs locally, not on Vercel"}'
TOKEN_PLACEHOLDER = b"__JEV_CONTROL_TOKEN__"


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


def _latest() -> bytes:
    url = (os.environ.get("LATEST_JSON_URL") or "").strip()
    if not url:
        return EMPTY_FEED
    req = Request(url, headers={"User-Agent": "btc-hft-jev-vercel"})
    with urlopen(req, timeout=4) as resp:
        return resp.read()


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
