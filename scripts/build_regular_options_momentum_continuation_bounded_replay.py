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


REPORT_ID = "regular_options_momentum_continuation_bounded_replay"
CONCEPT_ID = "breadth_confirmed_index_qqq_momentum_continuation_debit_spread_v1"
EXPECTED_STRUCTURE = "defined_risk_call_debit_spreads_only"

DEFAULT_SELECTOR = (
    ROOT / "data" / "profitability-lab" / "regular-options-preregistered-playbook-readiness-selector" / "latest.json"
)
DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT / "data" / "profitability-lab" / "regular-options-preregistered-momentum-continuation-playbook" / "latest.json"
)
DEFAULT_SOURCE_REPLAY = (
    ROOT / "data" / "profitability-lab" / "regular-options-momentum-continuation-research-replay" / "latest.json"
)
DEFAULT_PROOF_BLOCKER_RESOLUTION = (
    ROOT / "data" / "profitability-lab" / "regular-options-momentum-continuation-proof-blocker-resolution" / "latest.json"
)
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_CLEAN_BASE_STACK = ROOT / "data" / "profitability-lab" / "regular-options-historical-walk-forward" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-momentum-continuation-bounded-replay"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-momentum-continuation-bounded-replay.md"

CONTRACT_MULTIPLIER = 100
MIN_HISTORICAL_EXACT_ROWS = 200
MIN_LATEST_AUDIT_EXACT_ROWS = 30
MIN_QUOTE_COVERAGE = 0.90
MIN_PF_LOWER_BOUND = 1.0
MIN_STRESS_PF = 1.0
PROTECTED_HOLDOUT_FALLBACK = "2026-06-05"

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "lane_implementation_performed": False,
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
    "do_not_return_or_reimplement_momentum_research_replay",
    "do_not_return_or_reimplement_momentum_proof_blocker_resolution",
    "do_not_create_trades",
    "do_not_prepare_or_submit_broker_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_run_or_change_production_scanners",
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
    "do_not_claim_accepted_profitability",
    "do_not_count_historical_rows_as_forward_proof",
    "do_not_count_source_marks_midpoints_eod_display_manual_last_synthetic_or_lookahead_as_proof",
)

