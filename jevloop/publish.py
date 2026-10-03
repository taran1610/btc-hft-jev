"""Push ~/.jev-loop/latest.json to a public GitHub gist for the Vercel dashboard.

Vercel cannot run the loop. This process watches the local feed file and
PATCHes a public gist; vercel_app.py reads that gist for /latest.json.

Requires `gh` logged in with the `gist` scope (already true if you use gh).

  uv run python -m jevloop publish --forever
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

LOG_DIR = Path(os.environ.get("JEV_LOOP_HOME", str(Path.home() / ".jev-loop")))
LATEST_FILE = LOG_DIR / "latest.json"
DEFAULT_GIST_ID = "0d4f9acb360ca478ff30a817c0b01d72"
META_FILE = LOG_DIR / "publish.json"


def _gist_id() -> str:
    return (
        (os.environ.get("JEV_FEED_GIST_ID") or "").strip()
        or DEFAULT_GIST_ID
    )


def _push(gist_id: str, body: str) -> None:
    payload = json.dumps({"files": {"latest.json": {"content": body}}})
    proc = subprocess.run(
        [
            "gh",
            "api",
            "-X",
            "PATCH",
            f"/gists/{gist_id}",
            "--input",
            "-",
        ],
        input=payload,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "gh api failed").strip()
        raise RuntimeError(err)


def _once(gist_id: str) -> str:
    if not LATEST_FILE.exists():
        raise FileNotFoundError(f"missing feed: {LATEST_FILE}")
    body = LATEST_FILE.read_text(encoding="utf-8")
    json.loads(body)  # refuse to publish a partial write
    _push(gist_id, body)
    META_FILE.write_text(
        json.dumps(
            {
                "gist_id": gist_id,
                "url": f"https://gist.github.com/{gist_id}",
                "raw": f"https://gist.githubusercontent.com/taran1610/{gist_id}/raw/latest.json",
                "bytes": len(body),
                "pushed_at": time.time(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return body


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Publish latest.json to a public gist")
    p.add_argument("--forever", action="store_true", help="keep syncing while the loop runs")
    p.add_argument("--interval", type=float, default=3.0, help="seconds between checks (forever)")
    p.add_argument("--gist-id", default=_gist_id(), help="public gist id to overwrite")
    args = p.parse_args(argv)

    gist_id = args.gist_id.strip()
    if not gist_id:
        print("set JEV_FEED_GIST_ID or pass --gist-id", file=sys.stderr)
        return 1

    if not args.forever:
        _once(gist_id)
        print(f"published {LATEST_FILE} -> https://gist.github.com/{gist_id}")
        return 0

    print(f"publishing {LATEST_FILE} -> gist {gist_id} every {args.interval:.1f}s")
    print(f"raw feed: https://gist.githubusercontent.com/taran1610/{gist_id}/raw/latest.json")
    last_mtime: float | None = None
    last_err = ""
    while True:
        try:
            if not LATEST_FILE.exists():
                time.sleep(args.interval)
                continue
            mtime = LATEST_FILE.stat().st_mtime
            if last_mtime is None or mtime > last_mtime:
                _once(gist_id)
                last_mtime = mtime
                last_err = ""
                print(f"pushed {time.strftime('%H:%M:%S')} ({LATEST_FILE.stat().st_size} bytes)", flush=True)
        except Exception as exc:  # noqa: BLE001 — keep the publisher alive
            msg = str(exc)
            if msg != last_err:
                print(f"publish error: {msg}", file=sys.stderr, flush=True)
                last_err = msg
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
