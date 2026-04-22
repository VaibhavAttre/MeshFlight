from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn


ROOT_DIR = Path(__file__).resolve().parents[1]

for relative_path in (
    ROOT_DIR / "apps" / "api" / "src",
    ROOT_DIR / "packages" / "schema" / "src",
    ROOT_DIR / "packages" / "runtime_contracts" / "src",
    ROOT_DIR,
):
    path_str = str(relative_path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from meshflight_api.env import load_repo_env  # noqa: E402


load_repo_env()


def main() -> None:
    host = os.getenv("API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port_value = os.getenv("API_PORT", "8000").strip() or "8000"
    try:
        port = int(port_value)
    except ValueError:
        port = 8000

    uvicorn.run(
        "meshflight_api.main:app",
        host=host,
        port=port,
        reload=True,
        app_dir=str(ROOT_DIR / "apps" / "api" / "src"),
    )


if __name__ == "__main__":
    main()
