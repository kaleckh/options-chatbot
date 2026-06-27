from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_momentum_continuation_research_replay"
CONCEPT_ID = "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1"
STRUCTURE = "defined_risk_call_debit_spreads_only"

DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT / "data" / "profitability-lab" / "regular-options-preregistered-momentum-continuation-playbook" / "latest.json"
)
DEFAULT_SELECTOR = (
    ROOT / "data" / "profitability-lab" / "regular-options-preregistered-playbook-readiness-selector" / "latest.json"
)
DEFAULT_ALL_PLANNED = (
    ROOT / "data" / "profitability-lab" / "regular-options-autoresearch" / "all-planned-sleeves" / "latest.json"
)
DEFAULT_GOAL_LOOP = ROOT / "data" / "forward-tracking" / "options_goal_loop_latest.json"
DEFAULT_POINT_IN_TIME_VIX_BUCKET = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
)
DEFAULT_RUNS_DIR = ROOT / "data" / "options-validation" / "runs"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-momentum-continuation-research-replay"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-momentum-continuation-research-replay.md"

PERMITTED_RESEARCH_UNIVERSE = frozenset(
    {"SPY", "QQQ", "IWM", "DIA", "AAPL", "GOOGL", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"}
)
INDEX_BREADTH_CARRIERS = frozenset({"SPY", "QQQ", "IWM", "DIA"})
PROTECTED_HOLDOUT_START = date(2026, 6, 5)
BASE_CLEAN_STACK_TARGET = 157

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_submit_broker_orders",
    "do_not_import_quotes",
    "do_not_mutate_evidence_stores",
    "do_not_consume_protected_holdout",
    "do_not_release_scanner",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_promote_any_lane",
    "do_not_count_historical_rows_as_forward_profitability_proof",
    "do_not_count_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof",
)

MOMENTUM_RUN_TERMS = (
    "momentum",
    "index",
    "qqq",
    "spy",
    "iwm",
    "sleeve_next_index",
    "tracked_winner_cheap_debit_continuity",
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


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, "") or isinstance(value, bool):
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _vix_artifact_ready(payload: dict[str, Any]) -> bool:
    return (
        payload.get("status") == "point_in_time_vix_bucket_ready"
        and _as_list(payload.get("blockers")) == []
        and payload.get("point_in_time_vix_low_mid_bucket_available") is True
    )


def _vix_bucket_index(payload: dict[str, Any]) -> set[str]:
    if not _vix_artifact_ready(payload):
        return set()
    dates: set[str] = set()
    for item in _as_list(payload.get("bucket_rows")):
        row = _as_dict(item)
        if (
            row.get("point_in_time_valid") is True
            and row.get("source_provenance_status") == "trusted_local_or_contract_declared"
            and str(row.get("vix_bucket") or "").lower() in {"low", "mid", "high"}
            and row.get("bucket_date_et")
        ):
            dates.add(str(row["bucket_date_et"]))
    return dates


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
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("run_at")
    meta["report_id"] = payload.get("report_id") or payload.get("playbook")
    return payload, meta


def _source_meta_ok(meta: dict[str, Any]) -> bool:
    return meta.get("status") == "loaded"


def _matches_momentum_run(row: dict[str, Any]) -> bool:
    text = " ".join(
        str(row.get(key) or "")
        for key in ("variant_id", "sleeve_id", "lane_id", "description", "strategy_family", "run_path")
    ).lower()
    return any(term in text for term in MOMENTUM_RUN_TERMS)


