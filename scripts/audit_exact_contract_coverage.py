from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from exact_contract_accounting import (  # noqa: E402
    NEAREST_CONTRACT_RESOLUTION,
    contract_resolution_accounting,
    is_exact_contract_resolution,
    trade_contract_resolution,
)
DEFAULT_RUNS_DIR = ROOT / "data" / "options-validation" / "runs"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "exact-coverage-audits"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _fingerprint_payload(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "exact_contract_coverage_audit",
        "source_run": str(audit.get("source_run") or ""),
        "playbook": str(audit.get("playbook") or ""),
        "pricing_lane": str(audit.get("pricing_lane") or ""),
        "lookback_years": audit.get("lookback_years"),
    }


def build_exact_coverage_fingerprint(audit: dict[str, Any]) -> str:
    payload = _fingerprint_payload(audit)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def find_duplicate_exact_coverage_audit(output_dir: Path, fingerprint: str) -> Path | None:
    for audit_path in sorted(Path(output_dir).glob("exact_coverage_audit_*.json")):
        try:
            audit = _read_json(audit_path)
        except (OSError, json.JSONDecodeError):
            continue
        if audit.get("audit_fingerprint") == fingerprint:
            return audit_path
    return None


def _resolution(trade: dict[str, Any]) -> str:
    return trade_contract_resolution(trade)


def _month(value: Any) -> str:
    text = str(value or "")
    return text[:7] if len(text) >= 7 else "unknown"


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    accounting = contract_resolution_accounting(rows, priced_trade_count=total, candidate_trade_count=total)
    exact = int(accounting["exact_contract_match_count"])
    nearest = int(accounting["nearest_contract_match_count"])
    unresolved = int(accounting["unresolved_contract_count"])
    return {
        "total": total,
        "exact": exact,
        "nearest": nearest,
        "unresolved": unresolved,
        "exact_pct": round(exact / total * 100.0, 1) if total else 0.0,
    }


def _group(rows: list[dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if key_name == "ticker":
            key = str(row.get("ticker") or "unknown").upper()
        elif key_name == "month":
            key = _month(row.get("date"))
        elif key_name == "resolution":
            key = _resolution(row)
        else:
            key = "unknown"
        groups[key].append(row)
    output = [{"key": key, **_metrics(group_rows)} for key, group_rows in groups.items()]
    output.sort(key=lambda item: (item["exact_pct"], -item["total"], item["key"]))
    return output


def build_exact_coverage_audit(report_path: Path) -> dict[str, Any]:
    report = _read_json(report_path)
    trades = [trade for trade in list(report.get("trades") or []) if trade.get("priced", True)]
    resolutions = Counter(_resolution(trade) for trade in trades)
    accounting = contract_resolution_accounting(
        trades,
        priced_trade_count=int(report.get("priced_trade_count") or len(trades)),
        candidate_trade_count=int(report.get("candidate_trade_count") or len(trades)),
    )
    exact_rows = [trade for trade in trades if is_exact_contract_resolution(_resolution(trade))]
    nearest_rows = [trade for trade in trades if _resolution(trade) == NEAREST_CONTRACT_RESOLUTION]
    audit = {
        "source_run": str(report_path),
        "playbook": report.get("playbook"),
        "pricing_lane": report.get("pricing_lane") or report.get("effective_pricing_lane"),
        "lookback_years": report.get("lookback_years"),
        "quote_coverage_pct": report.get("quote_coverage_pct"),
        "earliest_quote_at_utc": (report.get("truth_store") or {}).get("earliest_quote_at_utc"),
        "latest_quote_at_utc": (report.get("truth_store") or {}).get("latest_quote_at_utc"),
        "contract_accounting": accounting,
        "overall": _metrics(trades),
        "authoritative_exact": _metrics(exact_rows),
        "research_nearest_listed": _metrics(nearest_rows),
        "resolution_counts": dict(resolutions),
        "by_ticker": _group(trades, "ticker"),
        "by_month": _group(trades, "month"),
        "by_resolution": _group(trades, "resolution"),
        "next_data_need": (
            "Collect more exact live-chain/forward observations for this canary; nearest-listed rows are useful research only."
        ),
    }
    audit["audit_fingerprint"] = build_exact_coverage_fingerprint(audit)
    return audit


def _latest_matching_run(runs_dir: Path, playbook: str) -> Path:
    matches = sorted(runs_dir.glob(f"*{playbook}*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not matches:
        raise FileNotFoundError(f"No runs found for playbook {playbook!r} under {runs_dir}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit exact-contract coverage for a replay run.")
    parser.add_argument("--run")
    parser.add_argument("--runs-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--playbook", default="bullish_index_calls_quality90_debit55")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--force", action="store_true", help="Write a new artifact even if this exact source run was already audited.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report_path = Path(args.run) if args.run else _latest_matching_run(Path(args.runs_dir), args.playbook)
    audit = build_exact_coverage_audit(report_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    duplicate = find_duplicate_exact_coverage_audit(output_dir, str(audit.get("audit_fingerprint") or ""))
    if duplicate is not None and not args.force:
        compact = {
            "status": "duplicate_skipped",
            "duplicate_of": str(duplicate),
            "fingerprint": audit.get("audit_fingerprint"),
            "source_run": audit["source_run"],
            "overall": audit["overall"],
            "hint": "Use --force to write a new exact coverage artifact for this source run.",
        }
        print(json.dumps(audit if args.json else compact, indent=2))
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = output_dir / f"exact_coverage_audit_{stamp}_{report_path.stem}.json"
    latest_path = output_dir / "latest.json"
    serialized = json.dumps(audit, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    compact = {
        "output": str(output_path),
        "latest": str(latest_path),
        "source_run": audit["source_run"],
        "overall": audit["overall"],
        "by_ticker": audit["by_ticker"],
        "next_data_need": audit["next_data_need"],
    }
    print(json.dumps(audit if args.json else compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
