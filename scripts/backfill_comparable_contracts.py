from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
PYTHON_BACKEND_DIR = ROOT_DIR / "python-backend"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(PYTHON_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_BACKEND_DIR))

from options_execution import commission_total_usd
from local_env import load_local_env
from positions_repository import create_positions_repository
from positions_service import review_open_positions, resolve_comparable_contract_pick
from suggested_trades_repository import create_suggested_trades_repository


TRACKED_DB_PATH = ROOT_DIR / "data" / "tracked_positions.db"
SUGGESTED_DB_PATH = ROOT_DIR / "chat_history.db"

load_local_env(ROOT_DIR)


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


def _backup_file(path: Path, *, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.stem}.backup-{label}-{stamp}{path.suffix}")
    shutil.copy2(path, backup_path)
    return backup_path


def _backup_tracked_positions_snapshot(repository, *, label: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = ROOT_DIR / "data" / f"tracked_positions.{label}-{stamp}.json"
    backup_path.write_text(
        json.dumps(repository.list_positions(None), indent=2, default=str),
        encoding="utf-8",
    )
    return backup_path


def _strategy_type(scan_pick: dict[str, Any]) -> str:
    explicit = str(scan_pick.get("strategy_type") or "").strip().lower()
    if explicit:
        return explicit
    if scan_pick.get("short_strike") is not None or _snapshot_short_contract_symbol(scan_pick):
        return "vertical_spread"
    return "single_leg"


def _snapshot_contract_symbol(source_pick: dict[str, Any]) -> str:
    return str(
        source_pick.get("contract_symbol")
        or source_pick.get("contractSymbol")
        or source_pick.get("option_contract_symbol")
        or ""
    ).strip()


def _snapshot_short_contract_symbol(source_pick: dict[str, Any]) -> str:
    return str(
        source_pick.get("short_contract_symbol")
        or source_pick.get("shortContractSymbol")
        or source_pick.get("short_option_contract_symbol")
        or ""
    ).strip()


def _has_complete_exact_snapshot_contracts(source_pick: dict[str, Any]) -> bool:
    if source_pick.get("approximation_only"):
        return False
    if not _snapshot_contract_symbol(source_pick):
        return False
    if source_pick.get("short_strike") is not None or _snapshot_short_contract_symbol(source_pick):
        return bool(_snapshot_short_contract_symbol(source_pick))
    return True


def _needs_backfill(row: Any, source_pick: dict[str, Any]) -> bool:
    if str(row["status"] or "").strip().lower() != "open":
        return False
    row_contract_symbol = row.get("contract_symbol") if isinstance(row, dict) else row["contract_symbol"]
    if not str(row_contract_symbol or "").strip():
        return True
    if source_pick.get("approximation_only"):
        return True
    if source_pick.get("short_strike") is not None and not _snapshot_short_contract_symbol(source_pick):
        return True
    return False


def migrate_tracked_positions(repository) -> dict[str, Any]:
    rows = repository.list_positions(None)
    updated_ids: list[int] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        source_pick = _load_json(row.get("source_pick_snapshot"))
        if not _needs_backfill(row, source_pick):
            continue
        if _has_complete_exact_snapshot_contracts(source_pick):
            resolved_pick = dict(source_pick)
            resolved_pick["contract_symbol"] = _snapshot_contract_symbol(source_pick)
            if _snapshot_short_contract_symbol(source_pick):
                resolved_pick["short_contract_symbol"] = _snapshot_short_contract_symbol(source_pick)
            resolved_fill_price = float(row.get("entry_option_price") or 0.0)
            resolution = {"source": "source_pick_snapshot_contract_symbol"}
        else:
            resolved_pick, resolved_fill_price, resolution = resolve_comparable_contract_pick(
                source_pick,
                fill_price=float(row.get("entry_option_price") or 0.0),
                filled_at=row.get("filled_at"),
            )
        if resolution is None or not str(resolved_pick.get("contract_symbol") or "").strip():
            skipped.append({"id": int(row["id"]), "ticker": source_pick.get("ticker"), "reason": "no_comparable_contract"})
            continue
        contracts = max(int(row.get("contracts") or 1), 1)
        strategy_type = _strategy_type(resolved_pick)
        entry_fee = commission_total_usd(contracts=contracts, sides=2 if strategy_type == "vertical_spread" else 1)
        repository.update_position(
            int(row["id"]),
            {
                "contract_symbol": resolved_pick.get("contract_symbol"),
                "strike": float(resolved_pick.get("strike")),
                "expiry": str(resolved_pick.get("expiry")),
                "entry_option_price": float(resolved_fill_price),
                "entry_execution_price": float(resolved_fill_price),
                "entry_execution_basis": str(
                    resolved_pick.get("entry_execution_basis") or "comparable_contract_entry"
                ),
                "entry_fee_total_usd": float(entry_fee),
                "entry_underlying_price": resolved_pick.get("entry_underlying_price"),
                "source_pick_snapshot": resolved_pick,
                "proof_eligible": False,
                "proof_ineligibility_reason": "comparable_exact_contract",
            },
        )
        updated_ids.append(int(row["id"]))
    return {"updated_ids": updated_ids, "skipped": skipped}


def migrate_suggested_trades() -> dict[str, Any]:
    conn = sqlite3.connect(SUGGESTED_DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT id, status, contracts, contract_symbol, strike, expiry, entry_option_price, entry_underlying_price,
               source_pick_snapshot, filled_at
        FROM suggested_trades
        ORDER BY id
        """
    ).fetchall()
    updated_ids: list[int] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        source_pick = _load_json(row["source_pick_snapshot"])
        if str(row["status"] or "").strip().lower() != "open":
            continue
        if not _needs_backfill(dict(row), source_pick):
            continue
        if _has_complete_exact_snapshot_contracts(source_pick):
            resolved_pick = dict(source_pick)
            resolved_pick["contract_symbol"] = _snapshot_contract_symbol(source_pick)
            if _snapshot_short_contract_symbol(source_pick):
                resolved_pick["short_contract_symbol"] = _snapshot_short_contract_symbol(source_pick)
            resolved_fill_price = float(row["entry_option_price"] or 0.0)
            resolution = {"source": "source_pick_snapshot_contract_symbol"}
        else:
            resolved_pick, resolved_fill_price, resolution = resolve_comparable_contract_pick(
                source_pick,
                fill_price=float(row["entry_option_price"] or 0.0),
                filled_at=row["filled_at"],
            )
        if resolution is None or not str(resolved_pick.get("contract_symbol") or "").strip():
            skipped.append({"id": int(row["id"]), "ticker": source_pick.get("ticker"), "reason": "no_comparable_contract"})
            continue
        cur.execute(
            """
            UPDATE suggested_trades
            SET contract_symbol = ?,
                strike = ?,
                expiry = ?,
                entry_option_price = ?,
                entry_underlying_price = ?,
                source_pick_snapshot = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                str(resolved_pick.get("contract_symbol")),
                float(resolved_pick.get("strike")),
                str(resolved_pick.get("expiry")),
                float(resolved_fill_price),
                resolved_pick.get("entry_underlying_price"),
                json.dumps(resolved_pick),
                int(row["id"]),
            ),
        )
        updated_ids.append(int(row["id"]))
    conn.commit()
    conn.close()
    return {"updated_ids": updated_ids, "skipped": skipped}