def _candidate_run_paths(all_planned: dict[str, Any], runs_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for row in _as_list(all_planned.get("variants")):
        variant = _as_dict(row)
        if not _matches_momentum_run(variant):
            continue
        run_path = variant.get("run_path")
        if not run_path:
            continue
        path = Path(str(run_path))
        if not path.is_absolute():
            path = ROOT / path
        paths.append(path)
    if not paths and runs_dir.exists():
        paths.extend(sorted(runs_dir.glob("*_intraday.json"), key=lambda item: item.stat().st_mtime, reverse=True)[:20])
    deduped: dict[str, Path] = {}
    for path in paths:
        deduped[str(path.resolve())] = path
    return list(deduped.values())


def _variant_lookup(all_planned: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in _as_list(all_planned.get("variants")):
        variant = _as_dict(row)
        run_path = variant.get("run_path")
        if not run_path:
            continue
        path = Path(str(run_path))
        if not path.is_absolute():
            path = ROOT / path
        lookup[str(path.resolve())] = variant
    return lookup


def _has_any_key(row: dict[str, Any], terms: tuple[str, ...]) -> bool:
    lower_terms = tuple(term.lower() for term in terms)
    return any(any(term in key.lower() for term in lower_terms) and row.get(key) not in (None, "") for key in row)


def _selected_spread(row: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(row.get("selected_spread"))


def _long_contract(row: dict[str, Any]) -> Any:
    spread = _selected_spread(row)
    return row.get("long_contract_symbol") or spread.get("long_contract_symbol") or row.get("contract_symbol")


def _short_contract(row: dict[str, Any]) -> Any:
    spread = _selected_spread(row)
    return row.get("short_contract_symbol") or spread.get("short_contract_symbol")


def _is_call_debit_spread(row: dict[str, Any]) -> bool:
    return (
        str(row.get("strategy_type") or "").lower() == "vertical_spread"
        and str(row.get("type") or row.get("option_type") or "").lower() == "call"
        and bool(_long_contract(row))
        and bool(_short_contract(row))
        and _safe_float(row.get("net_debit") or row.get("entry_px") or row.get("entry_spread_ask_bid_debit")) is not None
    )


def _trusted_run(run: dict[str, Any]) -> bool:
    return (
        run.get("truth_source") == "historical_imported"
        and run.get("execution_realism") == "quote_backed_intraday_replay"
        and run.get("imported_data_scope") in (None, "trusted")
    )


def _has_side_aware_entry(row: dict[str, Any]) -> bool:
    return _safe_float(row.get("entry_spread_ask_bid_debit") or row.get("entry_side_aware_debit")) is not None


def _has_side_aware_exit(row: dict[str, Any]) -> bool:
    return _safe_float(row.get("exit_spread_bid_ask_value") or row.get("exit_side_aware_value")) is not None


def _proof_formula() -> dict[str, str]:
    return {
        "entry_debit": "long_call_ask - short_call_bid",
        "exit_value": "long_call_bid - short_call_ask",
        "net_pnl_usd": "(exit_value - entry_debit) * 100 - fees_and_slippage",
        "important_boundary": "existing imported spread marks and midpoint-like marks may be diagnostic, but are not counted as proof unless explicit side-aware OPRA/NBBO bid/ask legs are present",
    }


def _dedupe_key(row: dict[str, Any]) -> str:
    return "|".join(
        str(part or "")
        for part in (
            row.get("ticker"),
            row.get("date") or row.get("entry_date"),
            row.get("exit_date") or row.get("closed_date"),
            _long_contract(row),
            _short_contract(row),
        )
    )


def _row_reasons(
    row: dict[str, Any],
    *,
    run: dict[str, Any],
    seen_keys: set[str],
    vix_bucket_dates: set[str],
) -> list[str]:
    reasons: list[str] = []
    ticker = str(row.get("ticker") or "").upper()
    entry_date = _parse_date(row.get("date") or row.get("entry_date"))
    key = _dedupe_key(row)
    if key in seen_keys:
        reasons.append("duplicate_within_research_harness")
    if entry_date is None:
        reasons.append("missing_entry_date")
    elif entry_date >= PROTECTED_HOLDOUT_START:
        reasons.append("protected_holdout_blocked")
    if ticker not in PERMITTED_RESEARCH_UNIVERSE:
        reasons.append("rejected_outside_preregistered_universe")
    if not _is_call_debit_spread(row):
        reasons.append("rejected_not_call_debit_spread")
    if not _trusted_run(run):
        reasons.append("missing_trusted_intraday_opra_nbbo_run_source")
    if not _has_side_aware_entry(row):
        reasons.append("missing_side_aware_entry_bid_ask")
    if not _has_side_aware_exit(row):
        reasons.append("missing_side_aware_exit_bid_ask")
    if not _has_any_key(row, ("vix",)) and str(row.get("date") or row.get("entry_date") or "")[:10] not in vix_bucket_dates:
        reasons.append("missing_point_in_time_vix_bucket")
    if not _has_any_key(row, ("breadth", "advance_decline", "adv_dec")):
        reasons.append("missing_point_in_time_breadth_confirmation")
    if _safe_float(row.get("spy_ret5")) is None:
        reasons.append("missing_point_in_time_spy_momentum_confirmation")
    if ticker != "QQQ" and _safe_float(row.get("qqq_ret5")) is None and _safe_float(row.get("qqq_ret20")) is None:
        reasons.append("missing_point_in_time_qqq_momentum_confirmation")
    if str(row.get("spread_diagnostics_proof_role") or "").lower() == "diagnostic_only":
        reasons.append("spread_diagnostics_marked_diagnostic_only")
    if str(row.get("long_entry_quote_basis") or "").lower() == "mid" or str(row.get("short_entry_quote_basis") or "").lower() == "mid":
        reasons.append("entry_contains_mid_quote_basis")
    if row.get("net_pnl_usd") in (None, ""):
        reasons.append("missing_net_usd_pnl")
    return sorted(set(reasons))


def _denominator_status(reasons: list[str]) -> str:
    priority = (
        "protected_holdout_blocked",
        "duplicate_within_research_harness",
        "rejected_outside_preregistered_universe",
        "rejected_not_call_debit_spread",
        "missing_trusted_intraday_opra_nbbo_run_source",
        "missing_point_in_time_vix_bucket",
        "missing_point_in_time_breadth_confirmation",
        "missing_point_in_time_spy_momentum_confirmation",
        "missing_point_in_time_qqq_momentum_confirmation",
        "missing_side_aware_entry_bid_ask",
        "missing_side_aware_exit_bid_ask",
        "entry_contains_mid_quote_basis",
        "spread_diagnostics_marked_diagnostic_only",
        "missing_net_usd_pnl",
    )
    for item in priority:
        if item in reasons:
            return item
    return "exact_entry_and_policy_exit_captured"


def _denominator_row(row: dict[str, Any], *, run: dict[str, Any], run_path: Path, seen_keys: set[str], vix_bucket_dates: set[str]) -> dict[str, Any]:
    reasons = _row_reasons(row, run=run, seen_keys=seen_keys, vix_bucket_dates=vix_bucket_dates)
    status = _denominator_status(reasons)
    key = _dedupe_key(row)
    seen_keys.add(key)
    entry_debit = _safe_float(row.get("entry_spread_ask_bid_debit") or row.get("entry_side_aware_debit"))
    exit_value = _safe_float(row.get("exit_spread_bid_ask_value") or row.get("exit_side_aware_value"))
    net_pnl = _safe_float(row.get("net_pnl_usd"))
    diagnostic_net_pnl = net_pnl if net_pnl is not None else None
    return {
        "row_id": key,
        "ticker": str(row.get("ticker") or "").upper(),
        "entry_date": row.get("date") or row.get("entry_date"),
        "exit_date": row.get("exit_date") or row.get("closed_date"),
        "long_contract_symbol": _long_contract(row),
        "short_contract_symbol": _short_contract(row),
        "source_run": _rel(run_path),
        "source_playbook": run.get("playbook"),
        "denominator_status": status,
        "proof_qualified": status == "exact_entry_and_policy_exit_captured",
        "reason_codes": reasons,
        "entry_debit_formula_value": round(entry_debit, 4) if entry_debit is not None else None,
        "exit_value_formula_value": round(exit_value, 4) if exit_value is not None else None,
        "proof_net_pnl_usd": round(net_pnl, 2) if status == "exact_entry_and_policy_exit_captured" and net_pnl is not None else None,
        "diagnostic_net_pnl_usd": round(diagnostic_net_pnl, 2) if diagnostic_net_pnl is not None else None,
        "diagnostic_pnl_pct": _safe_float(row.get("net_pnl_pct") or row.get("pnl_pct")),
        "truth_source": row.get("truth_source") or run.get("truth_source"),
        "execution_realism": row.get("execution_realism") or run.get("execution_realism"),
        "entry_fill_basis": row.get("entry_fill_basis"),
        "exit_fill_basis": row.get("exit_fill_basis"),
        "entry_quote_basis": {
            "long": row.get("long_entry_quote_basis"),
            "short": row.get("short_entry_quote_basis"),
        },
    }


def _load_run_denominator_rows(run_paths: list[Path], *, vix_bucket_dates: set[str] | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rows: list[dict[str, Any]] = []
    metas: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    vix_bucket_dates = vix_bucket_dates or set()
    for path in run_paths:
        run, meta = _load_json(path, required=False)
        meta["trade_count"] = len(_as_list(run.get("trades")))
        meta["unpriced_trade_count"] = len(_as_list(run.get("unpriced_trades")))
        meta["trusted_intraday_source"] = _trusted_run(run) if run else False
        metas.append(meta)
        if meta["status"] != "loaded":
            continue
        for trade in _as_list(run.get("trades")):
            source = _as_dict(trade)
            rows.append(_denominator_row(source, run=run, run_path=path, seen_keys=seen_keys, vix_bucket_dates=vix_bucket_dates))
        for trade in _as_list(run.get("unpriced_trades")):
            source = _as_dict(trade)
            rows.append(_denominator_row(source, run=run, run_path=path, seen_keys=seen_keys, vix_bucket_dates=vix_bucket_dates))
    return rows, metas


def _profit_metrics(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    values = [_safe_float(row.get(field)) for row in rows]
    pnl = [value for value in values if value is not None]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = None
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    elif gross_win > 0:
        profit_factor = float("inf")
    return {
        "row_count": len(rows),
        "priced_row_count": len(pnl),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate_pct": round((len(wins) / len(pnl)) * 100.0, 2) if pnl else None,
        "net_pnl_usd": round(sum(pnl), 2) if pnl else None,
        "avg_pnl_usd": round(sum(pnl) / len(pnl), 2) if pnl else None,
        "gross_win_usd": round(gross_win, 2),
        "gross_loss_usd": round(gross_loss, 2),
        "profit_factor": round(profit_factor, 4) if profit_factor not in (None, float("inf")) else profit_factor,
    }


def _top_blockers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(str(item) for item in _as_list(row.get("reason_codes")))
    return [{"reason": reason, "row_count": count} for reason, count in counts.most_common()]


def _run_level_compatibility(all_planned: dict[str, Any], run_metas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lookup = _variant_lookup(all_planned)
    rows = []
    for meta in run_metas:
        path = Path(str(meta.get("path") or ""))
        abs_key = str((ROOT / path).resolve()) if not path.is_absolute() else str(path.resolve())
        variant = lookup.get(abs_key, {})
        novelty = _as_dict(variant.get("novelty_vs_core_plus_clean_reference"))
        robustness = _as_dict(variant.get("robustness"))
        metrics = _as_dict(variant.get("standalone_metrics"))
        rows.append(
            {
                "run_path": meta.get("path"),
                "variant_id": variant.get("variant_id"),
                "trusted_intraday_source": meta.get("trusted_intraday_source"),
                "exact_trade_count": _safe_int(metrics.get("exact_trade_count") or meta.get("trade_count")),
                "quote_coverage_pct": _safe_float(metrics.get("quote_coverage_pct")),
                "profit_factor": _safe_float(metrics.get("profit_factor")),
                "stress_5pct_per_side_profit_factor": _safe_float(robustness.get("stress_5pct_per_side_profit_factor")),
                "base_clean_trade_count": _safe_int(novelty.get("base_clean_trade_count"), BASE_CLEAN_STACK_TARGET),
                "strict_new_trade_count": _safe_int(novelty.get("strict_new_trade_count")),
                "with_candidate_trade_count": _safe_int(novelty.get("with_candidate_trade_count")),
            }
        )
    return rows


def _goal_state(goal_payload: dict[str, Any], goal_meta: dict[str, Any]) -> dict[str, Any]:
    accounting = _as_dict(goal_payload.get("forward_evidence_accounting"))
    return {
        "artifact_status": goal_meta["status"],
        "current_decision_state": goal_payload.get("current_decision_state"),
        "post_freeze_strict_exact_completed_rows": accounting.get("post_freeze_strict_exact_completed_rows"),
        "minimum_required": accounting.get("minimum_required"),
        "strict_usd_pf_lower_bound_5pct": accounting.get("strict_usd_pf_lower_bound_5pct"),
        "live_entry_allowed": accounting.get("live_entry_allowed"),
        "auto_track_allowed": accounting.get("auto_track_allowed"),
        "broker_order_allowed": accounting.get("broker_order_allowed"),
        "promotion_ready": accounting.get("promotion_ready"),
    }


def _overall_status(proof_rows: list[dict[str, Any]], denominator_rows: list[dict[str, Any]]) -> str:
    if not denominator_rows:
        return "implemented_research_replay_no_denominator_rows"
    if proof_rows:
        return "implemented_research_replay_has_proof_rows_not_forward_proof"
    return "implemented_research_replay_no_proof_qualified_rows"


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    selector_path: Path = DEFAULT_SELECTOR,
    all_planned_path: Path = DEFAULT_ALL_PLANNED,
    goal_loop_path: Path = DEFAULT_GOAL_LOOP,
    point_in_time_vix_bucket_path: Path = DEFAULT_POINT_IN_TIME_VIX_BUCKET,
    runs_dir: Path = DEFAULT_RUNS_DIR,
    run_paths: list[Path] | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    preregistered, preregistered_meta = _load_json(preregistered_playbook_path, required=True)
    selector, selector_meta = _load_json(selector_path, required=True)
    all_planned, all_planned_meta = _load_json(all_planned_path, required=True)
    goal_loop, goal_loop_meta = _load_json(goal_loop_path, required=False)
    point_in_time_vix_bucket, vix_meta = _load_json(point_in_time_vix_bucket_path, required=False)
    vix_bucket_dates = _vix_bucket_index(point_in_time_vix_bucket)
    selected_paths = run_paths if run_paths is not None else _candidate_run_paths(all_planned, runs_dir)
    denominator_rows, run_metas = _load_run_denominator_rows(selected_paths, vix_bucket_dates=vix_bucket_dates)
    proof_rows = [row for row in denominator_rows if row.get("proof_qualified") is True]
    diagnostic_priced = [row for row in denominator_rows if row.get("diagnostic_net_pnl_usd") is not None]
    status_counts = Counter(str(row.get("denominator_status")) for row in denominator_rows)
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _overall_status(proof_rows, denominator_rows),
        **READ_ONLY_FLAGS,
        "research_only_replay_harness_implemented": True,
        "historical_replay_performed": True,
        "lane_implementation_performed": False,
        "scope": "approved_research_only_momentum_continuation_replay_harness",
        "concept_id": CONCEPT_ID,
        "structure": STRUCTURE,
        "operator_approval_record": {
            "approved": True,
            "approval_scope": "one research-only implementation/replay harness only",
            "not_approved": [
                "live validation",
                "auto-track",
                "broker orders",
                "quote import",
                "evidence-store mutation",
                "protected-holdout consumption",
                "scanner release",
                "stop/sizing/proof-bar changes",
                "promotion",
            ],
        },
        "historical_rows_are_not_forward_proof": True,
        "forward_acceptance_target": {
            "profitable_strict_completed_rows_required": 30,
            "current_post_freeze_strict_completed_rows": _goal_state(goal_loop, goal_loop_meta).get(
                "post_freeze_strict_exact_completed_rows"
            ),
            "accepted_profitability": False,
        },
        "proof_formula": _proof_formula(),
        "source_artifacts": {
            "preregistered_playbook": preregistered_meta,
            "readiness_selector": selector_meta,
            "all_planned_sleeves": all_planned_meta,
            "goal_loop": goal_loop_meta,
            "point_in_time_vix_bucket": vix_meta,
            "run_artifacts": run_metas,
        },
        "source_validations": {
            "preregistered_concept_matches": (
                preregistered.get("concept_id") == CONCEPT_ID
                or _as_dict(preregistered.get("concept")).get("concept_id") == CONCEPT_ID
            ),
            "selector_top_candidate_matches": _as_dict(selector.get("top_ranked_candidate")).get("concept_id") == CONCEPT_ID,
            "run_artifact_count": len(run_metas),
            "trusted_intraday_run_artifact_count": sum(1 for item in run_metas if item.get("trusted_intraday_source")),
            "point_in_time_vix_bucket_ready": _vix_artifact_ready(point_in_time_vix_bucket),
            "point_in_time_vix_bucket_date_count": len(vix_bucket_dates),
        },
        "eligible_universe": sorted(PERMITTED_RESEARCH_UNIVERSE),
        "index_breadth_carriers": sorted(INDEX_BREADTH_CARRIERS),
        "denominator": {
            "row_count": len(denominator_rows),
            "status_counts": dict(sorted(status_counts.items())),
            "top_blockers": _top_blockers(denominator_rows),
            "sample_rows": denominator_rows[:50],
        },
        "proof_qualified": {
            "row_count": len(proof_rows),
            "metrics": _profit_metrics(proof_rows, "proof_net_pnl_usd"),
            "rows": proof_rows[:50],
        },
        "diagnostic_only_existing_marks": {
            "row_count": len(diagnostic_priced),
            "metrics": _profit_metrics(diagnostic_priced, "diagnostic_net_pnl_usd"),
            "not_counted_reason": (
                "Existing imported spread marks and midpoint-basis rows are shown to audit what old artifacts imply, "
                "but they are not accepted as proof for this preregistered design without explicit side-aware entry "
                "and exit OPRA/NBBO bid/ask leg evidence plus point-in-time VIX and breadth inputs."
            ),
        },
        "run_level_compatibility": _run_level_compatibility(all_planned, run_metas),
        "next_oracle_question": (
            "Given the approved research-only harness results, choose the next concrete repo task that can move from "
            "0 proof-qualified momentum-continuation rows toward 30 profitable strict forward-audit rows. Prefer a "
            "falsifiable implementation or data-surface repair path that preserves the listed prohibitions. If this "
            "concept is blocked, pivot to the next materially different option edge family rather than stopping."
        ),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("research_only_replay_harness_implemented") is not True:
        raise ValueError("research replay harness must be marked implemented")
    if report.get("lane_implementation_performed") is not False:
        raise ValueError("research harness must not be marked as production lane implementation")
    if report.get("accepted_profitability") is not False:
        raise ValueError("historical research harness cannot accept profitability")
    if report.get("protected_holdout_consumed") is not False:
        raise ValueError("protected holdout cannot be consumed")
    if report.get("broker_order_allowed") is not False:
        raise ValueError("broker orders cannot be allowed")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    denominator = _as_dict(report.get("denominator"))
    proof = _as_dict(report.get("proof_qualified"))
    diagnostic = _as_dict(report.get("diagnostic_only_existing_marks"))
    forward = _as_dict(report.get("forward_acceptance_target"))
    lines = [
        "# Regular Options Momentum Continuation Research Replay",
        "",
        "This report is generated from `scripts/build_regular_options_momentum_continuation_research_replay.py`. It implements the operator-approved research-only replay harness for the preregistered momentum-continuation call-debit-spread concept. It writes derived research artifacts only; it does not enable live validation, auto-track, broker orders, quote import, evidence-store mutation, protected-holdout consumption, scanner release, stop/sizing/proof-bar changes, or promotion.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report['concept_id']}`.",
        f"- Research harness implemented: `{_fmt_bool(report['research_only_replay_harness_implemented'])}`.",
        f"- Historical replay performed: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Forward strict completed rows: `{forward.get('current_post_freeze_strict_completed_rows')}` / `{forward.get('profitable_strict_completed_rows_required')}`.",
        f"- Denominator rows: `{denominator.get('row_count')}`.",
        f"- Proof-qualified rows: `{proof.get('row_count')}`.",
        f"- Diagnostic priced rows: `{diagnostic.get('row_count')}`.",
        "",
        "## Proof Formula",
        "",
    ]
    for key, value in _as_dict(report.get("proof_formula")).items():
        lines.append(f"- `{key}`: {value}.")
    lines.extend(
        [
            "",
            "## Proof Metrics",
            "",
            f"- Proof metrics: `{json.dumps(proof.get('metrics'), sort_keys=True)}`.",
            f"- Diagnostic-only metrics: `{json.dumps(diagnostic.get('metrics'), sort_keys=True)}`.",
            f"- Diagnostic-only boundary: {diagnostic.get('not_counted_reason')}",
            "",
            "## Denominator Status Counts",
            "",
            "| Status | Rows |",
            "| --- | ---: |",
        ]
    )
    for status, count in _as_dict(denominator.get("status_counts")).items():
        lines.append(f"| `{status}` | {count} |")
    lines.extend(["", "## Top Blockers", "", "| Reason | Rows |", "| --- | ---: |"])
    for row in _as_list(denominator.get("top_blockers"))[:20]:
        item = _as_dict(row)
        lines.append(f"| `{item.get('reason')}` | {item.get('row_count')} |")
    lines.extend(
        [
            "",
            "## Run Compatibility",
            "",
            "| Run | Variant | Trusted | Exact | Strict New | PF | Stress PF | Coverage |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in _as_list(report.get("run_level_compatibility"))[:30]:
        item = _as_dict(row)
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{item.get('run_path')}`",
                    f"`{item.get('variant_id')}`",
                    f"`{_fmt_bool(item.get('trusted_intraday_source'))}`",
                    str(item.get("exact_trade_count")),
                    str(item.get("strict_new_trade_count")),
                    str(item.get("profit_factor")),
                    str(item.get("stress_5pct_per_side_profit_factor")),
                    str(item.get("quote_coverage_pct")),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Next Oracle Question",
            "",
            report["next_oracle_question"],
            "",
            "## Forbidden Actions",
            "",
        ]
    )
    lines.extend(f"- `{action}`" for action in _as_list(report.get("forbidden_actions")))
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
    parser = argparse.ArgumentParser(description="Build the approved research-only momentum continuation replay harness.")
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--selector", type=Path, default=DEFAULT_SELECTOR)
    parser.add_argument("--all-planned", type=Path, default=DEFAULT_ALL_PLANNED)
    parser.add_argument("--goal-loop", type=Path, default=DEFAULT_GOAL_LOOP)
    parser.add_argument("--point-in-time-vix-bucket", type=Path, default=DEFAULT_POINT_IN_TIME_VIX_BUCKET)
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--run", action="append", type=Path, dest="run_paths", default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        preregistered_playbook_path=args.preregistered_playbook,
        selector_path=args.selector,
        all_planned_path=args.all_planned,
        goal_loop_path=args.goal_loop,
        point_in_time_vix_bucket_path=args.point_in_time_vix_bucket,
        runs_dir=args.runs_dir,
        run_paths=args.run_paths,
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
