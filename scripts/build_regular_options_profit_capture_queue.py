from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-profit-capture-queue"
DEFAULT_DOC = ROOT / "docs" / "regular-options-profit-capture-queue.md"
DEFAULT_SYMBOL_SLEEVES = ROOT / "data" / "profitability-lab" / "regular-options-symbol-sleeves" / "latest.json"
DEFAULT_CURRENT_POLICY = ROOT / "data" / "forward-tracking" / "current_policy_historical_picks_latest.json"
DEFAULT_GUARDRAIL_STARVATION = ROOT / "data" / "forward-tracking" / "regular_guardrail_starvation_latest.json"

TRUSTED_EXACT = "trusted_intraday_opra_nbbo_exact"
TIER_A = "tier_a_clean_exact_capture"
TIER_B = "tier_b_profitable_watch_repair"
TIER_C = "tier_c_fresh_scan_signature_match"
TIER_BLOCKED = "blocked_but_interesting"
TIER_QUARANTINE = "quarantine_do_not_chase"
TIER_A_MIN_EXACT_TRADES = 10
TIER_A_MIN_QUOTE_COVERAGE = 97.5
TIER_A_MIN_PROFIT_FACTOR = 1.5

READINESS_PAPER_REVIEW = "paper_review_candidate"
READINESS_WATCH_REPAIR = "watch_repair_only"
READINESS_FRESH_SIGNATURE = "historical_signature_only"
READINESS_BLOCKED = "blocked_guardrail_only"
READINESS_DO_NOT_CHASE = "do_not_chase"

DISQUALIFYING_CLEAN_REASONS = {
    "sample_status:thin",
    "trading_desk_guardrail_negative_concentration",
    "zero_bid_exit_rate_above_2",
    "unresolved_rows_remain",
    "quote_coverage_below_97_5",
    "adequate_negative_exact_intraday_evidence",
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(_safe_float(value), digits)


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"missing": True, "path": str(path)}
    payload = json.loads(path.read_text(encoding="utf8"))
    if isinstance(payload, dict):
        payload.setdefault("path", str(path))
        return payload
    return {"missing": True, "path": str(path), "error": "json_root_not_object"}


def _generated_at(payload: dict[str, Any]) -> str | None:
    for key in ("generated_at_utc", "generated_at", "run_at", "created_at"):
        if payload.get(key):
            return str(payload.get(key))
    return None


def input_manifest_entry(path: Path, source_type: str) -> dict[str, Any]:
    entry = {
        "source_type": source_type,
        "path": _rel(path),
        "exists": path.exists(),
        "generated_at": None,
        "status": "missing",
    }
    if not path.exists():
        return entry
    try:
        payload = _load_json(path)
    except Exception as exc:
        entry["status"] = f"unreadable:{exc}"
        return entry
    entry["generated_at"] = _generated_at(payload)
    entry["status"] = "ok"
    return entry


def _median(values: list[float]) -> float | None:
    return round(median(values), 2) if values else None


def _pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round((numerator / denominator) * 100.0, 2)


def current_policy_by_symbol_lane(payload: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for row in payload.get("rows") or []:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("ticker") or "").upper()
        lane = str(row.get("lane") or "")
        if not symbol or not lane:
            continue
        key = (symbol, lane)
        bucket = buckets.setdefault(
            key,
            {
                "symbol": symbol,
                "lane": lane,
                "rows": 0,
                "priced": 0,
                "decision_counts": Counter(),
                "guardrail_hit_counts": Counter(),
                "_pnls": [],
            },
        )
        bucket["rows"] += 1
        decision = str(row.get("current_policy_decision") or "unknown")
        bucket["decision_counts"][decision] += 1
        for hit in row.get("guardrail_hits") or []:
            bucket["guardrail_hit_counts"][str(hit)] += 1
        pnl = row.get("pnl_pct")
        if pnl is not None:
            parsed = _safe_float(pnl)
            bucket["priced"] += 1
            bucket["_pnls"].append(parsed)
    finalized: dict[tuple[str, str], dict[str, Any]] = {}
    for key, bucket in buckets.items():
        pnls = list(bucket.pop("_pnls"))
        negatives = sum(1 for value in pnls if value < 0)
        deep_losses = sum(1 for value in pnls if value <= -50)
        near_total_losses = sum(1 for value in pnls if value <= -90)
        gross_win = round(sum(value for value in pnls if value > 0), 2)
        gross_loss = round(abs(sum(value for value in pnls if value < 0)), 2)
        if gross_loss > 0:
            profit_factor = round(gross_win / gross_loss, 2)
        elif gross_win > 0:
            profit_factor = gross_win
        else:
            profit_factor = 0.0
        finalized[key] = {
            **bucket,
            "avg_pnl_pct": round(sum(pnls) / len(pnls), 2) if pnls else None,
            "median_pnl_pct": _median(pnls),
            "negative_count": negatives,
            "negative_rate_pct": _pct(negatives, len(pnls)),
            "deep_loss_count": deep_losses,
            "near_total_loss_count": near_total_losses,
            "gross_win_pct": gross_win,
            "gross_loss_pct": gross_loss,
            "profit_factor": profit_factor,
            "win_rate_pct": _pct(sum(1 for value in pnls if value > 0), len(pnls)),
            "decision_counts": dict(bucket["decision_counts"]),
            "guardrail_hit_counts": dict(bucket["guardrail_hit_counts"]),
        }
    return finalized


