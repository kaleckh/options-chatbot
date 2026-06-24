from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_regular_options_all_planned_sleeves as all_planned
REPORT_ID = "regular_options_base_clean_stack_identity_ledger"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-base-clean-stack-identity-ledger.md"

DEFAULT_EXPECTED_BASE_CLEAN_ROWS = 157
PROTECTED_HOLDOUT_START = "2026-06-05"

REQUIRED_IDENTITY_FIELDS = (
    "lane_id",
    "source_playbook",
    "ticker",
    "entry_date",
    "direction",
    "strategy_type",
    "long_contract_symbol",
    "short_contract_symbol",
    "entry_policy",
    "exit_policy",
    "candidate_source_id",
)

BANNED_IDENTITY_FIELDS = {
    "pnl_pct",
    "pnl_percent",
    "realized_pnl",
    "realized_pnl_usd",
    "net_pnl",
    "net_pnl_usd",
    "future_move",
    "future_return",
    "exit_result",
    "source_mark",
    "midpoint",
    "model_price",
    "last_trade",
    "eod_mark",
    "display_mark",
    "manual_mark",
    "synthetic_mark",
    "protected_holdout_data",
}

READ_ONLY_FLAGS = {
    "read_only": True,
    "research_only": True,
    "accepted_profitability": False,
    "proof_row_count": 0,
    "historical_replay_performed": False,
    "replay_performed": False,
    "historical_rows_are_forward_proof": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "production_scanner_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "scanner_strategy_stop_sizing_or_proof_bar_changed": False,
    "promotion_ready": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_run_replay",
    "do_not_create_trades",
    "do_not_prepare_or_submit_broker_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_import_quotes",
    "do_not_mutate_evidence_stores",
    "do_not_append_forward_cohort_rows",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_count_ledger_rows_as_profitability_or_forward_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "expected_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["report_id"] = payload.get("report_id") or payload.get("contract_id")
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("last_updated")
    return payload, meta


def _fixture_rows(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    rows = payload.get("selected_trades") or payload.get("rows") or payload.get("trades")
    if isinstance(rows, list):
        return [_as_dict(row) for row in rows], []
    if isinstance(payload.get("base_clean_stack"), dict):
        return [], ["aggregate_only_base_stack_not_acceptable"]
    return [], ["base_clean_stack_row_source_missing"]


def _load_base_rows(source_rows_path: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    if source_rows_path is not None:
        payload, meta = _load_json(source_rows_path, required=True)
        if meta.get("status") != "loaded":
            return [], meta, ["base_clean_stack_row_source_missing"]
        rows, blockers = _fixture_rows(payload)
        return rows, meta, blockers
    raw_rows = all_planned.base_clean_rows()
    selected = all_planned.multilane.dedupe_portfolio_trades(raw_rows)["selected_trades"]
    meta = {
        "path": "scripts/run_regular_options_all_planned_sleeves.py:base_clean_rows",
        "required": True,
        "exists": True,
        "status": "loaded",
        "raw_row_count": len(raw_rows),
        "deduped_selected_row_count": len(selected),
        "source": "existing_local_all_planned_base_clean_rows",
    }
    return [_as_dict(row) for row in selected], meta, []


def identity_payload(row: dict[str, Any]) -> dict[str, Any]:
    source_playbook = _norm(row.get("source_playbook"))
    return {
        "lane_id": _norm(row.get("lane_id")),
        "lane_family": _norm(row.get("lane_family")),
        "source_playbook": source_playbook,
        "ticker": _norm(row.get("ticker")).upper(),
        "entry_date": _norm(row.get("entry_date")),
        "planned_entry_timestamp": _norm(row.get("planned_entry_timestamp")),
        "direction": _norm(row.get("direction")).lower(),
        "strategy_type": _norm(row.get("strategy_type")),
        "long_contract_symbol": _norm(row.get("long_contract_symbol")),
        "short_contract_symbol": _norm(row.get("short_contract_symbol")),
        "entry_policy": _norm(row.get("entry_policy") or source_playbook),
        "exit_policy": _norm(row.get("exit_policy") or source_playbook),
        "candidate_source_id": _norm(row.get("candidate_source_id") or row.get("source_result_path") or source_playbook),
        "entry_contract_resolution": _norm(row.get("entry_contract_resolution")),
        "proof_grade": _norm(row.get("proof_grade")),
        "dedupe_key": _norm(row.get("dedupe_key")),
    }


def identity_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf8")).hexdigest()


def _missing_identity_fields(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in REQUIRED_IDENTITY_FIELDS:
        if payload.get(field) in ("", None, []):
            missing.append(field)
    return missing


def _ledger_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    payload = identity_payload(row)
    missing = _missing_identity_fields(payload)
    used_fields = set(payload)
    declared_identity_fields = {str(item) for item in _as_list(row.get("identity_fields"))}
    future_fields = sorted(used_fields.intersection(BANNED_IDENTITY_FIELDS) | declared_identity_fields.intersection(BANNED_IDENTITY_FIELDS))
    protected_overlap = _norm(row.get("entry_date")) >= PROTECTED_HOLDOUT_START
    return {
        "ledger_row_id": f"base_clean_{index:04d}",
        "source_path": _norm(row.get("source_result_path")),
        "source_row_id": _norm(row.get("source_row_id") or row.get("dedupe_key") or f"row_{index}"),
        "stable_identity_hash": identity_hash(payload),
        "identity_payload": payload,
        "identity_field_completeness": "complete" if not missing else "missing_required_fields",
        "missing_identity_fields": missing,
        "future_or_outcome_identity_fields": future_fields,
        "protected_holdout_overlap": protected_overlap,
        "proof_eligibility_flags": {
            "exact_priced": row.get("exact_priced") is True,
            "proof_grade": row.get("proof_grade"),
            "portfolio_eligible": row.get("portfolio_eligible") is True,
        },
        "source_row_contains_outcome_fields_not_used_for_identity": sorted(
            str(key) for key in row if str(key) in BANNED_IDENTITY_FIELDS
        ),
    }


def build_report(
    *,
    source_rows_path: Path | None = None,
    as_of_date: str = "2026-06-04",
    expected_base_clean_rows: int = DEFAULT_EXPECTED_BASE_CLEAN_ROWS,
    no_write_requested: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    rows, source_meta, source_blockers = _load_base_rows(source_rows_path)
    ledger = [_ledger_row(row, index) for index, row in enumerate(rows, start=1)]
    hashes = [str(row["stable_identity_hash"]) for row in ledger]
    duplicate_hashes = sorted({item for item in hashes if hashes.count(item) > 1})
    missing_rows = [row for row in ledger if row["missing_identity_fields"]]
    future_rows = [row for row in ledger if row["future_or_outcome_identity_fields"]]
    holdout_rows = [row for row in ledger if row["protected_holdout_overlap"]]
    blockers = set(source_blockers)
    if not rows:
        blockers.add("base_clean_stack_row_source_missing")
    if len(ledger) != int(expected_base_clean_rows):
        blockers.add("expected_base_clean_row_count_mismatch")
    if duplicate_hashes:
        blockers.add("duplicate_base_identity_hashes")
    if missing_rows:
        blockers.add("missing_required_identity_fields")
    if future_rows:
        blockers.add("future_field_dependency_detected")
    if holdout_rows:
        blockers.add("protected_holdout_overlap_detected")
    status = "base_clean_stack_identity_ledger_ready" if not blockers else "blocked_base_clean_stack_identity_ledger"
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "no_write_requested": no_write_requested,
        "scope": "read_only_base_clean_stack_row_level_identity_ledger",
        "as_of_date": as_of_date,
        "protected_holdout_start": PROTECTED_HOLDOUT_START,
        "expected_base_clean_stack_exact_rows": int(expected_base_clean_rows),
        "ledger_row_count": len(ledger),
        "unique_identity_count": len(set(hashes)),
        "duplicate_identity_count": len(duplicate_hashes),
        "duplicate_identity_hashes": duplicate_hashes,
        "missing_identity_field_row_count": len(missing_rows),
        "future_or_outcome_field_dependency_count": len(future_rows),
        "protected_holdout_overlap_count": len(holdout_rows),
        "identity_hashes": hashes,
        "required_identity_fields": list(REQUIRED_IDENTITY_FIELDS),
        "banned_identity_fields": sorted(BANNED_IDENTITY_FIELDS),
        "ledger_entries": ledger,
        "blockers": sorted(blockers),
        "source_artifacts": {"base_clean_row_source": source_meta},
        "accepted_profitability_reason": "A row-level identity ledger is duplicate-control infrastructure only; it is not replay, profitability proof, or forward evidence.",
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) != expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("accepted_profitability") is not False or report.get("proof_row_count") != 0:
        raise ValueError("ledger cannot claim accepted profitability or proof rows")
    if report["status"] == "base_clean_stack_identity_ledger_ready":
        if report.get("ledger_row_count") != report.get("expected_base_clean_stack_exact_rows"):
            raise ValueError("ready ledger row count mismatch")
        if report.get("unique_identity_count") != report.get("ledger_row_count"):
            raise ValueError("ready ledger identity count mismatch")
        for key in ("duplicate_identity_count", "missing_identity_field_row_count", "future_or_outcome_field_dependency_count", "protected_holdout_overlap_count"):
            if report.get(key) != 0:
                raise ValueError(f"ready ledger has nonzero {key}")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Base Clean Stack Identity Ledger",
        "",
        "This generated artifact is a read-only row-level identity ledger for the current clean base stack. It is duplicate-control infrastructure only and does not create proof rows, run replay, or claim profitability.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Expected base clean rows: `{report['expected_base_clean_stack_exact_rows']}`.",
        f"- Ledger rows: `{report['ledger_row_count']}`.",
        f"- Unique identities: `{report['unique_identity_count']}`.",
        f"- Duplicate identities: `{report['duplicate_identity_count']}`.",
        f"- Missing identity rows: `{report['missing_identity_field_row_count']}`.",
        f"- Future/outcome identity dependencies: `{report['future_or_outcome_field_dependency_count']}`.",
        f"- Protected holdout overlaps: `{report['protected_holdout_overlap_count']}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        "",
        "## Required Identity Fields",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report["required_identity_fields"])
    lines.extend(["", "## Blockers", ""])
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in report["blockers"])
    else:
        lines.append("- None.")
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in report["forbidden_actions"])
    lines.append("")
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
    json_path = output_dir / f"{stamp}.json"
    md_path = output_dir / f"{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    markdown = render_markdown(report_with_artifacts)
    for path in (json_path, latest_json):
        path.write_text(json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a read-only base clean stack row-level identity ledger.")
    parser.add_argument("--source-rows", type=Path, default=None)
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--expected-base-clean-rows", type=int, default=DEFAULT_EXPECTED_BASE_CLEAN_ROWS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        source_rows_path=args.source_rows,
        as_of_date=args.as_of_date,
        expected_base_clean_rows=args.expected_base_clean_rows,
        no_write_requested=args.no_write,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
