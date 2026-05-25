from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "promotion-checklists"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _fingerprint_payload(checklist: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "canary_promotion_checklist",
        "source_run": str(checklist.get("source_run") or ""),
        "playbook": str(checklist.get("playbook") or ""),
        "requirements": [
            {
                "id": item.get("id"),
                "target": item.get("target"),
            }
            for item in list(checklist.get("requirements") or [])
        ],
    }


def build_promotion_checklist_fingerprint(checklist: dict[str, Any]) -> str:
    payload = _fingerprint_payload(checklist)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def find_duplicate_promotion_checklist(output_dir: Path, fingerprint: str) -> Path | None:
    for checklist_path in sorted(Path(output_dir).glob("promotion_checklist_*.json")):
        try:
            checklist = _read_json(checklist_path)
        except (OSError, json.JSONDecodeError):
            continue
        if checklist.get("checklist_fingerprint") == fingerprint:
            return checklist_path
    return None


def _metric(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source.get(key)
    return None


def _status(value: float, threshold: float) -> str:
    return "pass" if value >= threshold else "needs_more"


def build_canary_promotion_checklist(
    run_path: Path,
    *,
    min_exact_trades: int = 40,
    min_closed_forward_trades: int = 20,
    min_profit_factor: float = 1.2,
) -> dict[str, Any]:
    report = _read_json(run_path)
    exact = dict(report.get("authoritative_profitability_metrics") or report.get("exact_contract_metrics") or {})
    all_priced = {
        "trade_count": report.get("total_trades"),
        "profit_factor": report.get("profit_factor"),
        "avg_pnl_pct": report.get("avg_pnl_pct"),
        "win_rate_pct": report.get("win_rate_pct"),
    }
    exact_count = int(_metric(exact, "trade_count", "trades") or 0)
    exact_pf = float(_metric(exact, "profit_factor") or 0.0)
    checklist = {
        "source_run": str(run_path),
        "playbook": report.get("playbook"),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "promotion_allowed": False,
        "reason": "Checklist is advisory only; live promotion still requires exact-contract forward proof.",
        "evidence": {
            "all_priced_research": all_priced,
            "exact_contract_proof": exact,
            "quote_window": {
                "earliest_quote_at_utc": (report.get("truth_store") or {}).get("earliest_quote_at_utc"),
                "latest_quote_at_utc": (report.get("truth_store") or {}).get("latest_quote_at_utc"),
            },
        },
        "requirements": [
            {
                "id": "exact_historical_trade_count",
                "status": _status(exact_count, min_exact_trades),
                "current": exact_count,
                "target": min_exact_trades,
            },
            {
                "id": "exact_historical_profit_factor",
                "status": _status(exact_pf, min_profit_factor),
                "current": exact_pf,
                "target": min_profit_factor,
            },
            {
                "id": "closed_forward_trade_count",
                "status": "needs_forward_collection",
                "current": 0,
                "target": min_closed_forward_trades,
            },
        ],
        "next_actions": [
            "Run the quality90_debit55_canary scan lane as the proof/control yardstick.",
            "Record every exact live-chain canary pick into the forward ledger.",
            "Do not promote from all-priced research rows alone.",
        ],
    }
    checklist["checklist_fingerprint"] = build_promotion_checklist_fingerprint(checklist)
    return checklist


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an advisory promotion checklist for a canary replay.")
    parser.add_argument("--run", required=True)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--force", action="store_true", help="Write a new checklist even if the same source run and targets were already checked.")
    args = parser.parse_args()

    checklist = build_canary_promotion_checklist(Path(args.run))
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    duplicate = find_duplicate_promotion_checklist(output_dir, str(checklist.get("checklist_fingerprint") or ""))
    if duplicate is not None and not args.force:
        print(
            json.dumps(
                {
                    "status": "duplicate_skipped",
                    "duplicate_of": str(duplicate),
                    "fingerprint": checklist.get("checklist_fingerprint"),
                    "requirements": checklist["requirements"],
                    "hint": "Use --force to write a new checklist for this source run and target set.",
                },
                indent=2,
            )
        )
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = output_dir / f"promotion_checklist_{stamp}_{Path(args.run).stem}.json"
    latest_path = output_dir / "latest.json"
    serialized = json.dumps(checklist, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    print(json.dumps({"output": str(output_path), "latest": str(latest_path), "requirements": checklist["requirements"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