def current_policy_capture_rows(
    current_policy_index: dict[tuple[str, str], dict[str, Any]],
    existing_keys: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for (symbol, lane), bucket in current_policy_index.items():
        if (symbol, lane) in existing_keys:
            continue
        priced = _safe_int(bucket.get("priced"))
        avg_pnl = _safe_float(bucket.get("avg_pnl_pct"))
        if priced <= 0 or avg_pnl <= 0:
            continue
        decision_counts = bucket.get("decision_counts") if isinstance(bucket.get("decision_counts"), dict) else {}
        would_take = _safe_int(decision_counts.get("would_take_today"))
        if would_take <= 0:
            continue
        reason_codes = ["current_policy_historical_paper_only"]
        if priced < 10:
            reason_codes.append("sample_status:thin")
        if _safe_int(bucket.get("deep_loss_count")):
            reason_codes.append("current_policy_deep_losses_remain")
        rows.append(
            {
                "symbol": symbol,
                "lane_id": lane,
                "lane_family": lane,
                "status": "watch",
                "evidence_class": "current_policy_historical_paper_realized",
                "sample_status": "adequate" if priced >= 10 else "thin",
                "reason_codes": reason_codes,
                "status_reason": "; ".join(reason_codes),
                "next_step": (
                    "Use as current-policy paper capture evidence; convert into clean proof only through "
                    "trusted exact-contract proof gates and fresh forward validation."
                ),
                "metrics": {
                    "exact_trusted_priced_trades": priced,
                    "candidates": _safe_int(bucket.get("rows")),
                    "unresolved_rows": 0,
                    "quote_coverage": 100.0,
                    "profit_factor": _round(bucket.get("profit_factor")),
                    "avg_pnl": _round(bucket.get("avg_pnl_pct")),
                    "median_pnl": _round(bucket.get("median_pnl_pct")),
                    "win_rate": _round(bucket.get("win_rate_pct")),
                },
                "current_policy_generated": True,
            }
        )
    return rows


def _lane_matches(playbook_id: str, row: dict[str, Any]) -> bool:
    playbook = playbook_id.lower()
    lane_id = str(row.get("lane_id") or "").lower()
    family = str(row.get("lane_family") or "").lower()
    return playbook == lane_id or playbook == family or playbook in lane_id or playbook in family


def _profitable(row: dict[str, Any]) -> bool:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    return (
        _safe_int(metrics.get("exact_trusted_priced_trades")) > 0
        and _safe_float(metrics.get("avg_pnl")) > 0
        and _safe_float(metrics.get("profit_factor")) > 1.0
    )


def classify_capture_tier(row: dict[str, Any]) -> str | None:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    status = str(row.get("status") or "")
    evidence_class = str(row.get("evidence_class") or "")
    exact = _safe_int(metrics.get("exact_trusted_priced_trades"))
    unresolved = _safe_int(metrics.get("unresolved_rows"))
    coverage = _safe_float(metrics.get("quote_coverage"))
    profit_factor = _safe_float(metrics.get("profit_factor"))
    avg_pnl = _safe_float(metrics.get("avg_pnl"))
    reason_codes = set(row.get("reason_codes") or [])

    if status in {"quarantine", "rejected"}:
        return TIER_QUARANTINE

    clean_exact = (
        status == "keep"
        and evidence_class == TRUSTED_EXACT
        and exact >= TIER_A_MIN_EXACT_TRADES
        and unresolved == 0
        and coverage >= TIER_A_MIN_QUOTE_COVERAGE
        and profit_factor >= TIER_A_MIN_PROFIT_FACTOR
        and avg_pnl > 0
        and not (reason_codes & DISQUALIFYING_CLEAN_REASONS)
    )
    if clean_exact:
        return TIER_A

    if status in {"keep", "watch"} and _profitable(row):
        return TIER_B

    return None


def evidence_repair_priority(row: dict[str, Any], tier: str | None) -> str:
    if tier != TIER_B:
        return "none"
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    unresolved = _safe_int(metrics.get("unresolved_rows"))
    coverage = _safe_float(metrics.get("quote_coverage"))
    exact = _safe_int(metrics.get("exact_trusted_priced_trades"))
    profit_factor = _safe_float(metrics.get("profit_factor"))
    avg_pnl = _safe_float(metrics.get("avg_pnl"))
    if unresolved > 0 and exact >= 8 and profit_factor >= 1.5 and avg_pnl >= 20:
        return "high"
    if unresolved > 0 or coverage < 97.5:
        return "medium"
    return "low"


def tier_a_promotion_gap(row: dict[str, Any]) -> dict[str, Any]:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    reason_codes = set(row.get("reason_codes") or [])
    blockers: list[dict[str, Any]] = []
    status = str(row.get("status") or "")
    evidence_class = str(row.get("evidence_class") or "")
    exact = _safe_int(metrics.get("exact_trusted_priced_trades"))
    unresolved = _safe_int(metrics.get("unresolved_rows"))
    coverage = _safe_float(metrics.get("quote_coverage"))
    profit_factor = _safe_float(metrics.get("profit_factor"))
    avg_pnl = _safe_float(metrics.get("avg_pnl"))
    disqualifiers = sorted(reason_codes & DISQUALIFYING_CLEAN_REASONS)

    if status != "keep":
        blockers.append({"gate": "status_keep", "current": status or None, "target": "keep"})
    if evidence_class != TRUSTED_EXACT:
        blockers.append({"gate": "trusted_exact_evidence", "current": evidence_class or None, "target": TRUSTED_EXACT})
    if exact < TIER_A_MIN_EXACT_TRADES:
        blockers.append(
            {
                "gate": "minimum_exact_trades",
                "current": exact,
                "target": TIER_A_MIN_EXACT_TRADES,
                "remaining": TIER_A_MIN_EXACT_TRADES - exact,
            }
        )
    if unresolved > 0:
        blockers.append({"gate": "zero_unresolved_rows", "current": unresolved, "target": 0, "remaining": unresolved})
    if coverage < TIER_A_MIN_QUOTE_COVERAGE:
        blockers.append(
            {
                "gate": "quote_coverage",
                "current": _round(coverage),
                "target": TIER_A_MIN_QUOTE_COVERAGE,
                "remaining": round(TIER_A_MIN_QUOTE_COVERAGE - coverage, 2),
            }
        )
    if profit_factor < TIER_A_MIN_PROFIT_FACTOR:
        blockers.append(
            {
                "gate": "profit_factor",
                "current": _round(profit_factor),
                "target": TIER_A_MIN_PROFIT_FACTOR,
                "remaining": round(TIER_A_MIN_PROFIT_FACTOR - profit_factor, 2),
            }
        )
    if avg_pnl <= 0:
        blockers.append({"gate": "positive_average_pnl", "current": _round(avg_pnl), "target": ">0"})
    if disqualifiers:
        blockers.append({"gate": "clean_disqualifiers", "current": disqualifiers, "target": []})

    return {
        "target_tier": TIER_A,
        "eligible_now": not blockers,
        "blocking_gate_count": len(blockers),
        "blocking_gates": blockers,
    }


def quarantine_overlay(row: dict[str, Any]) -> dict[str, Any]:
    reasons = set(row.get("reason_codes") or [])
    status = str(row.get("status") or "")
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    flag_reasons = sorted(
        reasons
        & {
            "trading_desk_guardrail_negative_concentration",
            "adequate_negative_exact_intraday_evidence",
            "bullish_pullback_remove_negative_exact_evidence",
            "zero_bid_exit_rate_above_2",
        }
    )
    if status in {"quarantine", "rejected"}:
        flag_reasons.append(f"status:{status}")
    if _safe_int(metrics.get("exact_trusted_priced_trades")) >= 5 and _safe_float(metrics.get("avg_pnl")) < 0:
        flag_reasons.append("negative_avg_exact_evidence")
    return {
        "quarantine": bool(flag_reasons),
        "reasons": sorted(set(flag_reasons)),
    }


def selection_gate_for_tier(tier: str) -> dict[str, Any]:
    if tier == TIER_A:
        return {
            "selection_readiness": READINESS_PAPER_REVIEW,
            "selection_reason": "Clean exact Tier A row; eligible for paper-review shortlist, not live auto-promotion.",
        }
    if tier == TIER_B:
        return {
            "selection_readiness": READINESS_WATCH_REPAIR,
            "selection_reason": "Profitable but incomplete Tier B row; watch and repair before takeability.",
        }
    if tier == TIER_C:
        return {
            "selection_readiness": READINESS_FRESH_SIGNATURE,
            "selection_reason": "Fresh scan matched a historical signature only; keep research/paper until proof gates clear.",
        }
    if tier == TIER_BLOCKED:
        return {
            "selection_readiness": READINESS_BLOCKED,
            "selection_reason": "Fresh candidate remains blocked by current guardrails.",
        }
    return {
        "selection_readiness": READINESS_DO_NOT_CHASE,
        "selection_reason": "Rejected, quarantined, or execution-risk row; do not chase.",
    }


def rank_score(row: dict[str, Any], tier: str) -> float:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    tier_bonus = {TIER_A: 1000.0, TIER_B: 500.0, TIER_QUARANTINE: -500.0}.get(tier, 0.0)
    pf_component = min(_safe_float(metrics.get("profit_factor")), 20.0)
    return round(
        tier_bonus
        + _safe_int(metrics.get("exact_trusted_priced_trades")) * 3.0
        + pf_component * 12.0
        + _safe_float(metrics.get("avg_pnl"))
        + _safe_float(metrics.get("quote_coverage")) * 0.4
        - _safe_int(metrics.get("unresolved_rows")) * 8.0,
        2,
    )


def _compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "exact_trusted_priced_trades": _safe_int(metrics.get("exact_trusted_priced_trades")),
        "candidates": _safe_int(metrics.get("candidates")),
        "unresolved_rows": _safe_int(metrics.get("unresolved_rows")),
        "quote_coverage": _round(metrics.get("quote_coverage")),
        "profit_factor": _round(metrics.get("profit_factor")),
        "avg_pnl": _round(metrics.get("avg_pnl")),
        "median_pnl": _round(metrics.get("median_pnl")),
        "win_rate": _round(metrics.get("win_rate")),
    }


