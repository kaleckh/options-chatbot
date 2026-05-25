from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("OPTIONS_SCAN_PLAYBOOK", "tracked_winner_observation")
os.environ.setdefault("OPTIONS_SCAN_AUTO_TRACK", "0")

from scripts.log_scan_picks import main


if __name__ == "__main__":
    main()
