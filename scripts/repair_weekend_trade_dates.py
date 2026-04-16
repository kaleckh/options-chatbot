from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON_BACKEND_DIR = ROOT_DIR / "python-backend"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(PYTHON_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_BACKEND_DIR))

from local_env import load_local_env
from positions_repository import create_positions_repository
from positions_service import review_open_positions


load_local_env(ROOT_DIR)


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not value:
        raise ValueError("Expected datetime value.")
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _load_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    if isinstance(parsed, str):
        try:
            parsed = json.loads(parsed)
        except Exception:
            return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _backup_tracked_positions_snapshot(repository, *, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = ROOT_DIR / "data" / f"tracked_positions.{label}-{stamp}.json"
    backup_path.write_text(
        json.dumps(repository.list_positions(None), indent=2, default=str),
        encoding="utf-8",
    )
    return backup_path


def _is_weekend(dt: datetime) -> bool:
    return dt.weekday() >= 5


def _previous_weekday(dt: datetime) -> datetime:
    adjusted = dt
    while adjusted.weekday() >= 5:
        adjusted -= timedelta(days=1)
    return adjusted


def _append_repair_note(notes: str | None, *, original: datetime, corrected: datetime) -> str:
    suffix = (
        f"Weekend fill corrected to prior market day {corrected.date().isoformat()} "
        f"from imported weekend timestamp {original.date().isoformat()}."
    )
    base = str(notes or "").strip()
    if suffix in base:
        return base
    if not base:
        return suffix
    return f"{base} | {suffix}"


def repair_weekend_trades() -> dict[str, Any]:
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repository, "is_available", False):
        raise RuntimeError(getattr(repository, "error_message", "Tracked positions repository unavailable."))

    weekend_rows = [
        position
        for position in repository.list_positions(None)
        if position.get("filled_at") and _is_weekend(_parse_datetime(position["filled_at"]))
    ]

    updated_ids: list[int] = []
    open_ids_to_refresh: list[int] = []
    repairs: list[dict[str, Any]] = []

    for position in weekend_rows:
        original_filled_at = _parse_datetime(position["filled_at"])
        corrected_filled_at = _previous_weekday(original_filled_at)
        if corrected_filled_at == original_filled_at:
            continue

        source_pick = _load_json(position.get("source_pick_snapshot"))
        repair_meta = dict(source_pick.get("weekend_fill_repair") or {})
        repair_meta.update(
            {
                "original_filled_at": original_filled_at.isoformat(),
                "corrected_filled_at": corrected_filled_at.isoformat(),
                "corrected_on": datetime.now().isoformat(),
                "rule": "prior_weekday_for_weekend_fill",
            }
        )
        source_pick["weekend_fill_repair"] = repair_meta

        repository.update_position(
            int(position["id"]),
            {
                "filled_at": corrected_filled_at,
                "notes": _append_repair_note(
                    position.get("notes"),
                    original=original_filled_at,
                    corrected=corrected_filled_at,
                ),
                "source_pick_snapshot": source_pick,
            },
        )

        updated_ids.append(int(position["id"]))
        repairs.append(
            {
                "id": int(position["id"]),
                "ticker": position.get("ticker"),
                "status": position.get("status"),
                "original_filled_at": original_filled_at.isoformat(),
                "corrected_filled_at": corrected_filled_at.isoformat(),
            }
        )
        if str(position.get("status") or "").lower() == "open":
            open_ids_to_refresh.append(int(position["id"]))

    reviewed_positions: list[dict[str, Any]] = []
    if open_ids_to_refresh:
        reviewed_positions = review_open_positions(repository, position_ids=open_ids_to_refresh)

    remaining_weekend_ids = [
        int(position["id"])
        for position in repository.list_positions(None)
        if position.get("filled_at") and _is_weekend(_parse_datetime(position["filled_at"]))
    ]

    return {
        "updated_ids": updated_ids,
        "open_reviewed_ids": [int(position["id"]) for position in reviewed_positions],
        "remaining_weekend_ids": remaining_weekend_ids,
        "repairs": repairs,
    }


def main() -> None:
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    backup_path = _backup_tracked_positions_snapshot(
        repository,
        label="before-weekend-trade-date-repair",
    )
    result = repair_weekend_trades()
    print(
        json.dumps(
            {
                "backup_path": str(backup_path),
                **result,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