def _resolve_artifact_path(path_value: Any) -> Path | None:
    if path_value is None or path_value == "":
        return None
    path = Path(str(path_value))
    if not path.is_absolute():
        path = ROOT / path
    return path


def _load_artifact(path: Path, artifact_cache: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cache_key = str(path)
    if cache_key not in artifact_cache:
        try:
            artifact_cache[cache_key] = _load_json(path)
        except Exception as exc:
            artifact_cache[cache_key] = {"missing": True, "path": str(path), "error": str(exc)}
    return artifact_cache[cache_key]


def _missing_leg_role(trade: dict[str, Any]) -> str:
    missing_long = bool(trade.get("missing_long_contract_symbol"))
    missing_short = bool(trade.get("missing_short_contract_symbol"))
    if missing_long and missing_short:
        return "both"
    if missing_long:
        return "long"
    if missing_short:
        return "short"
    return "unknown"


def _repair_contracts(trade: dict[str, Any]) -> list[str]:
    contracts = [
        trade.get("missing_long_contract_symbol"),
        trade.get("missing_short_contract_symbol"),
    ]
    if not any(contracts):
        contracts = [trade.get("long_contract_symbol"), trade.get("short_contract_symbol")]
    return sorted({str(contract) for contract in contracts if contract})


def _compact_selected_spread(trade: dict[str, Any]) -> dict[str, Any]:
    spread = trade.get("selected_spread") if isinstance(trade.get("selected_spread"), dict) else {}
    return {
        "debit_pct_of_width": _round(spread.get("debit_pct_of_width")),
        "bid_ask_pct": _round(spread.get("bid_ask_pct")),
        "fill_degradation_vs_mid_pct": _round(spread.get("fill_degradation_vs_mid_pct")),
        "long_prior_quote_days": _safe_int(spread.get("long_prior_quote_days")) if spread.get("long_prior_quote_days") is not None else None,
        "short_prior_quote_days": _safe_int(spread.get("short_prior_quote_days")) if spread.get("short_prior_quote_days") is not None else None,
        "long_delta": _round(spread.get("long_delta"), 4),
        "short_delta": _round(spread.get("short_delta"), 4),
    }


def _repair_target_from_trade(trade: dict[str, Any], *, source_artifact: Path) -> dict[str, Any]:
    return {
        "source_artifact": _rel(source_artifact),
        "ticker": str(trade.get("ticker") or "").upper(),
        "entry_date": trade.get("date"),
        "missing_quote_date": trade.get("missing_quote_date"),
        "unpriced_reason": trade.get("unpriced_reason") or trade.get("non_promotable_reason"),
        "missing_leg_role": _missing_leg_role(trade),
        "contracts": _repair_contracts(trade),
        "long_contract_symbol": trade.get("long_contract_symbol"),
        "short_contract_symbol": trade.get("short_contract_symbol"),
        "long_entry_expiry": trade.get("long_entry_expiry"),
        "short_entry_expiry": trade.get("short_entry_expiry"),
        "long_entry_strike": _round(trade.get("long_entry_strike"), 4),
        "short_entry_strike": _round(trade.get("short_entry_strike"), 4),
        "selected_spread": _compact_selected_spread(trade),
    }


def _repair_target_key(target: dict[str, Any]) -> tuple[Any, ...]:
    return (
        target.get("ticker"),
        target.get("entry_date"),
        target.get("missing_quote_date"),
        tuple(target.get("contracts") or []),
        target.get("long_contract_symbol"),
        target.get("short_contract_symbol"),
    )


def repair_target_summary(
    row: dict[str, Any],
    *,
    artifact_cache: dict[str, dict[str, Any]],
    limit: int = 8,
) -> dict[str, Any]:
    metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
    unresolved = _safe_int(metrics.get("unresolved_rows"))
    source_paths = [
        path
        for path in (_resolve_artifact_path(path_value) for path_value in row.get("source_artifacts") or [])
        if path is not None
    ]
    if unresolved <= 0:
        return {
            "detail_status": "not_applicable_no_unresolved_rows",
            "unresolved_rows": unresolved,
            "source_artifacts": [_rel(path) for path in source_paths],
            "targets_found": 0,
            "shown_target_count": 0,
            "targets": [],
        }
    if not source_paths:
        return {
            "detail_status": "source_artifacts_missing",
            "unresolved_rows": unresolved,
            "source_artifacts": [],
            "targets_found": 0,
            "shown_target_count": 0,
            "targets": [],
            "next_repair_action": "Find the source replay artifact before attempting exact quote repair.",
        }

    symbol = str(row.get("symbol") or "").upper()
    targets_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    unreadable_sources: list[str] = []
    for path in source_paths:
        payload = _load_artifact(path, artifact_cache)
        if payload.get("missing") or payload.get("error"):
            unreadable_sources.append(_rel(path) or str(path))
            continue
        for trade in payload.get("unpriced_trades") or []:
            if not isinstance(trade, dict):
                continue
            if symbol and str(trade.get("ticker") or "").upper() != symbol:
                continue
            target = _repair_target_from_trade(trade, source_artifact=path)
            targets_by_key.setdefault(_repair_target_key(target), target)

    targets = sorted(
        targets_by_key.values(),
        key=lambda target: (
            str(target.get("missing_quote_date") or ""),
            str(target.get("entry_date") or ""),
            ",".join(target.get("contracts") or []),
        ),
    )
    missing_leg_counts = Counter(str(target.get("missing_leg_role") or "unknown") for target in targets)
    missing_quote_dates = sorted({str(target.get("missing_quote_date")) for target in targets if target.get("missing_quote_date")})
    contracts = sorted({contract for target in targets for contract in target.get("contracts") or []})
    detail_status = "available" if targets else "unpriced_details_not_found"
    if unreadable_sources and not targets:
        detail_status = "source_artifacts_unreadable"
    return {
        "detail_status": detail_status,
        "unresolved_rows": unresolved,
        "source_artifacts": [_rel(path) for path in source_paths],
        "unreadable_sources": unreadable_sources,
        "targets_found": len(targets),
        "shown_target_count": min(len(targets), limit),
        "missing_leg_counts": dict(sorted(missing_leg_counts.items())),
        "missing_quote_dates": missing_quote_dates[:limit],
        "contracts": contracts[: limit * 2],
        "targets": targets[:limit],
        "next_repair_action": (
            "Repair or re-import trusted intraday OPRA/NBBO quotes for these missing quote dates and exact contracts, "
            "then rerun the source replay and rebuild this queue."
            if targets
            else "Open the source replay artifacts and classify why unpriced trade details are unavailable."
        ),
    }


def build_capture_row(
    row: dict[str, Any],
    *,
    tier: str,
    current_policy: dict[tuple[str, str], dict[str, Any]],
    fresh_scan_status: dict[tuple[str, str], dict[str, Any]],
    artifact_cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    symbol = str(row.get("symbol") or "")
    lane_id = str(row.get("lane_id") or "")
    lane_family = str(row.get("lane_family") or "")
    policy = current_policy.get((symbol, lane_id)) or current_policy.get((symbol, lane_family)) or {}
    fresh = fresh_scan_status.get((symbol, lane_id)) or fresh_scan_status.get((symbol, lane_family)) or {}
    repair = evidence_repair_priority(row, tier)
    quarantine = quarantine_overlay(row)
    metrics = _compact_metrics(row.get("metrics") if isinstance(row.get("metrics"), dict) else {})
    selection_gate = selection_gate_for_tier(tier)
    repair_summary = (
        repair_target_summary(row, artifact_cache=artifact_cache) if repair in {"high", "medium"} else None
    )
    return {
        "capture_tier": tier,
        **selection_gate,
        "symbol": symbol,
        "lane_id": lane_id,
        "lane_family": lane_family,
        "status": row.get("status"),
        "evidence_class": row.get("evidence_class"),
        "sample_status": row.get("sample_status"),
        "metrics": metrics,
        "rank_score": rank_score(row, tier),
        "reason_codes": list(row.get("reason_codes") or []),
        "status_reason": row.get("status_reason"),
        "next_step": row.get("next_step"),
        "evidence_repair_priority": repair,
        "tier_a_promotion_gap": tier_a_promotion_gap(row),
        "repair_target_summary": repair_summary,
        "quarantine_overlay": quarantine,
        "current_policy_overlay": policy,
        "fresh_scan_overlay": fresh,
        "live_policy_change": False,
    }


def fresh_scan_matches(
    payload: dict[str, Any],
    sleeve_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    rows_by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sleeve_rows:
        symbol = str(row.get("symbol") or "")
        if symbol:
            rows_by_symbol[symbol].append(row)

    matches: list[dict[str, Any]] = []
    fresh_status: dict[tuple[str, str], dict[str, Any]] = {}
    for playbook in payload.get("playbooks") or []:
        if not isinstance(playbook, dict):
            continue
        playbook_id = str(playbook.get("playbook_id") or "")
        label = playbook.get("label")
        for pick in playbook.get("returned_picks") or []:
            if not isinstance(pick, dict):
                continue
            symbol = str(pick.get("ticker") or "").upper()
            candidates = rows_by_symbol.get(symbol, [])
            lane_matches = [row for row in candidates if _lane_matches(playbook_id, row)]
            matched_rows = lane_matches or candidates
            compact_sleeves = [
                {
                    "symbol": row.get("symbol"),
                    "lane_id": row.get("lane_id"),
                    "status": row.get("status"),
                    "capture_tier": classify_capture_tier(row),
                    "avg_pnl": _round((row.get("metrics") or {}).get("avg_pnl")),
                    "profit_factor": _round((row.get("metrics") or {}).get("profit_factor")),
                    "exact": _safe_int((row.get("metrics") or {}).get("exact_trusted_priced_trades")),
                    "unresolved": _safe_int((row.get("metrics") or {}).get("unresolved_rows")),
                }
                for row in sorted(
                    matched_rows,
                    key=lambda item: (
                        1 if classify_capture_tier(item) in {TIER_A, TIER_B} else 0,
                        _safe_float((item.get("metrics") or {}).get("avg_pnl")),
                        _safe_int((item.get("metrics") or {}).get("exact_trusted_priced_trades")),
                    ),
                    reverse=True,
                )[:4]
            ]
            guardrail_decision = str(pick.get("guardrail_decision") or "unknown")
            match_type = "lane_signature" if lane_matches else "symbol_only" if matched_rows else "no_symbol_sleeve"
            capture_tier = TIER_C if guardrail_decision == "clear" else TIER_BLOCKED
            selection_gate = selection_gate_for_tier(capture_tier)
            record = {
                "capture_tier": capture_tier,
                **selection_gate,
                "match_type": match_type,
                "playbook_id": playbook_id,
                "playbook_label": label,
                "symbol": symbol,
                "direction": pick.get("direction"),
                "expiry": pick.get("expiry"),
                "guardrail_decision": guardrail_decision,
                "guardrail_reasons": list(pick.get("guardrail_reasons") or []),
                "candidate_execution_label": pick.get("candidate_execution_label"),
                "net_debit": _round(pick.get("net_debit"), 4),
                "debit_pct_of_width": _round(pick.get("debit_pct_of_width")),
                "quality_score": _round(pick.get("quality_score")),
                "ret5": _round(pick.get("ret5")),
                "matched_sleeves": compact_sleeves,
                "still_blocked": guardrail_decision == "blocked",
                "live_policy_change": False,
            }
            matches.append(record)
            for matched in matched_rows:
                key = (symbol, str(matched.get("lane_id") or ""))
                status = fresh_status.setdefault(
                    key,
                    {
                        "fresh_scan_match_count": 0,
                        "clear_count": 0,
                        "blocked_count": 0,
                        "playbooks": [],
                        "guardrail_reasons": [],
                    },
                )
                status["fresh_scan_match_count"] += 1
                if guardrail_decision == "clear":
                    status["clear_count"] += 1
                if guardrail_decision == "blocked":
                    status["blocked_count"] += 1
                if playbook_id not in status["playbooks"]:
                    status["playbooks"].append(playbook_id)
                for reason in pick.get("guardrail_reasons") or []:
                    if reason not in status["guardrail_reasons"]:
                        status["guardrail_reasons"].append(reason)
    matches.sort(
        key=lambda row: (
            0 if row["guardrail_decision"] == "clear" else 1,
            row["match_type"],
            row["symbol"],
            row["playbook_id"],
        )
    )
    return matches, fresh_status


def _queue_summary(
    rows: list[dict[str, Any]],
    fresh_rows: list[dict[str, Any]],
    quarantine_rows: list[dict[str, Any]],
    blocked_interesting_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    tier_counts = Counter(str(row.get("capture_tier")) for row in rows)
    repair_counts = Counter(str(row.get("evidence_repair_priority")) for row in rows)
    fresh_counts = Counter(str(row.get("guardrail_decision")) for row in fresh_rows)
    selection_counts = Counter(
        str(row.get("selection_readiness")) for row in [*rows, *fresh_rows, *quarantine_rows]
    )
    return {
        "queue_rows": len(rows),
        "tier_counts": dict(sorted(tier_counts.items())),
        "selection_readiness_counts": dict(sorted(selection_counts.items())),
        "evidence_repair_priority_counts": dict(sorted(repair_counts.items())),
        "fresh_scan_match_count": len(fresh_rows),
        "fresh_scan_guardrail_decision_counts": dict(sorted(fresh_counts.items())),
        "blocked_but_interesting_count": len(blocked_interesting_rows),
        "high_priority_evidence_repair_count": repair_counts.get("high", 0),
        "quarantine_queue_count": len(quarantine_rows),
        "quarantine_overlay_count": sum(
            1 for row in rows if (row.get("quarantine_overlay") or {}).get("quarantine")
        ),
        "live_policy_change": False,
    }


def build_report(
    *,
    symbol_sleeves_path: Path = DEFAULT_SYMBOL_SLEEVES,
    current_policy_path: Path = DEFAULT_CURRENT_POLICY,
    guardrail_starvation_path: Path = DEFAULT_GUARDRAIL_STARVATION,
) -> dict[str, Any]:
    symbol_sleeves = _load_json(symbol_sleeves_path)
    current_policy = _load_json(current_policy_path)
    guardrail_starvation = _load_json(guardrail_starvation_path)

    current_policy_index = current_policy_by_symbol_lane(current_policy)
    sleeve_rows = [row for row in symbol_sleeves.get("lane_symbol_rows") or [] if isinstance(row, dict)]
    existing_keys = {
        (str(row.get("symbol") or ""), str(row.get("lane_id") or ""))
        for row in sleeve_rows
        if row.get("symbol") and row.get("lane_id")
    }
    current_policy_rows = current_policy_capture_rows(current_policy_index, existing_keys)
    evidence_rows = [*sleeve_rows, *current_policy_rows]
    fresh_rows, fresh_status = fresh_scan_matches(guardrail_starvation, evidence_rows)
    artifact_cache: dict[str, dict[str, Any]] = {}

    capture_rows: list[dict[str, Any]] = []
    quarantine_rows: list[dict[str, Any]] = []
    for row in evidence_rows:
        tier = classify_capture_tier(row)
        if not tier:
            continue
        capture_row = build_capture_row(
            row,
            tier=tier,
            current_policy=current_policy_index,
            fresh_scan_status=fresh_status,
            artifact_cache=artifact_cache,
        )
        if tier == TIER_QUARANTINE:
            quarantine_rows.append(capture_row)
        else:
            capture_rows.append(capture_row)

    capture_rows.sort(
        key=lambda row: (
            0 if row.get("capture_tier") == TIER_A else 1,
            -_safe_float(row.get("rank_score")),
            str(row.get("symbol")),
            str(row.get("lane_id")),
        )
    )
    quarantine_rows.sort(
        key=lambda row: (
            -_safe_int((row.get("metrics") or {}).get("exact_trusted_priced_trades")),
            _safe_float((row.get("metrics") or {}).get("avg_pnl")),
            str(row.get("symbol")),
        )
    )
    blocked_interesting = [
        row
        for row in fresh_rows
        if row.get("guardrail_decision") == "blocked"
        and (
            _safe_float(row.get("quality_score")) >= 70.0
            or any((sleeve.get("capture_tier") in {TIER_A, TIER_B}) for sleeve in row.get("matched_sleeves") or [])
        )
    ]
    evidence_repair = [
        row
        for row in capture_rows
        if row.get("capture_tier") == TIER_B and row.get("evidence_repair_priority") in {"high", "medium"}
    ]
    evidence_repair.sort(
        key=lambda row: (
            0 if row.get("evidence_repair_priority") == "high" else 1,
            -_safe_float((row.get("metrics") or {}).get("avg_pnl")),
            -_safe_int((row.get("metrics") or {}).get("unresolved_rows")),
        )
    )

    report = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "scope": "regular_options_profit_capture_queue",
        "status": "research_paper_capture_queue",
        "live_policy_change": False,
        "proof_policy": {
            "queue_is": "research/paper visibility and proof-hardening layer",
            "queue_is_not": "scanner promotion, broker recommendation, live stop change, or proof-bar reduction",
            "tier_a_requires": [
                "trusted intraday OPRA/NBBO exact-contract evidence",
                "status keep",
                "at least 10 exact priced trades",
                "zero unresolved rows",
                "quote coverage at least 97.5%",
                "profit factor at least 1.5",
                "positive average P&L",
                "no thin-sample, unresolved, zero-bid, or negative-concentration clean disqualifier",
            ],
            "tier_b_means": "profitable keep/watch evidence that still needs proof repair, coverage, sample, or forward-paper validation",
            "tier_c_means": "fresh scan candidate matching a profitable historical signature; still paper/research unless separately proof-eligible",
            "blocked_rows_remain_blocked": True,
        },
        "inputs": [
            input_manifest_entry(symbol_sleeves_path, "regular_options_symbol_sleeves"),
            input_manifest_entry(current_policy_path, "current_policy_historical_picks"),
            input_manifest_entry(guardrail_starvation_path, "regular_guardrail_starvation"),
        ],
        "source_readback": {
            "symbol_sleeve_rows": len(sleeve_rows),
            "current_policy_generated_capture_rows": len(current_policy_rows),
            "current_policy_symbol_lane_buckets": len(current_policy_index),
            "guardrail_starvation_status": (guardrail_starvation.get("overall") or {}).get("status"),
        },
        "capture_queue": capture_rows,
        "fresh_scan_matches": fresh_rows,
        "blocked_but_interesting": blocked_interesting,
        "evidence_repair_queue": evidence_repair,
        "quarantine_queue": quarantine_rows,
        "summary": _queue_summary(capture_rows, fresh_rows, quarantine_rows, blocked_interesting),
        "final_readback": {
            "top_clean_exact": [row for row in capture_rows if row.get("capture_tier") == TIER_A][:12],
            "top_watch_repair": [row for row in capture_rows if row.get("capture_tier") == TIER_B][:20],
            "fresh_scan_matches": fresh_rows[:20],
            "blocked_but_interesting": blocked_interesting[:20],
            "evidence_repair_queue": evidence_repair[:20],
            "quarantine_preview": quarantine_rows[:20],
        },
    }
    return report


def _metrics_cells(row: dict[str, Any]) -> list[str]:
    metrics = row.get("metrics") or {}
    return [
        str(metrics.get("exact_trusted_priced_trades", 0)),
        str(metrics.get("unresolved_rows", 0)),
        str(metrics.get("quote_coverage", "")),
        str(metrics.get("profit_factor", "")),
        str(metrics.get("avg_pnl", "")),
        str(metrics.get("median_pnl", "")),
    ]


def _capture_table(rows: list[dict[str, Any]], limit: int = 30) -> list[str]:
    lines = [
        "| Tier | Readiness | Symbol | Lane | Status | Exact | Unres | Cov % | PF | Avg % | Median % | Repair | Fresh | Reason |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    for row in rows[:limit]:
        fresh = row.get("fresh_scan_overlay") or {}
        reason = ", ".join((row.get("reason_codes") or [])[:3])
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("capture_tier")),
                    _fmt(row.get("selection_readiness")),
                    _fmt(row.get("symbol")),
                    _fmt(row.get("lane_id")),
                    _fmt(row.get("status")),
                    *_metrics_cells(row),
                    _fmt(row.get("evidence_repair_priority")),
                    _fmt(json.dumps(fresh, sort_keys=True) if fresh else ""),
                    _fmt(reason),
                ]
            )
            + " |"
        )
    return lines