REQUIRED_DENOMINATOR_STATUSES = (
    "no_candidate",
    "rejected_no_trend_confirmation",
    "rejected_no_breadth_confirmation",
    "rejected_vix_bucket",
    "rejected_width_or_liquidity",
    "missing_leg_quote",
    "zero_bid_or_untradable",
    "exact_entry_captured",
    "open_waiting_policy_exit_or_expiry",
    "exact_exit_captured",
    "expired_settled_exact",
    "missing_exit",
    "protected_holdout_blocked",
    "malformed_candidate",
    "duplicate_strict_new_identity",
    "replay_gate_blocked",
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
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


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
    meta["report_id"] = payload.get("report_id")
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["source_status"] = payload.get("status")
    return payload, meta


def _load_rows(path: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if path is None:
        return [], {"path": None, "required": False, "exists": False, "status": "not_requested", "row_count": 0}
    meta = {"path": _rel(path), "required": False, "exists": path.exists(), "status": "missing", "row_count": 0, "malformed_rows": 0}
    if not path.exists():
        return [], meta
    text = path.read_text(encoding="utf8").strip()
    if not text:
        meta["status"] = "loaded"
        return [], meta
    rows: list[dict[str, Any]] = []
    malformed = 0
    try:
        if text.startswith("["):
            payload = json.loads(text)
            if isinstance(payload, list):
                rows = [row for row in payload if isinstance(row, dict)]
                malformed = len(payload) - len(rows)
            else:
                malformed = 1
        else:
            for line in text.splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    malformed += 1
    except json.JSONDecodeError:
        malformed += 1
    meta["status"] = "loaded" if malformed == 0 else "loaded_with_malformed_rows"
    meta["row_count"] = len(rows)
    meta["malformed_rows"] = malformed
    return rows, meta


def _protected_holdout_start(holdout: dict[str, Any]) -> str:
    return str(
        holdout.get("protected_holdout_start")
        or _as_dict(holdout.get("protected_range")).get("start_date")
        or PROTECTED_HOLDOUT_FALLBACK
    )


def _selector_valid(selector: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    inventory_matches = [
        row
        for row in _as_list(selector.get("design_inventory"))
        if isinstance(row, dict) and row.get("concept_id") == CONCEPT_ID
    ]
    if not inventory_matches:
        reasons.append("selector_inventory_missing_momentum_continuation")
    return not reasons, reasons


def _preregistration_valid(playbook: dict[str, Any]) -> tuple[bool, list[str]]:
    concept = _as_dict(playbook.get("concept"))
    reasons: list[str] = []
    if (playbook.get("concept_id") or concept.get("concept_id")) != CONCEPT_ID:
        reasons.append("unexpected_concept_id")
    if playbook.get("status") != "preregistered_design_only":
        reasons.append("unexpected_status")
    if (playbook.get("structure") or concept.get("structure")) != EXPECTED_STRUCTURE:
        reasons.append("unexpected_structure")
    if playbook.get("accepted_profitability") is not False:
        reasons.append("accepted_profitability_not_false")
    return not reasons, reasons


def _strict_new_identity(row: dict[str, Any]) -> str:
    ticker = str(row.get("ticker") or row.get("underlying") or "").upper().strip()
    entry = str(row.get("entry_date") or row.get("selection_date") or row.get("date") or "").strip()
    expiration = str(row.get("expiration") or row.get("expiry") or "").strip()
    long_leg = str(row.get("long_call_contract") or row.get("long_contract_symbol") or row.get("contract_symbol") or row.get("long_call_strike") or "").strip()
    short_leg = str(row.get("short_call_contract") or row.get("short_contract_symbol") or row.get("short_call_strike") or "").strip()
    basis = str(row.get("quote_basis") or row.get("entry_quote_basis") or "trusted_opra_nbbo_bid_ask").strip()
    if not ticker or not entry:
        return ""
    return "|".join([CONCEPT_ID, ticker, entry, expiration, long_leg, short_leg, basis])


def _base_stack_identity_set(base_stack: dict[str, Any]) -> set[str]:
    identities: set[str] = set()
    for key in ("rows", "selected_rows", "clean_rows", "replay_rows", "trades"):
        for row in _as_list(base_stack.get(key)):
            if isinstance(row, dict):
                identity = _strict_new_identity(row)
                if identity:
                    identities.add(identity)
    return identities


def _fixture_status(row: dict[str, Any], *, protected_start: str, seen: set[str], base_identities: set[str]) -> tuple[str, list[str], float | None]:
    blockers: list[str] = []
    identity = _strict_new_identity(row)
    entry_date = _parse_date(row.get("entry_date") or row.get("selection_date") or row.get("date"))
    holdout_date = _parse_date(protected_start)
    if row.get("candidate") is False:
        return "no_candidate", ["no_candidate"], None
    if identity and (identity in seen or identity in base_identities):
        return "duplicate_strict_new_identity", ["duplicate_strict_new_identity"], None
    if entry_date is None:
        blockers.append("missing_entry_date")
    elif holdout_date is not None and entry_date >= holdout_date:
        return "protected_holdout_blocked", ["protected_holdout_blocked"], None
    if row.get("trend_confirmed") is False:
        return "rejected_no_trend_confirmation", ["rejected_no_trend_confirmation"], None
    if row.get("breadth_confirmed") is False:
        return "rejected_no_breadth_confirmation", ["rejected_no_breadth_confirmation"], None
    if str(row.get("vix_bucket") or "").lower() not in {"low", "mid", "low_mid", "low-mid"}:
        return "rejected_vix_bucket", ["rejected_vix_bucket"], None
    long_strike = _safe_float(row.get("long_call_strike"))
    short_strike = _safe_float(row.get("short_call_strike"))
    if long_strike is not None and short_strike is not None and long_strike >= short_strike:
        return "malformed_candidate", ["long_call_strike_must_be_below_short_call_strike"], None
    width = short_strike - long_strike if long_strike is not None and short_strike is not None else None
    if width is not None and width <= 0:
        return "rejected_width_or_liquidity", ["nonpositive_width"], None
    entry_long_ask = _safe_float(_first_present(row, "long_call_ask", "entry_long_call_ask"))
    entry_short_bid = _safe_float(_first_present(row, "short_call_bid", "entry_short_call_bid"))
    exit_long_bid = _safe_float(_first_present(row, "long_call_bid_exit", "exit_long_call_bid"))
    exit_short_ask = _safe_float(_first_present(row, "short_call_ask_exit", "exit_short_call_ask"))
    if entry_long_ask is None or entry_short_bid is None:
        return "missing_leg_quote", ["missing_entry_leg_quote"], None
    if entry_long_ask <= 0 or entry_short_bid <= 0:
        return "zero_bid_or_untradable", ["entry_zero_bid_or_untradable"], None
    entry_debit = entry_long_ask - entry_short_bid
    if entry_debit <= 0:
        return "rejected_width_or_liquidity", ["entry_debit_nonpositive"], None
    if row.get("open_waiting_policy_exit") is True:
        return "open_waiting_policy_exit_or_expiry", ["open_waiting_policy_exit_or_expiry"], None
    fees = _safe_float(row.get("fees_usd")) or 0.0
    slippage = _safe_float(row.get("slippage_usd")) or 0.0
    if exit_long_bid is not None and exit_short_ask is not None:
        if exit_long_bid <= 0 or exit_short_ask < 0:
            return "zero_bid_or_untradable", ["exit_zero_bid_or_untradable"], None
        exit_value = exit_long_bid - exit_short_ask
        net = (exit_value - entry_debit) * CONTRACT_MULTIPLIER - fees - slippage
        return "exact_exit_captured", [], net
    underlying_expiry = _safe_float(row.get("underlying_expiry_price"))
    if underlying_expiry is not None and long_strike is not None and short_strike is not None:
        settlement_value = max(underlying_expiry - long_strike, 0.0) - max(underlying_expiry - short_strike, 0.0)
        net = (settlement_value - entry_debit) * CONTRACT_MULTIPLIER - fees - slippage
        return "expired_settled_exact", [], net
    if row.get("entry_only") is True:
        return "exact_entry_captured", ["entry_captured_without_exit"], None
    return "missing_exit", ["missing_policy_exit_quote_or_expiry_settlement"], None


def _classify_fixture_rows(rows: list[dict[str, Any]], *, protected_start: str, base_identities: set[str]) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        identity = _strict_new_identity(row)
        status, blockers, net = _fixture_status(row, protected_start=protected_start, seen=seen, base_identities=base_identities)
        if identity:
            seen.add(identity)
        classified.append(
            {
                "row_number": index,
                "strict_new_identity": identity,
                "ticker": str(row.get("ticker") or row.get("underlying") or "").upper(),
                "entry_date": row.get("entry_date") or row.get("selection_date") or row.get("date"),
                "expiration": row.get("expiration") or row.get("expiry"),
                "denominator_status": status,
                "blockers": blockers,
                "net_pnl_usd": round(net, 2) if net is not None else None,
            }
        )
    return classified


def _profit_metrics(rows: list[dict[str, Any]], *, field: str = "net_pnl_usd") -> dict[str, Any]:
    values = [_safe_float(row.get(field)) for row in rows]
    pnl = [value for value in values if value is not None]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else None)
    return {
        "row_count": len(rows),
        "priced_row_count": len(pnl),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate_pct": round((len(wins) / len(pnl)) * 100.0, 2) if pnl else None,
        "net_pnl_usd": round(sum(pnl), 2) if pnl else None,
        "avg_pnl_usd": round(sum(pnl) / len(pnl), 2) if pnl else None,
        "gross_profit_usd": round(gross_profit, 2),
        "gross_loss_usd": round(gross_loss, 2),
        "profit_factor": round(pf, 4) if pf not in (None, float("inf")) else pf,
        "bootstrap_pf_lower_bound_5pct": None,
        "stress_pf": round(pf, 4) if pf not in (None, float("inf")) else pf,
    }


def _fixture_metrics(rows: list[dict[str, Any]], blockers: list[str]) -> dict[str, Any]:
    exact = [row for row in rows if row.get("denominator_status") in {"exact_exit_captured", "expired_settled_exact"}]
    status_counts = Counter(str(row.get("denominator_status")) for row in rows)
    profit = _profit_metrics(exact)
    return {
        "total_denominator_rows": len(rows),
        "denominator_counts": dict(sorted(status_counts.items())),
        "exact_completed_rows": len(exact),
        "strict_new_exact_completed_rows": sum(1 for row in exact if row.get("strict_new_identity")),
        "minimum_historical_exact_rows": MIN_HISTORICAL_EXACT_ROWS,
        "latest_audit_30_row_bar_met": len(exact) >= MIN_LATEST_AUDIT_EXACT_ROWS,
        "quote_coverage": round(len(exact) / len(rows), 4) if rows else 0.0,
        "unpriced_count": len(rows) - len(exact),
        "replay_gate_blocker_count": len(blockers),
        **profit,
    }


def _resolution_metrics(source_replay: dict[str, Any], resolution: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    counts = _as_dict(resolution.get("resolution_counts"))
    strict_metrics = _as_dict(resolution.get("strict_research_metrics"))
    side_aware_metrics = _as_dict(resolution.get("side_aware_diagnostic_metrics"))
    old_mark_metrics = _as_dict(_as_dict(source_replay.get("diagnostic_only_existing_marks")).get("metrics"))
    denominator_rows = _safe_float(source_replay.get("source_denominator_rows")) or _safe_float(_as_dict(source_replay.get("denominator")).get("row_count")) or 0
    proof_rows = _safe_float(resolution.get("proof_qualified_rows_after_resolution")) or 0
    side_rows = _safe_float(counts.get("side_aware_quotes_resolved")) or 0
    return {
        "total_denominator_rows": int(denominator_rows),
        "exact_completed_rows": int(proof_rows),
        "strict_new_exact_completed_rows": int(proof_rows),
        "minimum_historical_exact_rows": MIN_HISTORICAL_EXACT_ROWS,
        "latest_audit_30_row_bar_met": int(proof_rows) >= MIN_LATEST_AUDIT_EXACT_ROWS,
        "quote_coverage": round(side_rows / denominator_rows, 4) if denominator_rows else 0.0,
        "point_in_time_inputs_resolved": counts.get("point_in_time_inputs_resolved"),
        "side_aware_quotes_resolved": counts.get("side_aware_quotes_resolved"),
        "proof_qualified_rows_after_resolution": resolution.get("proof_qualified_rows_after_resolution"),
        "blocker_counts": counts.get("blocker_counts") or {},
        "strict_research_metrics": strict_metrics,
        "side_aware_diagnostic_metrics": side_aware_metrics,
        "old_mark_diagnostic_metrics": old_mark_metrics,
        "replay_gate_blocker_count": len(blockers),
    }


def _source_replay_valid(source_replay: dict[str, Any]) -> bool:
    return (
        source_replay.get("concept_id") == CONCEPT_ID
        and source_replay.get("research_only_replay_harness_implemented") is True
        and source_replay.get("accepted_profitability") is False
    )


def _resolution_valid(resolution: dict[str, Any]) -> bool:
    return (
        resolution.get("concept_id") == CONCEPT_ID
        and resolution.get("accepted_profitability") is False
        and resolution.get("historical_rows_are_forward_proof") is False
    )


def _status_from_metrics(metrics: dict[str, Any], blockers: list[str]) -> str:
    if blockers:
        return "blocked_momentum_continuation_bounded_replay"
    exact = int(metrics.get("strict_new_exact_completed_rows") or 0)
    quote_coverage = _safe_float(metrics.get("quote_coverage")) or 0.0
    strict_metrics = _as_dict(metrics.get("strict_research_metrics"))
    net = _safe_float(metrics.get("net_pnl_usd")) if "net_pnl_usd" in metrics else _safe_float(strict_metrics.get("net_pnl_usd"))
    pf = _safe_float(metrics.get("profit_factor")) if "profit_factor" in metrics else _safe_float(strict_metrics.get("profit_factor"))
    pf_lb = _safe_float(metrics.get("bootstrap_pf_lower_bound_5pct")) if "bootstrap_pf_lower_bound_5pct" in metrics else _safe_float(strict_metrics.get("bootstrap_pf_lower_bound_5pct"))
    stress = _safe_float(metrics.get("stress_pf")) if "stress_pf" in metrics else _safe_float(strict_metrics.get("stress_pf"))
    if (
        exact >= MIN_HISTORICAL_EXACT_ROWS
        and exact >= MIN_LATEST_AUDIT_EXACT_ROWS
        and quote_coverage >= MIN_QUOTE_COVERAGE
        and net is not None
        and net > 0
        and pf is not None
        and pf > 1.0
        and pf_lb is not None
        and pf_lb > MIN_PF_LOWER_BOUND
        and stress is not None
        and stress >= MIN_STRESS_PF
    ):
        return "momentum_continuation_replay_candidate_for_review_not_forward_proof"
    return "rejected_momentum_continuation_bounded_replay"


def build_report(
    *,
    selector_path: Path = DEFAULT_SELECTOR,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    source_replay_path: Path = DEFAULT_SOURCE_REPLAY,
    proof_blocker_resolution_path: Path = DEFAULT_PROOF_BLOCKER_RESOLUTION,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    clean_base_stack_path: Path = DEFAULT_CLEAN_BASE_STACK,
    fixture_candidates_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    selector, selector_meta = _load_json(selector_path, required=True)
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    source_replay, source_replay_meta = _load_json(source_replay_path, required=True)
    resolution, resolution_meta = _load_json(proof_blocker_resolution_path, required=True)
    holdout, holdout_meta = _load_json(holdout_contract_path, required=True)
    clean_base_stack, clean_base_meta = _load_json(clean_base_stack_path, required=False)
    fixture_rows, fixture_meta = _load_rows(fixture_candidates_path)

    blockers: list[str] = []
    selector_ok, selector_reasons = _selector_valid(selector) if selector_meta["status"] == "loaded" else (False, ["missing_readiness_selector"])
    prereg_ok, prereg_reasons = _preregistration_valid(playbook) if playbook_meta["status"] == "loaded" else (False, ["missing_preregistration_artifact"])
    if not selector_ok:
        blockers.extend(selector_reasons)
    if not prereg_ok:
        blockers.extend(prereg_reasons)
    if source_replay_meta["status"] != "loaded" or not _source_replay_valid(source_replay):
        blockers.append("missing_or_invalid_momentum_research_replay")
    if resolution_meta["status"] != "loaded" or not _resolution_valid(resolution):
        blockers.append("missing_or_invalid_momentum_proof_blocker_resolution")
    elif resolution.get("status") != "momentum_continuation_proof_candidate_for_review_not_forward_proof":
        blockers.extend(str(item) for item in _as_list(resolution.get("blockers")) if item)
    blockers = sorted(set(blockers))

    protected_start = _protected_holdout_start(holdout)
    base_identities = _base_stack_identity_set(clean_base_stack)
    replay_rows: list[dict[str, Any]] = []
    historical_replay_performed = False
    existing_resolution_consumed = False
    if fixture_rows and not blockers:
        replay_rows = _classify_fixture_rows(fixture_rows, protected_start=protected_start, base_identities=base_identities)
        metrics = _fixture_metrics(replay_rows, blockers)
        historical_replay_performed = True
    elif fixture_rows and blockers:
        replay_rows = [{"denominator_status": "replay_gate_blocked", "blockers": blockers, "source_rows_not_replayed": len(fixture_rows)}]
        metrics = _fixture_metrics(replay_rows, blockers)
    else:
        metrics = _resolution_metrics(source_replay, resolution, blockers)
        existing_resolution_consumed = resolution_meta["status"] == "loaded"

    status = _status_from_metrics(metrics, blockers)
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **{**READ_ONLY_FLAGS, "historical_replay_performed": historical_replay_performed},
        "existing_resolution_consumed": existing_resolution_consumed,
        "scope": "read_only_momentum_continuation_bounded_replay_gate",
        "concept_id": CONCEPT_ID,
        "structure": EXPECTED_STRUCTURE,
        "protected_holdout_start": protected_start,
        "research_universe": sorted(_as_list(_as_dict(playbook.get("concept")).get("permitted_research_universe")) or []),
        "proof_formula": {
            "entry_debit": "long_call_ask - short_call_bid",
            "exit_value": "long_call_bid - short_call_ask",
            "expiry_settlement_value": "max(underlying_expiry_price - long_call_strike, 0) - max(underlying_expiry_price - short_call_strike, 0)",
            "net_pnl_usd": "(exit_value_or_settlement - entry_debit) * 100 - fees/slippage",
        },
        "replay_gate_blockers": blockers,
        "denominator_statuses": list(REQUIRED_DENOMINATOR_STATUSES),
        "replay_rows": replay_rows[:100],
        "metrics": metrics,
        "source_artifacts": {
            "readiness_selector": selector_meta,
            "preregistered_momentum_playbook": playbook_meta,
            "momentum_research_replay": source_replay_meta,
            "momentum_proof_blocker_resolution": resolution_meta,
            "forward_holdout_contract": holdout_meta,
            "historical_clean_base_stack": clean_base_meta,
            "fixture_candidates": fixture_meta,
        },
        "validations": {
            "selector_valid": selector_ok,
            "selector_reasons": selector_reasons,
            "preregistration_valid": prereg_ok,
            "preregistration_reasons": prereg_reasons,
            "source_replay_valid": _source_replay_valid(source_replay) if source_replay else False,
            "proof_blocker_resolution_valid": _resolution_valid(resolution) if resolution else False,
        },
        "historical_rows_are_forward_proof": False,
        "accepted_profitability_reason": "blocked until strict exact point-in-time rows clear the replay gate and then produce fresh forward proof",
        "next_oracle_instruction": (
            "Return this bounded replay result to the same GPT-5.5 Pro session. If blockers remain, do not repeat this "
            "momentum bounded replay or its prior proof-blocker resolution unless a new point-in-time breadth/momentum input "
            "surface or explicit approved data repair changes the blocker. Select the next materially different, "
            "falsifiable branch that can move toward at least 30 profitable strict completed forward-audit rows."
        ),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if key == "historical_replay_performed":
            continue
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("concept_id") != CONCEPT_ID:
        raise ValueError("wrong concept")
    for status in REQUIRED_DENOMINATOR_STATUSES:
        if status not in report.get("denominator_statuses", []):
            raise ValueError(f"missing denominator status {status}")
    if report.get("historical_rows_are_forward_proof") is not False:
        raise ValueError("historical rows cannot become forward proof")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    metrics = _as_dict(report.get("metrics"))
    side_metrics = _as_dict(metrics.get("side_aware_diagnostic_metrics"))
    old_metrics = _as_dict(metrics.get("old_mark_diagnostic_metrics"))
    strict_metrics = _as_dict(metrics.get("strict_research_metrics"))
    lines = [
        "# Regular Options Momentum Continuation Bounded Replay",
        "",
        "This generated report is read-only. It gates the bounded momentum-continuation replay behind the preregistered design inventory, the prior research replay, the proof-blocker resolution audit, strict-new accounting, and protected-holdout checks.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report['concept_id']}`.",
        f"- Historical replay performed in this gate: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Existing proof-blocker resolution consumed: `{_fmt_bool(report['existing_resolution_consumed'])}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical rows are forward proof: `{_fmt_bool(report['historical_rows_are_forward_proof'])}`.",
        f"- Strict exact rows: `{metrics.get('strict_new_exact_completed_rows')}`.",
        f"- Quote coverage: `{metrics.get('quote_coverage')}`.",
        "",
        "## Replay Gate Blockers",
        "",
    ]
    if report.get("replay_gate_blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("replay_gate_blockers")))
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Metrics",
            "",
            f"- Total denominator rows: `{metrics.get('total_denominator_rows')}`.",
            f"- Exact completed rows: `{metrics.get('exact_completed_rows')}`.",
            f"- Side-aware diagnostic rows: `{metrics.get('side_aware_quotes_resolved')}`.",
            f"- Side-aware diagnostic metrics: `{json.dumps(side_metrics, sort_keys=True)}`.",
            f"- Strict research metrics: `{json.dumps(strict_metrics, sort_keys=True)}`.",
            f"- Old-mark diagnostic metrics: `{json.dumps(old_metrics, sort_keys=True)}`.",
            "",
            "Historical positive diagnostics are not accepted profitability. They are only evidence for the next GPT-5.5 Pro branch decision because strict point-in-time inputs and forward proof remain missing.",
            "",
            "## Next Oracle Instruction",
            "",
            report["next_oracle_instruction"],
            "",
            "## Forbidden Actions",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
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
    parser = argparse.ArgumentParser(description="Run the read-only momentum-continuation bounded replay gate.")
    parser.add_argument("--selector", type=Path, default=DEFAULT_SELECTOR)
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--source-replay", type=Path, default=DEFAULT_SOURCE_REPLAY)
    parser.add_argument("--proof-blocker-resolution", type=Path, default=DEFAULT_PROOF_BLOCKER_RESOLUTION)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--clean-base-stack", type=Path, default=DEFAULT_CLEAN_BASE_STACK)
    parser.add_argument("--fixture-candidates", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = build_report(
        selector_path=args.selector,
        preregistered_playbook_path=args.preregistered_playbook,
        source_replay_path=args.source_replay,
        proof_blocker_resolution_path=args.proof_blocker_resolution,
        holdout_contract_path=args.holdout_contract,
        clean_base_stack_path=args.clean_base_stack,
        fixture_candidates_path=args.fixture_candidates,
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
