"""Vercel entrypoint: the same FastAPI app, configured for a serverless host.

Vercel runs the app as Fluid-compute functions that can be frozen between requests, so:
  * auctions are closed on incoming traffic instead of by a background loop (CLOSE_ON_REQUEST);
  * each instance's in-memory Bloom filter refreshes itself every minute (BLOOM_MAX_AGE_SECONDS);
  * the built React app (frontend/dist) is served by the same function, so there is one URL.
Explicit environment variables in the Vercel project still take precedence over these defaults.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))   # the backend imports itself as `app.*`

os.environ.setdefault("RUN_CLOSER", "false")
os.environ.setdefault("CLOSE_ON_REQUEST", "true")
os.environ.setdefault("BLOOM_MAX_AGE_SECONDS", "60")
os.environ.setdefault("FRONTEND_DIST", str(ROOT / "frontend" / "dist"))

from app.main import app  # noqa: E402,F401  (Vercel looks for a FastAPI instance named `app`)
