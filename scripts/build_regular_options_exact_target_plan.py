from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.regular_options_repair_targets import contract_parts  # noqa: E402


REPORT_ID = "regular_options_exact_target_plan"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-exact-target-plan"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-exact-target-plan.md"
DEFAULT_MANIFEST = (
    ROOT / "data" / "profitability-lab" / "regular-options-robust-candidate-source-quality-manifest" / "latest.json"
)
DEFAULT_BULLISH_PULLBACK_RUN = (
    ROOT / "data" / "options-validation" / "runs" / "20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json"
)
DEFAULT_LANE_A_RUN = (
    ROOT
    / "data"
    / "options-validation"
    / "runs"
    / "20260530_191945_lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1_intraday.json"
)
PROTECTED_HOLDOUT_START = "2026-06-05"
MISSING_EXIT_QUOTE_REASON = "missing_exit_quote_for_leg"
NO_CHAIN_NATIVE_SPREAD_REASON = "no_chain_native_spread"


PERMISSION_TABLE = [
    {
        "permission": "read_only_ok",
        "allowed": True,
        "applies_to": "Extracting, grouping, deduping, and reporting exact target rows from existing artifacts.",
        "requires_approval": False,
    },
    {
        "permission": "evidence_mutation_requires_approval",
        "allowed": False,
        "applies_to": "Any quote import, evidence-store write, replay write, DB migration, backup/delete, or --apply path.",
        "requires_approval": True,
    },
    {
        "permission": "policy_change_requires_approval",
        "allowed": False,
        "applies_to": "Any source-quality policy, scanner, contract-selection, proof-bar, lane-state, stop, or sizing change.",
        "requires_approval": True,
    },
    {
        "permission": "not_actionable_without_forward_evidence",
        "allowed": False,
        "applies_to": "Promotion, production proof, live-validation, or forward-proof claims from these historical rows.",
        "requires_approval": True,
    },
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _norm(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _rel(path: Path | str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate).replace("\\", "/")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": _rel(path), "error": "missing_artifact"}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "unreadable", "path": _rel(path), "error": type(exc).__name__}
    return payload if isinstance(payload, dict) else {"status": "invalid", "path": _rel(path), "error": "json_root_not_object"}


def _parse_date(value: Any) -> date | None:
    text = _norm(value)[:10]
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _date_status(value: Any, *, holdout_start: date, basis: str) -> dict[str, Any]:
    parsed = _parse_date(value)
    if parsed is None:
        return {
            "date_basis": basis,
            "date": None,
            "pre_holdout": None,
            "protected_holdout_overlap": None,
            "holdout_status": "missing_or_invalid_date",
        }
    overlap = parsed >= holdout_start
    return {
        "date_basis": basis,
        "date": parsed.isoformat(),
        "pre_holdout": not overlap,
        "protected_holdout_overlap": overlap,
        "holdout_status": "protected_holdout_overlap" if overlap else "pre_holdout",
    }


def _reason(row: dict[str, Any]) -> str:
    return _norm(row.get("unpriced_reason") or row.get("non_promotable_reason") or "unknown")


def _ticker(row: dict[str, Any]) -> str:
    value = _norm(row.get("ticker") or row.get("underlying") or row.get("symbol")).upper()
    return value or "UNKNOWN"


def _missing_contract_fields(row: dict[str, Any]) -> list[tuple[str, str, str]]:
    fields: list[tuple[str, str, str]] = []
    for side, key in (("long", "missing_long_contract_symbol"), ("short", "missing_short_contract_symbol")):
        contract = _norm(row.get(key)).upper()
        if contract:
            fields.append((side, key, contract))
    return fields


def _target_key(*, quote_date: str, contract_symbol: str, leg_side: str, source_field: str, reason: str) -> str:
    return "|".join([quote_date, contract_symbol.upper(), leg_side, source_field, reason])


def _source_occurrence(
    *,
    row: dict[str, Any],
    row_index: int,
    source_path: Path | str,
    leg_side: str,
    source_field: str,
) -> dict[str, Any]:
    return {
        "source_path": _rel(source_path),
        "source_row_index": row_index,
        "ticker": _ticker(row),
        "candidate_entry_date": _norm(row.get("date"))[:10] or None,
        "leg_side": leg_side,
        "source_field": source_field,
        "reason": _reason(row),
        "long_contract_symbol": _norm(row.get("long_contract_symbol")).upper() or None,
        "short_contract_symbol": _norm(row.get("short_contract_symbol")).upper() or None,
        "sleeve_id": _norm(row.get("sleeve_id")) or None,
        "selection_source": _norm(row.get("selection_source")) or None,
        "calibration_density": _norm(row.get("calibration_density")) or None,
        "strategy_type": _norm(row.get("strategy_type")) or None,
        "option_type": _norm(row.get("type")) or None,
    }


def build_missing_quote_group(
    *,
    group_id: str,
    label: str,
    source_path: Path | str,
    run_report: dict[str, Any],
    holdout_start: date,
) -> dict[str, Any]:
    rows = [dict(row) for row in _as_list(run_report.get("unpriced_trades") or run_report.get("unpriced_candidates"))]
    reason_counts: Counter[str] = Counter()
    ticker_counts: Counter[str] = Counter()
    quote_date_counts: Counter[str] = Counter()
    leg_field_counts: Counter[str] = Counter()
    targets: dict[str, dict[str, Any]] = {}
    missing_quote_row_count = 0
    rows_without_contract_count = 0

    for index, row in enumerate(rows):
        reason = _reason(row)
        if reason != MISSING_EXIT_QUOTE_REASON:
            continue
        missing_quote_row_count += 1
        reason_counts[reason] += 1
        ticker_counts[_ticker(row)] += 1
        fields = _missing_contract_fields(row)
        if not fields:
            rows_without_contract_count += 1
            continue
        quote_date = _norm(row.get("missing_quote_date"))[:10]
        quote_date_counts[quote_date or "UNKNOWN"] += 1
        for leg_side, source_field, contract_symbol in fields:
            key = _target_key(
                quote_date=quote_date,
                contract_symbol=contract_symbol,
                leg_side=leg_side,
                source_field=source_field,
                reason=reason,
            )
            status = _date_status(quote_date, holdout_start=holdout_start, basis="missing_quote_date")
            target = targets.setdefault(
                key,
                {
                    "target_key": key,
                    "group_id": group_id,
                    "label": label,
                    "importable_quote_target": True,
                    "ticker": _ticker(row),
                    "tickers": [],
                    "quote_date": quote_date or None,
                    "target_date_basis": "missing_quote_date",
                    "leg_side": leg_side,
                    "source_field": source_field,
                    "reason": reason,
                    "contract_symbol": contract_symbol,
                    "contract": contract_parts(contract_symbol),
                    "pre_holdout": status["pre_holdout"],
                    "protected_holdout_overlap": status["protected_holdout_overlap"],
                    "holdout_status": status["holdout_status"],
                    "source_occurrence_count": 0,
                    "candidate_entry_dates": [],
                    "source_occurrences": [],
                },
            )
            occurrence = _source_occurrence(
                row=row,
                row_index=index,
                source_path=source_path,
                leg_side=leg_side,
                source_field=source_field,
            )
            target["source_occurrences"].append(occurrence)
            target["source_occurrence_count"] = len(target["source_occurrences"])
            target["tickers"] = sorted({item["ticker"] for item in target["source_occurrences"] if item.get("ticker")})
            target["candidate_entry_dates"] = sorted(
                {
                    str(item["candidate_entry_date"])
                    for item in target["source_occurrences"]
                    if item.get("candidate_entry_date")
                }
            )

    target_list = sorted(
        targets.values(),
        key=lambda item: (
            str(item.get("ticker") or ""),
            str(item.get("quote_date") or ""),
            str(item.get("leg_side") or ""),
            str(item.get("source_field") or ""),
            str(item.get("contract_symbol") or ""),
        ),
    )
    duplicate_targets = [item for item in target_list if int(item.get("source_occurrence_count") or 0) > 1]
    overlap_count = sum(1 for item in target_list if item.get("protected_holdout_overlap") is True)
    pre_holdout_count = sum(1 for item in target_list if item.get("pre_holdout") is True)
    quote_dates = sorted({str(item["quote_date"]) for item in target_list if item.get("quote_date")})
    return {
        "group_id": group_id,
        "label": label,
        "source_path": _rel(source_path),
        "classification": "importable_missing_exit_quote_target_plan_only",
        "row_count": missing_quote_row_count,
        "target_occurrence_count": sum(int(item.get("source_occurrence_count") or 0) for item in target_list),
        "unique_target_count": len(target_list),
        "duplicate_target_count": len(duplicate_targets),
        "duplicate_extra_row_count": sum(int(item.get("source_occurrence_count") or 0) - 1 for item in duplicate_targets),
        "rows_without_contract_count": rows_without_contract_count,
        "reason_counts": dict(sorted(reason_counts.items())),
        "ticker_counts": dict(sorted(ticker_counts.items())),
        "quote_date_counts": dict(sorted(quote_date_counts.items())),
        "leg_field_counts": dict(sorted(leg_field_counts.items())),
        "first_quote_date": quote_dates[0] if quote_dates else None,
        "last_quote_date": quote_dates[-1] if quote_dates else None,
        "pre_holdout_unique_target_count": pre_holdout_count,
        "protected_holdout_overlap_unique_target_count": overlap_count,
        "all_targets_pre_holdout": bool(target_list) and overlap_count == 0 and pre_holdout_count == len(target_list),
        "targets": target_list,
        "duplicate_targets": duplicate_targets,
    }


def build_no_chain_bucket(
    *,
    source_path: Path | str,
    run_report: dict[str, Any],
    holdout_start: date,
) -> dict[str, Any]:
    rows = [dict(row) for row in _as_list(run_report.get("unpriced_trades") or run_report.get("unpriced_candidates"))]
    gaps: list[dict[str, Any]] = []
    ticker_counts: Counter[str] = Counter()
    entry_date_counts: Counter[str] = Counter()

    for index, row in enumerate(rows):
        reason = _reason(row)
        if reason != NO_CHAIN_NATIVE_SPREAD_REASON:
            continue
        ticker = _ticker(row)
        entry_date = _norm(row.get("date"))[:10] or None
        status = _date_status(entry_date, holdout_start=holdout_start, basis="candidate_entry_date")
        ticker_counts[ticker] += 1
        entry_date_counts[entry_date or "UNKNOWN"] += 1
        gaps.append(
            {
                "gap_key": "|".join([ticker, str(entry_date), reason, str(index)]),
                "bucket_id": "lane_a_no_chain_native_spread",
                "classification": "non_importable_selection_gap",
                "importable_quote_target": False,
                "source_path": _rel(source_path),
                "source_row_index": index,
                "ticker": ticker,
                "candidate_entry_date": entry_date,
                "target_date": None,
                "target_date_basis": "not_applicable_no_chain_native_spread",
                "reason": reason,
                "pre_holdout": status["pre_holdout"],
                "protected_holdout_overlap": status["protected_holdout_overlap"],
                "holdout_status": status["holdout_status"],
                "sleeve_id": _norm(row.get("sleeve_id")) or None,
                "selection_source": _norm(row.get("selection_source")) or None,
                "calibration_density": _norm(row.get("calibration_density")) or None,
                "strategy_type": _norm(row.get("strategy_type")) or None,
                "option_type": _norm(row.get("type")) or None,
            }
        )

    gaps.sort(key=lambda item: (str(item.get("ticker")), str(item.get("candidate_entry_date")), item["source_row_index"]))
    entry_dates = sorted({str(item["candidate_entry_date"]) for item in gaps if item.get("candidate_entry_date")})
    overlap_count = sum(1 for item in gaps if item.get("protected_holdout_overlap") is True)
    pre_holdout_count = sum(1 for item in gaps if item.get("pre_holdout") is True)
    return {
        "bucket_id": "lane_a_no_chain_native_spread",
        "label": "Lane A rows with no chain-native spread under current selection filters",
        "source_path": _rel(source_path),
        "classification": "non_importable_selection_gap",
        "row_count": len(gaps),
        "unique_gap_count": len(gaps),
        "ticker_counts": dict(sorted(ticker_counts.items())),
        "entry_date_counts": dict(sorted(entry_date_counts.items())),
        "first_candidate_entry_date": entry_dates[0] if entry_dates else None,
        "last_candidate_entry_date": entry_dates[-1] if entry_dates else None,
        "pre_holdout_entry_count": pre_holdout_count,
        "protected_holdout_overlap_entry_count": overlap_count,
        "all_entries_pre_holdout": bool(gaps) and overlap_count == 0 and pre_holdout_count == len(gaps),
        "gaps": gaps,
    }


def _global_duplicate_summary(groups: list[dict[str, Any]]) -> dict[str, Any]:
    all_targets: dict[str, dict[str, Any]] = {}
    row_count = 0
    for group in groups:
        for target in _as_list(group.get("targets")):
            key = str(_as_dict(target).get("target_key") or "")
            row_count += int(_as_dict(target).get("source_occurrence_count") or 0)
            merged = all_targets.setdefault(
                key,
                {
                    "target_key": key,
                    "quote_date": target.get("quote_date"),
                    "contract_symbol": target.get("contract_symbol"),
                    "leg_side": target.get("leg_side"),
                    "source_field": target.get("source_field"),
                    "reason": target.get("reason"),
                    "groups": [],
                    "source_occurrence_count": 0,
                },
            )
            merged["groups"] = sorted(set(_as_list(merged.get("groups")) + [str(group.get("group_id"))]))
            merged["source_occurrence_count"] = int(merged.get("source_occurrence_count") or 0) + int(
                target.get("source_occurrence_count") or 0
            )
    duplicate_targets = [
        target
        for target in all_targets.values()
        if int(target.get("source_occurrence_count") or 0) > 1 or len(_as_list(target.get("groups"))) > 1
    ]
    return {
        "importable_target_row_count": row_count,
        "global_unique_importable_target_count": len(all_targets),
        "global_duplicate_extra_row_count": row_count - len(all_targets),
        "cross_group_duplicate_count": sum(1 for item in duplicate_targets if len(_as_list(item.get("groups"))) > 1),
        "duplicate_targets": sorted(
            duplicate_targets,
            key=lambda item: (
                str(item.get("quote_date") or ""),
                str(item.get("contract_symbol") or ""),
                str(item.get("source_field") or ""),
            ),
        ),
    }


def _safe_holdout_start(manifest: dict[str, Any]) -> str:
    summary = _as_dict(manifest.get("summary"))
    start = _norm(summary.get("protected_forward_holdout_start_date"))
    return start or PROTECTED_HOLDOUT_START


def _proposed_next_commands() -> list[dict[str, Any]]:
    return [
        {
            "label": "Regenerate exact target plan without writing artifacts",
            "mode": "read_only_no_write",
            "approved_for_write_or_import": False,
            "command": "uv run --locked python scripts/build_regular_options_exact_target_plan.py --no-write --json",
        },
        {
            "label": "Plan-only bullish-pullback helper readback",
            "mode": "plan_only_no_provider_request_no_write",
            "approved_for_write_or_import": False,
            "command": (
                "uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py "
                "data/options-validation/runs/20260528_224313_sleeve_pf59_coverage_a_refill_v1_intraday.json "
                "--plan-only --json"
            ),
        },
        {
            "label": "Plan-only Lane A helper readback",
            "mode": "plan_only_no_provider_request_no_write",
            "approved_for_write_or_import": False,
            "command": (
                "uv run --locked python scripts/import_missing_replay_quotes_from_thetadata.py "
                "data/options-validation/runs/20260530_191945_lane_a_chain_native_ret20_4_stop200_time75_rerun4_v1_intraday.json "
                "--plan-only --json"
            ),
        },
    ]


def build_report(
    *,
    manifest: dict[str, Any],
    bullish_pullback_run: dict[str, Any],
    lane_a_run: dict[str, Any],
    generated_at_utc: str | None = None,
    manifest_path: Path | str = DEFAULT_MANIFEST,
    bullish_pullback_run_path: Path | str = DEFAULT_BULLISH_PULLBACK_RUN,
    lane_a_run_path: Path | str = DEFAULT_LANE_A_RUN,
) -> dict[str, Any]:
    holdout_start_text = _safe_holdout_start(manifest)
    holdout_start = _parse_date(holdout_start_text) or date.fromisoformat(PROTECTED_HOLDOUT_START)
    bullish_group = build_missing_quote_group(
        group_id="bullish_pullback_missing_exit_quotes",
        label="Bullish-pullback missing short-leg exit quote targets",
        source_path=bullish_pullback_run_path,
        run_report=bullish_pullback_run,
        holdout_start=holdout_start,
    )
    lane_a_group = build_missing_quote_group(
        group_id="lane_a_missing_exit_quotes",
        label="Lane A missing short-leg exit quote targets",
        source_path=lane_a_run_path,
        run_report=lane_a_run,
        holdout_start=holdout_start,
    )
    no_chain_bucket = build_no_chain_bucket(
        source_path=lane_a_run_path,
        run_report=lane_a_run,
        holdout_start=holdout_start,
    )
    groups = [bullish_group, lane_a_group]
    global_duplicates = _global_duplicate_summary(groups)
    importable_overlap_count = sum(
        int(group.get("protected_holdout_overlap_unique_target_count") or 0) for group in groups
    )
    selection_gap_overlap_count = int(no_chain_bucket.get("protected_holdout_overlap_entry_count") or 0)
    holdout_failed = importable_overlap_count > 0 or selection_gap_overlap_count > 0
    status = "blocked_protected_holdout_overlap" if holdout_failed else "exact_target_plan_ready_read_only"
    manifest_summary = _as_dict(manifest.get("summary"))
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "read_only": True,
        "live_policy_change": False,
        "proof_claim": False,
        "promotion_ready": False,
        "scope": "regular_options_historical_exact_target_plan",
        "inputs": {
            "source_quality_manifest": _rel(manifest_path),
            "bullish_pullback_run": _rel(bullish_pullback_run_path),
            "lane_a_run": _rel(lane_a_run_path),
        },
        "manifest_readback": {
            "manifest_status": manifest.get("status"),
            "manifest_high_priority_row_count": manifest_summary.get("high_priority_row_count"),
            "manifest_expected_bullish_missing_quote_count": _as_dict(
                _as_dict(manifest.get("target_level_classifications")).get("bullish_pullback_unpriced_targets")
            ).get("missing_quote_count"),
            "manifest_expected_lane_a_missing_quote_count": _as_dict(
                _as_dict(manifest.get("target_level_classifications")).get("lane_a_unpriced_targets")
            ).get("missing_quote_count"),
            "manifest_expected_lane_a_no_chain_native_spread_count": _as_dict(
                _as_dict(manifest.get("target_level_classifications")).get("lane_a_unpriced_targets")
            ).get("no_chain_native_spread_count"),
        },
        "summary": {
            "status": status,
            "protected_holdout_start_date": holdout_start.isoformat(),
            "bullish_pullback_missing_quote_rows": bullish_group["row_count"],
            "bullish_pullback_unique_targets": bullish_group["unique_target_count"],
            "lane_a_missing_quote_rows": lane_a_group["row_count"],
            "lane_a_unique_targets": lane_a_group["unique_target_count"],
            "lane_a_no_chain_native_spread_rows": no_chain_bucket["row_count"],
            "global_importable_target_rows": global_duplicates["importable_target_row_count"],
            "global_unique_importable_targets": global_duplicates["global_unique_importable_target_count"],
            "global_duplicate_extra_rows": global_duplicates["global_duplicate_extra_row_count"],
            "protected_holdout_overlap": holdout_failed,
            "protected_holdout_overlap_importable_targets": importable_overlap_count,
            "protected_holdout_overlap_selection_gap_entries": selection_gap_overlap_count,
        },
        "holdout_guard": {
            "status": "failed_protected_holdout_overlap" if holdout_failed else "passed_pre_holdout_only",
            "protected_holdout_start_date": holdout_start.isoformat(),
            "date_basis": {
                "importable_missing_quote_targets": "missing_quote_date",
                "no_chain_native_spread_rows": "candidate_entry_date",
            },
            "importable_target_overlap_count": importable_overlap_count,
            "selection_gap_entry_overlap_count": selection_gap_overlap_count,
            "fail_closed_if_any_overlap": True,
        },
        "target_groups": {
            bullish_group["group_id"]: bullish_group,
            lane_a_group["group_id"]: lane_a_group,
        },
        "selection_gap_buckets": {
            no_chain_bucket["bucket_id"]: no_chain_bucket,
        },
        "duplicate_summary": global_duplicates,
        "permission_table": PERMISSION_TABLE,
        "proposed_next_commands": _proposed_next_commands(),
        "proof_gate_status": {
            "current_status": "read_only_plan_not_proof",
            "historical_rows_are_forward_proof": False,
            "production_proof_claim": False,
            "live_validation_allowed": False,
            "promotion_allowed": False,
            "protected_holdout_consumed": False,
            "quote_import_approved": False,
            "evidence_store_mutation_approved": False,
            "policy_change_approved": False,
        },
        "prohibited_actions": [
            "no quote imports",
            "no evidence-store mutation",
            "no --apply",
            "no DB migrations, backups, or deletes",
            "no broker, paper, live-trading, scanner, promotion, lane-state, proof-bar, source-quality policy, stop, sizing, or contract-selection changes",
            "do not run --run-all-planned",
            "do not consume protected holdout",
        ],
    }


def _cell(value: Any) -> str:
    return ("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")


def _count_text(counts: dict[str, Any], *, limit: int = 8) -> str:
    items = sorted(counts.items(), key=lambda item: (-int(item[1] or 0), str(item[0])))
    text = ", ".join(f"{key}={value}" for key, value in items[:limit])
    if len(items) > limit:
        text += f", ... +{len(items) - limit}"
    return text


def _target_table_rows(targets: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Group | Ticker | Quote Date | Side / Field | Reason | Contract | Occurrences | Holdout |",
        "|---|---|---|---|---|---|---:|---|",
    ]
    for target in targets:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(target.get('group_id'))}`",
                    f"`{_cell(target.get('ticker'))}`",
                    f"`{_cell(target.get('quote_date'))}`",
                    f"`{_cell(target.get('leg_side'))}` / `{_cell(target.get('source_field'))}`",
                    f"`{_cell(target.get('reason'))}`",
                    f"`{_cell(target.get('contract_symbol'))}`",
                    str(target.get("source_occurrence_count")),
                    f"`{_cell(target.get('holdout_status'))}`",
                ]
            )
            + " |"
        )
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    summary = _as_dict(report.get("summary"))
    guard = _as_dict(report.get("holdout_guard"))
    groups = _as_dict(report.get("target_groups"))
    bullish = _as_dict(groups.get("bullish_pullback_missing_exit_quotes"))
    lane_a = _as_dict(groups.get("lane_a_missing_exit_quotes"))
    no_chain = _as_dict(_as_dict(report.get("selection_gap_buckets")).get("lane_a_no_chain_native_spread"))
    duplicates = _as_dict(report.get("duplicate_summary"))
    proof = _as_dict(report.get("proof_gate_status"))
    all_targets = _as_list(bullish.get("targets")) + _as_list(lane_a.get("targets"))
    lines = [
        "# Regular Options Exact Target Plan",
        "",
        "This report is generated from `scripts/build_regular_options_exact_target_plan.py`. It is read-only: it extracts exact target rows from existing replay artifacts and does not request quotes, import quotes, mutate evidence stores, change policy, consume protected holdout, or make production proof claims.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Protected holdout starts `{summary.get('protected_holdout_start_date')}`; overlap `{summary.get('protected_holdout_overlap')}`.",
        f"- Bullish-pullback missing-exit quote rows: `{summary.get('bullish_pullback_missing_quote_rows')}` rows / `{summary.get('bullish_pullback_unique_targets')}` unique targets.",
        f"- Lane A missing-exit quote rows: `{summary.get('lane_a_missing_quote_rows')}` rows / `{summary.get('lane_a_unique_targets')}` unique targets.",
        f"- Lane A no-chain-native-spread rows: `{summary.get('lane_a_no_chain_native_spread_rows')}` non-importable selection-gap rows.",
        f"- Global importable target count: `{summary.get('global_importable_target_rows')}` rows / `{summary.get('global_unique_importable_targets')}` unique targets; duplicate extra rows `{summary.get('global_duplicate_extra_rows')}`.",
        "",
        "## Holdout Guard",
        "",
        f"- Guard status: `{guard.get('status')}`.",
        f"- Importable target date basis: `{_as_dict(guard.get('date_basis')).get('importable_missing_quote_targets')}`.",
        f"- Selection-gap date basis: `{_as_dict(guard.get('date_basis')).get('no_chain_native_spread_rows')}`.",
        f"- Importable target overlap count: `{guard.get('importable_target_overlap_count')}`.",
        f"- Selection-gap entry overlap count: `{guard.get('selection_gap_entry_overlap_count')}`.",
        "- If any target or selection-gap entry overlaps the protected holdout, this report status fails closed.",
        "",
        "## Target Counts",
        "",
        "| Group | Rows | Unique Targets | Duplicate Extra Rows | Date Range | Top Tickers | Reason Counts | Holdout |",
        "|---|---:|---:|---:|---|---|---|---|",
    ]
    for group in (bullish, lane_a):
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(group.get('group_id'))}`",
                    str(group.get("row_count")),
                    str(group.get("unique_target_count")),
                    str(group.get("duplicate_extra_row_count")),
                    f"`{_cell(group.get('first_quote_date'))}` to `{_cell(group.get('last_quote_date'))}`",
                    _cell(_count_text(_as_dict(group.get("ticker_counts")))),
                    _cell(_count_text(_as_dict(group.get("reason_counts")))),
                    f"`{_cell('pre_holdout' if group.get('all_targets_pre_holdout') else 'check_required')}`",
                ]
            )
            + " |"
        )

    lines.extend(["", "## Machine-Readable Target List", ""])
    lines.extend(_target_table_rows(all_targets))

    lines.extend(["", "## Lane A Selection-Gap Bucket", ""])
    lines.extend(
        [
            f"- Classification: `{no_chain.get('classification')}`.",
            f"- Rows: `{no_chain.get('row_count')}`.",
            f"- Candidate entry range: `{no_chain.get('first_candidate_entry_date')}` to `{no_chain.get('last_candidate_entry_date')}`.",
            f"- Tickers: `{_count_text(_as_dict(no_chain.get('ticker_counts')))}`.",
            "",
            "| Ticker | Candidate Entry Date | Reason | Classification | Holdout |",
            "|---|---|---|---|---|",
        ]
    )
    for gap in _as_list(no_chain.get("gaps")):
        gap = _as_dict(gap)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(gap.get('ticker'))}`",
                    f"`{_cell(gap.get('candidate_entry_date'))}`",
                    f"`{_cell(gap.get('reason'))}`",
                    f"`{_cell(gap.get('classification'))}`",
                    f"`{_cell(gap.get('holdout_status'))}`",
                ]
            )
            + " |"
        )

    lines.extend(["", "## Duplicates", ""])
    lines.extend(
        [
            f"- Global duplicate extra rows: `{duplicates.get('global_duplicate_extra_row_count')}`.",
            f"- Cross-group duplicate targets: `{duplicates.get('cross_group_duplicate_count')}`.",
            "",
            "| Quote Date | Contract | Side / Field | Reason | Groups | Occurrences |",
            "|---|---|---|---|---|---:|",
        ]
    )
    for item in _as_list(duplicates.get("duplicate_targets")):
        item = _as_dict(item)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(item.get('quote_date'))}`",
                    f"`{_cell(item.get('contract_symbol'))}`",
                    f"`{_cell(item.get('leg_side'))}` / `{_cell(item.get('source_field'))}`",
                    f"`{_cell(item.get('reason'))}`",
                    ", ".join(f"`{_cell(group)}`" for group in _as_list(item.get("groups"))),
                    str(item.get("source_occurrence_count")),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Proposed Dry-Run / Plan-Only Commands", ""])
    lines.append("No write/import command is approved by this report.")
    lines.extend(["", "| Label | Mode | Approved For Write/Import | Command |", "|---|---|---|---|"])
    for command in _as_list(report.get("proposed_next_commands")):
        command = _as_dict(command)
        lines.append(
            "| "
            + " | ".join(
                [
                    _cell(command.get("label")),
                    f"`{_cell(command.get('mode'))}`",
                    f"`{_cell(command.get('approved_for_write_or_import'))}`",
                    f"`{_cell(command.get('command'))}`",
                ]
            )
            + " |"
        )

    lines.extend(["", "## Permission Table", "", "| Permission | Allowed Here | Requires Approval | Applies To |", "|---|---|---|---|"])
    for item in _as_list(report.get("permission_table")):
        item = _as_dict(item)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{_cell(item.get('permission'))}`",
                    f"`{_cell(item.get('allowed'))}`",
                    f"`{_cell(item.get('requires_approval'))}`",
                    _cell(item.get("applies_to")),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Proof/Gate Status", ""])
    for key in (
        "current_status",
        "historical_rows_are_forward_proof",
        "production_proof_claim",
        "live_validation_allowed",
        "promotion_allowed",
        "protected_holdout_consumed",
        "quote_import_approved",
        "evidence_store_mutation_approved",
        "policy_change_approved",
    ):
        lines.append(f"- `{key}`: `{proof.get(key)}`.")

    lines.extend(["", "## Artifacts", ""])
    for key, value in _as_dict(report.get("artifacts")).items():
        lines.append(f"- `{key}`: `{_cell(_rel(value))}`")
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
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report)
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def run_plan(
    *,
    write: bool = True,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
    manifest_path: Path = DEFAULT_MANIFEST,
    bullish_pullback_run_path: Path = DEFAULT_BULLISH_PULLBACK_RUN,
    lane_a_run_path: Path = DEFAULT_LANE_A_RUN,
) -> dict[str, Any]:
    report = build_report(
        manifest=_load_json(manifest_path),
        bullish_pullback_run=_load_json(bullish_pullback_run_path),
        lane_a_run=_load_json(lane_a_run_path),
        manifest_path=manifest_path,
        bullish_pullback_run_path=bullish_pullback_run_path,
        lane_a_run_path=lane_a_run_path,
    )
    if write:
        write_outputs(report, output_dir=output_dir, docs_report=docs_report)
    return report


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only exact quote target plan for regular options.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--bullish-pullback-run", type=Path, default=DEFAULT_BULLISH_PULLBACK_RUN)
    parser.add_argument("--lane-a-run", type=Path, default=DEFAULT_LANE_A_RUN)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = run_plan(
        write=not args.no_write,
        output_dir=args.output_dir,
        docs_report=args.docs_report,
        manifest_path=args.manifest,
        bullish_pullback_run_path=args.bullish_pullback_run,
        lane_a_run_path=args.lane_a_run,
    )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
