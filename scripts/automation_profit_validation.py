from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from profit_loop_automation import main


if __name__ == "__main__":
    argv = list(sys.argv[1:])
    if argv and argv[0] in {"profit-validation", "profit-validation-resolve", "profit-validation-defer"}:
        raise SystemExit(main(argv))
    raise SystemExit(main(["profit-validation", *argv]))
