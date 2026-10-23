"""Deployment manifests must stay in sync with the backend's own dependency list."""
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _reqs(lines):
    return sorted(line.strip() for line in lines if line.strip() and not line.strip().startswith("#"))


def test_vercel_pyproject_matches_backend_requirements():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    backend = _reqs((ROOT / "backend" / "requirements.txt").read_text(encoding="utf-8").splitlines())
    assert _reqs(pyproject["project"]["dependencies"]) == backend
    assert pyproject["tool"]["vercel"]["entrypoint"] == "vercel_app:app"


def test_vercel_function_key_matches_entrypoint_file():
    import json
    cfg = json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))
    assert list(cfg["functions"]) == ["vercel_app.py"]
    assert re.search(r"frontend/node_modules", cfg["functions"]["vercel_app.py"]["excludeFiles"])
