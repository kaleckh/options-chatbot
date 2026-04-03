from __future__ import annotations

import shutil
import uuid
from pathlib import Path


_ROOT = Path(__file__).resolve().parent
_TEMP_ROOT = _ROOT / ".tmp-test-workspaces"


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