def _repair_summary_cells(row: dict[str, Any]) -> list[str]:
    summary = row.get("repair_target_summary") if isinstance(row.get("repair_target_summary"), dict) else {}
    if not summary:
        return ["", "", ""]
    leg_counts = summary.get("missing_leg_counts") if isinstance(summary.get("missing_leg_counts"), dict) else {}
    dates = ", ".join(str(value) for value in (summary.get("missing_quote_dates") or [])[:4])
    contracts = ", ".join(str(value) for value in (summary.get("contracts") or [])[:4])
    if not contracts:
        contracts = str(summary.get("detail_status") or "")
    return [
        _fmt(json.dumps(leg_counts, sort_keys=True) if leg_counts else summary.get("detail_status")),
        _fmt(dates),
        _fmt(contracts),
    ]


def _repair_table(rows: list[dict[str, Any]], limit: int = 30) -> list[str]:
    lines = [
        "| Repair | Symbol | Lane | Exact | Unres | Cov % | PF | Avg % | Missing legs | Missing dates | Contracts/detail | Source |",
        "|---|---|---|---:|---:|---:|---:|---:|---|---|---|---|",
    ]
    for row in rows[:limit]:
        metrics = row.get("metrics") or {}
        summary = row.get("repair_target_summary") if isinstance(row.get("repair_target_summary"), dict) else {}
        sources = ", ".join(str(value) for value in (summary.get("source_artifacts") or [])[:2])
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("evidence_repair_priority")),
                    _fmt(row.get("symbol")),
                    _fmt(row.get("lane_id")),
                    _fmt(metrics.get("exact_trusted_priced_trades", 0)),
                    _fmt(metrics.get("unresolved_rows", 0)),
                    _fmt(metrics.get("quote_coverage", "")),
                    _fmt(metrics.get("profit_factor", "")),
                    _fmt(metrics.get("avg_pnl", "")),
                    *_repair_summary_cells(row),
                    _fmt(sources),
                ]
            )
            + " |"
        )
    return lines


