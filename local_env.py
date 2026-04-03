from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv as _load_dotenv
except Exception:  # pragma: no cover - optional local convenience
    _load_dotenv = None


def load_local_env(root_dir: str | Path) -> list[str]:
    loaded: list[str] = []
    base = Path(root_dir)
    for name in (".env", ".env.local"):
        path = base / name
        if not path.exists():
            continue
        if _load_dotenv is not None:
            _load_dotenv(path, override=False)
        else:
            for raw_line in path.read_text(encoding="utf8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key or key in os.environ:
                    continue
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                    value = value[1:-1]
                os.environ[key] = value
        loaded.append(str(path))
    return loaded