def refresh_reviews(position_ids: list[int], suggested_ids: list[int]) -> None:
    tracked_repo = create_positions_repository(os.getenv("DATABASE_URL"))
    suggested_repo = create_suggested_trades_repository(str(SUGGESTED_DB_PATH))
    if position_ids:
        review_open_positions(tracked_repo, position_ids=position_ids)
    if suggested_ids:
        review_open_positions(suggested_repo, position_ids=suggested_ids)


def main() -> None:
    tracked_repo = create_positions_repository(os.getenv("DATABASE_URL"))
    tracked_backup = _backup_tracked_positions_snapshot(
        tracked_repo,
        label="backup-before-comparable-contract-backfill",
    )
    suggested_backup = _backup_file(SUGGESTED_DB_PATH, label="before-comparable-contract-backfill")
    tracked_result = migrate_tracked_positions(tracked_repo)
    suggested_result = migrate_suggested_trades()
    refresh_reviews(
        position_ids=tracked_result["updated_ids"],
        suggested_ids=suggested_result["updated_ids"],
    )
    print(
        json.dumps(
            {
                "tracked_backup": str(tracked_backup),
                "suggested_backup": str(suggested_backup),
                "tracked_updated": len(tracked_result["updated_ids"]),
                "tracked_skipped": tracked_result["skipped"],
                "suggested_updated": len(suggested_result["updated_ids"]),
                "suggested_skipped": suggested_result["skipped"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
