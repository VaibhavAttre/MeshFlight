from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[4]
ENV_PATH = ROOT_DIR / ".env"


def load_repo_env() -> None:
    """
    Load key/value pairs from the repo-root `.env` into `os.environ`.

    Uses normal assignment (not `setdefault`) so values in `.env` override any
    same-named variables already present in the process environment (e.g. a
    stale Windows user `OLLAMA_MODEL`, or an IDE-injected value). That keeps
    edits to `.env` effective after restarting the API.
    """
    if not ENV_PATH.exists():
        return

    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if value.startswith(("\"", "'")) and value.endswith(("\"", "'")) and len(value) >= 2:
            value = value[1:-1]

        os.environ[key] = value