def _fresh_table(rows: list[dict[str, Any]], limit: int = 30) -> list[str]:
    lines = [
        "| Tier | Readiness | Symbol | Playbook | Decision | Match | Debit % | Quality | Matched sleeves | Reasons |",
        "|---|---|---|---|---|---|---:|---:|---|---|",
    ]
    for row in rows[:limit]:
        sleeves = ", ".join(
            f"{sleeve.get('lane_id')}:{sleeve.get('capture_tier') or sleeve.get('status')}"
            for sleeve in row.get("matched_sleeves") or []
        )
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("capture_tier")),
                    _fmt(row.get("selection_readiness")),
                    _fmt(row.get("symbol")),
                    _fmt(row.get("playbook_id")),
                    _fmt(row.get("guardrail_decision")),
                    _fmt(row.get("match_type")),
                    _fmt(row.get("debit_pct_of_width")),
                    _fmt(row.get("quality_score")),
                    _fmt(sleeves),
                    _fmt("; ".join(row.get("guardrail_reasons") or [])),
                ]
            )
            + " |"
        )
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary") or {}
    final = report.get("final_readback") or {}
    lines = [
        "# Regular Options Profit Capture Queue",
        "",
        "This report is generated from `scripts/build_regular_options_profit_capture_queue.py`. It is a research/paper capture and proof-hardening layer, not a scanner promotion or broker-action surface.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Queue rows: `{summary.get('queue_rows')}`.",
        f"- Tier counts: `{json.dumps(summary.get('tier_counts') or {}, sort_keys=True)}`.",
        f"- Selection readiness: `{json.dumps(summary.get('selection_readiness_counts') or {}, sort_keys=True)}`.",
        f"- Evidence repair priorities: `{json.dumps(summary.get('evidence_repair_priority_counts') or {}, sort_keys=True)}`.",
        f"- Fresh scan matches: `{summary.get('fresh_scan_match_count')}` with decisions `{json.dumps(summary.get('fresh_scan_guardrail_decision_counts') or {}, sort_keys=True)}`.",
        f"- Blocked but interesting: `{summary.get('blocked_but_interesting_count')}`.",
        f"- Quarantine queue rows: `{summary.get('quarantine_queue_count')}`.",
        f"- Live policy change: `{report.get('live_policy_change')}`.",
        "",
        "## Proof Policy",
        "",
        "- Tier A requires trusted intraday OPRA/NBBO exact-contract evidence, zero unresolved rows, adequate sample, high quote coverage, positive PF/average P&L, and no clean disqualifier.",
        "- Tier B is profitable watch evidence that still needs proof repair, sample, coverage, or forward-paper validation.",
        "- Tier C fresh scan matches are historical-signature matches only; they are not validated trade recommendations by themselves.",
        "- Selection readiness is paper/research routing only; it does not change scanner, broker, or stop-loss behavior.",
        "- Blocked candidates remain blocked, with reasons preserved.",
        "",
        "## Tier A Clean Exact",
        "",
        *_capture_table(final.get("top_clean_exact") or [], limit=20),
        "",
        "## Tier B Watch / Repair",
        "",
        *_capture_table(final.get("top_watch_repair") or [], limit=30),
        "",
        "## Fresh Scan Signature Matches",
        "",
        *_fresh_table(final.get("fresh_scan_matches") or [], limit=30),
        "",
        "## Blocked But Interesting",
        "",
        *_fresh_table(final.get("blocked_but_interesting") or [], limit=30),
        "",
        "## Evidence Repair Queue",
        "",
        *_repair_table(final.get("evidence_repair_queue") or [], limit=30),
        "",
        "## Quarantine / Do Not Chase",
        "",
        *_capture_table(final.get("quarantine_preview") or [], limit=30),
        "",
        "## Inputs",
        "",
        "| Source | Status | Generated | Path |",
        "|---|---|---|---|",
    ]
    for entry in report.get("inputs") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(entry.get("source_type")),
                    _fmt(entry.get("status")),
                    _fmt(entry.get("generated_at")),
                    _fmt(entry.get("path")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, doc_path: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"regular_options_profit_capture_queue_{stamp}.json"
    latest_json = output_dir / "latest.json"
    markdown_path = output_dir / f"regular_options_profit_capture_queue_{stamp}.md"
    latest_markdown = output_dir / "latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(markdown_path),
        "latest_markdown": str(latest_markdown),
        "docs_report": str(doc_path),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    markdown_path.write_text(markdown, encoding="utf8")
    latest_markdown.write_text(markdown, encoding="utf8")
    doc_path.write_text(markdown, encoding="utf8")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the regular options profit capture queue.")
    parser.add_argument("--symbol-sleeves", type=Path, default=DEFAULT_SYMBOL_SLEEVES)
    parser.add_argument("--current-policy", type=Path, default=DEFAULT_CURRENT_POLICY)
    parser.add_argument("--guardrail-starvation", type=Path, default=DEFAULT_GUARDRAIL_STARVATION)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        symbol_sleeves_path=args.symbol_sleeves,
        current_policy_path=args.current_policy,
        guardrail_starvation_path=args.guardrail_starvation,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    else:
        print(json.dumps({"status": report["status"], "summary": report["summary"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
