"""Vercel build step (runs after Python dependencies are installed, before deployment).

1. Apply database migrations to DATABASE_URL.
2. Load demo data on an empty database when SEED_DEMO=true.
3. Build the React frontend into frontend/dist (served by the FastAPI function).
"""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run(cmd: list[str], cwd: Path) -> None:
    print(f"$ {' '.join(cmd)}  (in {cwd.name}/)", flush=True)
    subprocess.run(cmd, cwd=cwd, check=True)


def main() -> None:
    backend, frontend = ROOT / "backend", ROOT / "frontend"
    if os.environ.get("DATABASE_URL"):
        run([sys.executable, "-m", "alembic", "upgrade", "head"], backend)
        if os.environ.get("SEED_DEMO", "").lower() == "true":
            run([sys.executable, "-m", "scripts.seed", "--if-empty"], backend)
    else:
        print("DATABASE_URL is not set: skipping migrations (set it in the Vercel project settings).", flush=True)

    npm = "npm.cmd" if os.name == "nt" else "npm"
    # Serverless instances don't share a pub/sub channel, so a WebSocket would only reach browsers on the
    # same instance. Build the UI to refresh every few seconds instead, and say so in the header.
    os.environ.setdefault("VITE_LIVE_MODE", "poll")
    run([npm, "ci", "--no-audit", "--no-fund"], frontend)
    run([npm, "run", "build"], frontend)


if __name__ == "__main__":
    main()
