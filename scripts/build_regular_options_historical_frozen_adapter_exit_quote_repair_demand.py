from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_13_symbol_candidate_generation_surface_audit import _as_dict, _as_list  # noqa: E402
from scripts.build_regular_options_historical_frozen_scanner_replay_adapter import REPORT_ID as ADAPTER_REPORT_ID  # noqa: E402
from scripts.build_regular_options_robust_search_evaluation import _load_json  # noqa: E402


REPORT_ID = "regular_options_historical_frozen_adapter_exit_quote_repair_demand"
DEFAULT_ADAPTER = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-frozen-scanner-replay-adapter" / "latest.json"
)
DEFAULT_OUTPUT_DIR = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-frozen-adapter-exit-quote-repair-demand"
)
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-historical-frozen-adapter-exit-quote-repair-demand.md"
FALSE_FLAGS = {
    "read_only": True,
    "research_only": True,
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "promotion_ready": False,
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _repairable_trade(row: dict[str, Any]) -> dict[str, Any] | None:
    if row.get("exit_pricing_status") != "missing_trusted_exit_quote":
        return None
    exit_date = str(row.get("exit_date") or "")[:10]
    long_contract = str(row.get("long_contract_symbol") or "").strip().upper()
    short_contract = str(row.get("short_contract_symbol") or "").strip().upper()
    if not exit_date or not long_contract or not short_contract:
        return None
    return {
        "ticker": str(row.get("ticker") or row.get("symbol") or "").strip().upper(),
        "date": str(row.get("entry_date") or row.get("candidate_generation_date") or "")[:10],
        "missing_quote_date": exit_date,
        "missing_long_contract_symbol": long_contract,
        "missing_short_contract_symbol": short_contract,
        "unpriced_reason": "missing_exit_quote_for_leg",
        "source_row_id": row.get("row_id"),
        "source_dedupe_key": row.get("dedupe_key"),
        "source_exit_pricing_status": row.get("exit_pricing_status"),
    }


def build_report(
    *,
    adapter_path: Path = DEFAULT_ADAPTER,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    adapter, adapter_meta = _load_json(adapter_path)
    blockers: list[str] = []
    if adapter_meta.get("status") != "loaded" or adapter.get("report_id") != ADAPTER_REPORT_ID:
        blockers.append("historical_frozen_adapter_not_loaded")
    selected = [_as_dict(row) for row in _as_list(adapter.get("selected_candidates"))]
    demand_rows = [trade for row in selected if (trade := _repairable_trade(row))]
    excluded = Counter(
        str(row.get("exit_pricing_status") or "missing_exit_pricing_status")
        for row in selected
        if row.get("exact_priced") is not True and _repairable_trade(row) is None
    )
    target_contracts = sorted(
        {
            str(trade.get(key))
            for trade in demand_rows
            for key in ("missing_long_contract_symbol", "missing_short_contract_symbol")
            if trade.get(key)
        }
    )
    target_dates = sorted({str(trade["missing_quote_date"]) for trade in demand_rows})
    if blockers:
        status = "blocked_exit_quote_repair_demand"
    elif demand_rows:
        status = "exit_quote_repair_demand_ready"
    else:
        status = "exit_quote_repair_demand_empty"
    plan_command = (
        "uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py "
        f"{_rel(DEFAULT_OUTPUT_DIR / 'latest.json')} --plan-only --json"
    )
    import_command_template = (
        "uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py "
        f"{_rel(DEFAULT_OUTPUT_DIR / 'latest.json')} --theta-url http://127.0.0.1:25503 "
        "--source thetadata_opra_nbbo_1m --snapshot-kind intraday --interval 1m "
        "--start-time 15:55:00 --end-time 15:55:00 --timeout 180 --json"
    )
    return {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **FALSE_FLAGS,
        "source_adapter": adapter_meta,
        "selected_candidate_count": len(selected),
        "unpriced_repairable_trade_count": len(demand_rows),
        "target_contract_count": len(target_contracts),
        "target_quote_date_count": len(target_dates),
        "target_contracts": target_contracts,
        "target_quote_dates": target_dates,
        "excluded_unpriced_exit_status_counts": dict(sorted(excluded.items())),
        "unpriced_trades": demand_rows,
        "blockers": blockers,
        "plan_only_command": plan_command,
        "future_import_command_template": import_command_template,
        "boundary": "Read-only demand artifact only; it does not request ThetaData, import quotes, mutate options_history.db, rerun replay, or make profitability claims.",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Historical Frozen Adapter Exit Quote Repair Demand",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Repairable selected rows: `{report.get('unpriced_repairable_trade_count')}`.",
        f"- Target contracts: `{report.get('target_contract_count')}`.",
        f"- Target quote dates: `{report.get('target_quote_date_count')}`.",
        f"- Quotes imported: `{str(report.get('quotes_imported')).lower()}`.",
        "",
        "## Excluded Unpriced Statuses",
        "",
    ]
    excluded = _as_dict(report.get("excluded_unpriced_exit_status_counts"))
    lines.extend(f"- `{key}`: `{value}`" for key, value in excluded.items()) if excluded else lines.append("- None.")
    lines.extend(
        [
            "",
            "## Commands",
            "",
            "```powershell",
            str(report.get("plan_only_command")),
            str(report.get("future_import_command_template")),
            "```",
            "",
            "## Boundary",
            "",
            str(report.get("boundary")),
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    payload = dict(report)
    payload["artifacts"] = artifacts
    markdown = render_markdown(payload)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build read-only exit quote repair demand from the frozen adapter.")
    parser.add_argument("--adapter", type=Path, default=DEFAULT_ADAPTER)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    report = build_report(adapter_path=args.adapter)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    print(json.dumps(report, indent=2, sort_keys=True) if args.json_output else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
