from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path


_ROOT = Path(__file__).resolve().parent


def _default_temp_root() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    repo_name = _ROOT.name
    if codex_home:
        return Path(codex_home).expanduser() / ".tmp" / "workspace-tempdirs" / repo_name
    return Path(tempfile.gettempdir()) / f"{repo_name}-workspace-tempdirs"


_TEMP_ROOT = _default_temp_root()


class WorkspaceTempDir:
    """Repo-local temp directory helper for Windows environments with restricted OS temp ACLs."""

    def __init__(self, *, prefix: str = "tmp") -> None:
        _TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        self.path = (_TEMP_ROOT / f"{prefix}-{uuid.uuid4().hex}").resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self.name = str(self.path)

    def cleanup(self) -> None:
        shutil.rmtree(self.path, ignore_errors=True)

    def __enter__(self) -> str:
        return self.name

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.cleanup()
        return False
