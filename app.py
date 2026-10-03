"""Default Vercel Python entrypoint location. Delegates to the read-only app."""

from jevloop.vercel_app import app

__all__ = ["app"]
