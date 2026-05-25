from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence

from wfo_optimizer import (
    IMPORTED_DAILY_TRUTH_SOURCE,
    IMPORTED_TRUTH_SOURCE,
    MIN_IMPORTED_QUOTE_COVERAGE_PCT,
    SYNTHETIC_TRUTH_SOURCE,
    build_imported_exactness_sensitivity,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PHASE_MANIFEST = ROOT / "docs" / "autoresearch" / "truth-first-champions.json"
DEFAULT_QUEUE_JSON = ROOT / "docs" / "autoresearch" / "queue.json"
DEFAULT_QUEUE_MD = ROOT / "docs" / "autoresearch" / "queue.md"
DEFAULT_DECISION_LOG_MD = ROOT / "docs" / "autoresearch" / "decision-log.md"
DEFAULT_CURRENT_STATE_MD = ROOT / "docs" / "autoresearch" / "current-state.md"
DEFAULT_CURRENT_STATE_JSON = ROOT / "docs" / "autoresearch" / "current-state.json"

FORWARD_HOLDOUT_TRUTH_SOURCE = "forward_holdout"
TRUTH_PRECEDENCE = (
    FORWARD_HOLDOUT_TRUTH_SOURCE,
    IMPORTED_TRUTH_SOURCE,
    IMPORTED_DAILY_TRUTH_SOURCE,
    SYNTHETIC_TRUTH_SOURCE,
)
VALIDATION_STAGE_ORDER = (
    "rejected",
    "synthetic_candidate",
    "imported_truth_candidate",
    "holdout_recording",
    "live_review_candidate",
)
RUN_MODE_CHOICES = ("search", "validation")

MIN_SYNTHETIC_TOTAL_TRADES = 20
MIN_IMPORTED_PRICED_TRADES = 10
MAX_UNSUPPORTED_BY_IMPORT_RATE_PCT = 25.0
MIN_FORWARD_SESSION_COUNT = 3
MIN_FORWARD_UNIQUE_DAYS = 3
MIN_FORWARD_TAKEN_PICKS = 1
MIN_FORWARD_CLOSED_REVIEWS = 1
MIN_FORWARD_CLOSED_REVIEWS_FOR_LIVE_REVIEW = 3


def _docs_paths(root_dir: Path) -> dict[str, Path]:
    docs_root = root_dir / "docs" / "autoresearch"
    return {
        "queue_json": docs_root / "queue.json",
        "queue_md": docs_root / "queue.md",
        "decision_log_md": docs_root / "decision-log.md",
        "current_state_md": docs_root / "current-state.md",
        "current_state_json": docs_root / "current-state.json",
    }


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


def _safe_slug(value: str) -> str:
    text = str(value or "").strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-_") or "autoresearch"


def _normalize_truth_lane(value: Any) -> str:
    normalized = str(value or SYNTHETIC_TRUTH_SOURCE).strip().lower() or SYNTHETIC_TRUTH_SOURCE
    if normalized == "synthetic":
        normalized = SYNTHETIC_TRUTH_SOURCE
    if normalized not in {
        SYNTHETIC_TRUTH_SOURCE,
        IMPORTED_DAILY_TRUTH_SOURCE,
        IMPORTED_TRUTH_SOURCE,
        FORWARD_HOLDOUT_TRUTH_SOURCE,
    }:
        raise ValueError(f"Unsupported truth lane: {value}")
    return normalized


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_symbols(values: Sequence[Any] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized.append(symbol)
    return normalized


def _normalize_profile_targets(values: Sequence[Any] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        target = str(raw or "").strip().lower()
        if target not in {"equity", "index"} or target in seen:
            continue
        seen.add(target)
        normalized.append(target)
    return normalized


def _normalize_directions(values: Sequence[Any] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        direction = str(raw or "").strip().lower()
        if direction not in {"call", "put"} or direction in seen:
            continue
        seen.add(direction)
        normalized.append(direction)
    return normalized


def _normalized_cohort(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(raw.get("id") or "").strip(),
        "role": str(raw.get("role") or "").strip() or "candidate",
        "label": str(raw.get("label") or raw.get("id") or "").strip(),
        "playbooks": [str(item).strip() for item in (raw.get("playbooks") or []) if str(item).strip()],
        "overrides": dict(raw.get("overrides") or {}),
        "profile_targets": _normalize_profile_targets(raw.get("profile_targets")) or ["equity"],
        "directions": _normalize_directions(raw.get("directions")),
        "allowed_proposal_families": [
            str(item).strip()
            for item in (raw.get("allowed_proposal_families") or [])
            if str(item).strip()
        ],
    }


def load_phase_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    payload = _read_json(manifest_path)
    freeze_search = bool(payload.get("freeze_search"))
    raw_mode = str(payload.get("mode") or "").strip().lower()
    mode = raw_mode if raw_mode in RUN_MODE_CHOICES else ("validation" if freeze_search else "search")
    symbols = _normalize_symbols(
        payload.get("required_watchlist")
        or payload.get("required_universe")
        or payload.get("symbols")
    )
    cohorts = [_normalized_cohort(item) for item in (payload.get("cohorts") or []) if isinstance(item, dict)]
    if not cohorts:
        raise ValueError(f"Phase manifest has no cohorts: {manifest_path}")
    controls = [item for item in cohorts if item.get("role") == "control"]
    allowed_truth_lanes = [
        _normalize_truth_lane(item)
        for item in (payload.get("allowed_truth_lanes") or [SYNTHETIC_TRUTH_SOURCE, IMPORTED_DAILY_TRUTH_SOURCE, IMPORTED_TRUTH_SOURCE])
    ]
    allowed_families = [
        str(item).strip()
        for item in (payload.get("allowed_proposal_families") or [])
        if str(item).strip()
    ]
    return {
        "path": str(manifest_path),
        "phase_id": str(payload.get("phase_id") or payload.get("id") or manifest_path.stem).strip(),
        "mode": mode,
        "freeze_search": freeze_search,
        "phase": str(payload.get("phase") or mode).strip(),
        "holdout_start": str(payload.get("holdout_start") or "").strip() or None,
        "allowed_truth_lanes": allowed_truth_lanes,
        "required_watchlist_symbols": symbols,
        "required_baseline_control": str(
            payload.get("required_baseline_control") or (controls[0]["id"] if controls else "")
        ).strip() or None,
        "allowed_proposal_families": allowed_families,
        "cohorts": cohorts,
        "cohort_map": {item["id"]: item for item in cohorts if item.get("id")},
        "notes": list(payload.get("notes") or []),
        "raw": payload,
    }


def load_batch_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    payload = _read_json(manifest_path)
    control_slug = str(payload.get("control_slug") or payload.get("control_id") or "").strip()
    challenger_slugs = [
        str(item).strip()
        for item in (payload.get("challenger_slugs") or payload.get("challengers") or [])
        if str(item).strip()
    ]
    if not control_slug and not payload.get("control_run"):
        raise ValueError(f"Batch manifest must define control_slug or control_run: {manifest_path}")
    return {
        "path": str(manifest_path),
        "batch_id": str(payload.get("batch_id") or payload.get("id") or manifest_path.stem).strip(),
        "control_slug": control_slug or None,
        "control_run": str(payload.get("control_run") or "").strip() or None,
        "challenger_slugs": challenger_slugs,
        "playbooks": [str(item).strip() for item in (payload.get("playbooks") or []) if str(item).strip()],
        "truth_lanes": [_normalize_truth_lane(item) for item in (payload.get("truth_lanes") or [SYNTHETIC_TRUTH_SOURCE])],
        "window_mode": str(payload.get("window_mode") or "full").strip() or "full",
        "required_baseline_compatibility": str(
            payload.get("required_baseline_compatibility") or "primary_scenario"
        ).strip(),
        "raw": payload,
    }


def build_experiment_fingerprint(
    *,
    phase_id: Optional[str],
    mode: str,
    cohort_id: Optional[str],
    batch_id: Optional[str],
    playbooks: Sequence[str],
    truth_lane: str,
    window_mode: str,
    watchlist_symbols: Sequence[str],
    baseline_id: Optional[str],
    compare_to: Optional[str],
    effective_override_diff: Optional[dict[str, Any]],
    imported_store_metadata: Optional[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "phase_id": phase_id,
        "mode": str(mode or "search"),
        "cohort_id": cohort_id,
        "batch_id": batch_id,
        "playbooks": [str(item) for item in playbooks],
        "truth_lane": _normalize_truth_lane(truth_lane),
        "window_mode": str(window_mode or "full"),
        "watchlist_symbols": [str(item) for item in watchlist_symbols],
        "baseline_id": baseline_id,
        "compare_to": compare_to,
        "effective_override_diff": effective_override_diff or {},
        "imported_store_metadata": imported_store_metadata or {},
    }
    payload["fingerprint_id"] = hashlib.sha1(
        json.dumps(payload, sort_keys=True).encode("utf8")
    ).hexdigest()
    return payload


def _lane_summary(result: Optional[dict[str, Any]], truth_lane: str) -> dict[str, Any]:
    if not result or result.get("error"):
        return {
            "truth_source": _normalize_truth_lane(truth_lane),
            "available": False,
            "error": result.get("error") if isinstance(result, dict) else None,
        }
    return {
        "truth_source": _normalize_truth_lane(result.get("truth_source") or truth_lane),
        "available": True,
        "run_at": result.get("run_at"),
        "playbook": result.get("playbook"),
        "lookback_years": _safe_int(result.get("lookback_years")),
        "pricing_lane": result.get("pricing_lane"),
        "total_trades": _safe_int(result.get("total_trades")),
        "candidate_trade_count": _safe_int(
            result.get("candidate_trade_count"),
            _safe_int(result.get("total_trades")) + _safe_int(result.get("unpriced_trade_count")),
        ),
        "priced_trade_count": _safe_int(result.get("priced_trade_count"), _safe_int(result.get("total_trades"))),
        "unpriced_trade_count": _safe_int(result.get("unpriced_trade_count")),
        "quote_coverage_pct": round(_safe_float(result.get("quote_coverage_pct"), 100.0), 1),
        "profit_factor": round(_safe_float(result.get("profit_factor")), 2),
        "avg_pnl_pct": round(_safe_float(result.get("avg_pnl_pct")), 2),
        "directional_accuracy_pct": round(_safe_float(result.get("directional_accuracy_pct")), 1),
        "entry_quote_time_et": result.get("entry_quote_time_et"),
        "exit_quote_time_et": result.get("exit_quote_time_et"),
        "selection_source_counts": dict(result.get("selection_source_counts") or {}),
        "contract_resolution_counts": dict(result.get("contract_resolution_counts") or {}),
        "exact_target_contract": _safe_int(
            result.get("exact_contract_match_count"),
            _safe_int((result.get("contract_resolution_counts") or {}).get("exact_target_contract")),
        ),
        "nearest_listed_contract": _safe_int(
            result.get("nearest_contract_match_count"),
            _safe_int((result.get("contract_resolution_counts") or {}).get("nearest_listed_contract")),
        ),
        "unresolved_candidates": _safe_int(
            result.get("unresolved_contract_count"),
            _safe_int((result.get("contract_resolution_counts") or {}).get("unresolved_candidates")),
        ),
        "truth_store": dict(result.get("truth_store") or {}),
    }


def _matched_support_summary(comparison: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not comparison:
        return None
    matched = comparison.get("matched_support")
    return matched if isinstance(matched, dict) else None


def _bootstrap_trade_share(lane_summary: dict[str, Any]) -> Optional[float]:
    total = _safe_int(lane_summary.get("total_trades"))
    if total <= 0:
        return None
    selection_sources = dict(lane_summary.get("selection_source_counts") or {})
    bootstrap = _safe_int(selection_sources.get("bootstrap_heuristic"))
    return round(100.0 * bootstrap / total, 1)


def _support_audit_for_lane(
    *,
    lane_name: str,
    lane_summary: dict[str, Any],
    lane_checks: dict[str, Any],
    comparison: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    matched_support = _matched_support_summary(comparison)
    return {
        "truth_source": lane_name,
        "available": bool(lane_summary.get("available")),
        "sufficient": bool(lane_checks.get("sufficient")),
        "support_reasons": list(lane_checks.get("reasons") or []),
        "candidate_trade_count": _safe_int(lane_summary.get("candidate_trade_count")),
        "priced_trade_count": _safe_int(lane_summary.get("priced_trade_count")),
        "unpriced_trade_count": _safe_int(lane_summary.get("unpriced_trade_count")),
        "exact_target_contract": _safe_int(lane_summary.get("exact_target_contract")),
        "nearest_listed_contract": _safe_int(lane_summary.get("nearest_listed_contract")),
        "unresolved_candidates": _safe_int(lane_summary.get("unresolved_candidates")),
        "bootstrap_trade_share": _bootstrap_trade_share(lane_summary),
        "matched_support_trade_count": _safe_int((matched_support or {}).get("trade_count")),
        "quote_coverage_pct": lane_summary.get("quote_coverage_pct"),
    }


def _overall_support_audit(
    *,
    authoritative_lane: str,
    lane_support: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    current = dict(lane_support.get(authoritative_lane) or {})
    available = bool(current.get("available"))
    sufficient = bool(current.get("sufficient"))
    validation_outcome = "validated" if available and sufficient else "insufficient_support"
    reasons = list(current.get("support_reasons") or [])
    return {
        "authoritative_truth_source": authoritative_lane,
        "available": available,
        "sufficient": sufficient,
        "validation_outcome": validation_outcome,
        "reasons": reasons,
    }


def build_lane_sufficiency_checks(
    *,
    synthetic_summary: Optional[dict[str, Any]],
    imported_daily_summary: Optional[dict[str, Any]],
    imported_intraday_summary: Optional[dict[str, Any]],
    forward_summary: Optional[dict[str, Any]],
    imported_daily_comparison: Optional[dict[str, Any]],
    imported_intraday_comparison: Optional[dict[str, Any]],
) -> dict[str, Any]:
    checks: dict[str, Any] = {}

    synthetic_total = _safe_int((synthetic_summary or {}).get("total_trades"))
    checks[SYNTHETIC_TRUTH_SOURCE] = {
        "available": bool((synthetic_summary or {}).get("available")),
        "sufficient": synthetic_total >= MIN_SYNTHETIC_TOTAL_TRADES,
        "reasons": [] if synthetic_total >= MIN_SYNTHETIC_TOTAL_TRADES else [f"Need at least {MIN_SYNTHETIC_TOTAL_TRADES} synthetic trades."],
        "metrics": {"total_trades": synthetic_total},
    }

    for lane_name, lane_summary, comparison in (
        (IMPORTED_DAILY_TRUTH_SOURCE, imported_daily_summary, imported_daily_comparison),
        (IMPORTED_TRUTH_SOURCE, imported_intraday_summary, imported_intraday_comparison),
    ):
        priced = _safe_int((lane_summary or {}).get("priced_trade_count"))
        coverage = _safe_float((lane_summary or {}).get("quote_coverage_pct"), 0.0)
        unsupported_rate = comparison.get("unsupported_by_import_rate_pct") if isinstance(comparison, dict) else None
        reasons: list[str] = []
        if priced < MIN_IMPORTED_PRICED_TRADES:
            reasons.append(f"Need at least {MIN_IMPORTED_PRICED_TRADES} priced imported trades.")
        if coverage < MIN_IMPORTED_QUOTE_COVERAGE_PCT:
            reasons.append(
                f"Quote coverage {coverage:.1f}% is below the {MIN_IMPORTED_QUOTE_COVERAGE_PCT:.1f}% floor."
            )
        if unsupported_rate is not None and _safe_float(unsupported_rate) > MAX_UNSUPPORTED_BY_IMPORT_RATE_PCT:
            reasons.append(
                f"Unsupported-by-import rate {_safe_float(unsupported_rate):.1f}% exceeds the {MAX_UNSUPPORTED_BY_IMPORT_RATE_PCT:.1f}% ceiling."
            )
        checks[lane_name] = {
            "available": bool((lane_summary or {}).get("available")),
            "sufficient": not reasons and bool((lane_summary or {}).get("available")),
            "reasons": reasons,
            "metrics": {
                "priced_trade_count": priced,
                "quote_coverage_pct": round(coverage, 1),
                "unsupported_by_import_rate_pct": unsupported_rate,
            },
        }

    forward = dict(forward_summary or {})
    forward_reasons: list[str] = []
    if not forward.get("available"):
        forward_reasons.append("No forward holdout evidence has been recorded yet.")
    if _safe_int(forward.get("session_count")) < MIN_FORWARD_SESSION_COUNT:
        forward_reasons.append(f"Need at least {MIN_FORWARD_SESSION_COUNT} forward sessions.")
    if _safe_int(forward.get("unique_recording_days")) < MIN_FORWARD_UNIQUE_DAYS:
        forward_reasons.append(f"Need recordings on at least {MIN_FORWARD_UNIQUE_DAYS} distinct days.")
    if _safe_int(forward.get("taken_pick_count")) < MIN_FORWARD_TAKEN_PICKS:
        forward_reasons.append(f"Need at least {MIN_FORWARD_TAKEN_PICKS} taken pick in the holdout lane.")
    if _safe_int(forward.get("closed_review_count")) < MIN_FORWARD_CLOSED_REVIEWS:
        forward_reasons.append(f"Need at least {MIN_FORWARD_CLOSED_REVIEWS} closed reviewed position.")
    checks[FORWARD_HOLDOUT_TRUTH_SOURCE] = {
        "available": bool(forward.get("available")),
        "sufficient": not forward_reasons and bool(forward.get("available")),
        "reasons": forward_reasons,
        "metrics": {
            "session_count": _safe_int(forward.get("session_count")),
            "unique_recording_days": _safe_int(forward.get("unique_recording_days")),
            "taken_pick_count": _safe_int(forward.get("taken_pick_count")),
            "closed_review_count": _safe_int(forward.get("closed_review_count")),
        },
    }
    return checks


def _authoritative_lane(lane_checks: dict[str, Any]) -> str:
    for lane in TRUTH_PRECEDENCE:
        current = lane_checks.get(lane) or {}
        if current.get("available"):
            return lane
    return SYNTHETIC_TRUTH_SOURCE


def _recommended_stage(
    *,
    authoritative_lane: str,
    lane_checks: dict[str, Any],
) -> str:
    forward_check = lane_checks.get(FORWARD_HOLDOUT_TRUTH_SOURCE) or {}
    if authoritative_lane == FORWARD_HOLDOUT_TRUTH_SOURCE:
        closed = _safe_int(((forward_check.get("metrics") or {}).get("closed_review_count")))
        if forward_check.get("sufficient") and closed >= MIN_FORWARD_CLOSED_REVIEWS_FOR_LIVE_REVIEW:
            return "live_review_candidate"
        if forward_check.get("available"):
            return "holdout_recording"
        return "imported_truth_candidate"
    if authoritative_lane in {IMPORTED_DAILY_TRUTH_SOURCE, IMPORTED_TRUTH_SOURCE}:
        return "imported_truth_candidate"
    if (lane_checks.get(SYNTHETIC_TRUTH_SOURCE) or {}).get("available"):
        return "synthetic_candidate"
    return "rejected"


def _lane_caveats(
    *,
    synthetic_summary: dict[str, Any],
    imported_daily_summary: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    caveats: dict[str, dict[str, Any]] = {}
    if imported_daily_summary.get("available"):
        imported_entry_clock = str(
            imported_daily_summary.get("entry_quote_time_et") or "End-of-day snapshot ET"
        ).strip()
        synthetic_entry_clock = str(
            synthetic_summary.get("entry_quote_time_et") or "Synthetic next-session entry approximation"
        ).strip()
        caveats[IMPORTED_DAILY_TRUTH_SOURCE] = {
            "severity": "warning",
            "fill_equivalent_to_synthetic": False,
            "summary": (
                "historical_imported_daily is a harsher end-of-day stress lane and is not "
                "fill-equivalent to synthetic replay."
            ),
            "details": [
                f"{IMPORTED_DAILY_TRUTH_SOURCE} enters from {imported_entry_clock}.",
                f"{SYNTHETIC_TRUTH_SOURCE} approximates {synthetic_entry_clock}.",
                "Use imported daily to disqualify fragile cohorts, not as an apples-to-apples "
                "profitability ranking against synthetic replay.",
            ],
        }
    return caveats


def build_evidence_bundle(
    *,
    cohort_id: Optional[str],
    phase_id: Optional[str],
    synthetic_result: Optional[dict[str, Any]],
    imported_daily_result: Optional[dict[str, Any]],
    imported_intraday_result: Optional[dict[str, Any]],
    forward_summary: Optional[dict[str, Any]],
    imported_daily_comparison: Optional[dict[str, Any]],
    imported_intraday_comparison: Optional[dict[str, Any]],
) -> dict[str, Any]:
    synthetic_summary = _lane_summary(synthetic_result, SYNTHETIC_TRUTH_SOURCE)
    imported_daily_summary = _lane_summary(imported_daily_result, IMPORTED_DAILY_TRUTH_SOURCE)
    imported_intraday_summary = _lane_summary(imported_intraday_result, IMPORTED_TRUTH_SOURCE)
    lane_checks = build_lane_sufficiency_checks(
        synthetic_summary=synthetic_summary,
        imported_daily_summary=imported_daily_summary,
        imported_intraday_summary=imported_intraday_summary,
        forward_summary=forward_summary,
        imported_daily_comparison=imported_daily_comparison,
        imported_intraday_comparison=imported_intraday_comparison,
    )
    authoritative = _authoritative_lane(lane_checks)
    next_stage = _recommended_stage(authoritative_lane=authoritative, lane_checks=lane_checks)
    support_audit = {
        "lanes": {
            SYNTHETIC_TRUTH_SOURCE: _support_audit_for_lane(
                lane_name=SYNTHETIC_TRUTH_SOURCE,
                lane_summary=synthetic_summary,
                lane_checks=lane_checks.get(SYNTHETIC_TRUTH_SOURCE) or {},
            ),
            IMPORTED_DAILY_TRUTH_SOURCE: _support_audit_for_lane(
                lane_name=IMPORTED_DAILY_TRUTH_SOURCE,
                lane_summary=imported_daily_summary,
                lane_checks=lane_checks.get(IMPORTED_DAILY_TRUTH_SOURCE) or {},
                comparison=imported_daily_comparison,
            ),
            IMPORTED_TRUTH_SOURCE: _support_audit_for_lane(
                lane_name=IMPORTED_TRUTH_SOURCE,
                lane_summary=imported_intraday_summary,
                lane_checks=lane_checks.get(IMPORTED_TRUTH_SOURCE) or {},
                comparison=imported_intraday_comparison,
            ),
            FORWARD_HOLDOUT_TRUTH_SOURCE: {
                "truth_source": FORWARD_HOLDOUT_TRUTH_SOURCE,
                "available": bool((forward_summary or {}).get("available")),
                "sufficient": bool((lane_checks.get(FORWARD_HOLDOUT_TRUTH_SOURCE) or {}).get("sufficient")),
                "support_reasons": list((lane_checks.get(FORWARD_HOLDOUT_TRUTH_SOURCE) or {}).get("reasons") or []),
                "candidate_trade_count": _safe_int((forward_summary or {}).get("scan_pick_count")),
                "priced_trade_count": _safe_int((forward_summary or {}).get("taken_pick_count")),
                "unpriced_trade_count": 0,
                "exact_target_contract": 0,
                "nearest_listed_contract": 0,
                "unresolved_candidates": 0,
                "bootstrap_trade_share": None,
                "matched_support_trade_count": 0,
                "quote_coverage_pct": None,
            },
        },
        "daily_exactness_sensitivity": build_imported_exactness_sensitivity(imported_daily_result),
    }
    lane_caveats = _lane_caveats(
        synthetic_summary=synthetic_summary,
        imported_daily_summary=imported_daily_summary,
    )
    support_audit["overall"] = _overall_support_audit(
        authoritative_lane=authoritative,
        lane_support=dict(support_audit.get("lanes") or {}),
    )
    evidence_state = (
        "validated"
        if (support_audit.get("overall") or {}).get("sufficient")
        else "insufficient_support"
    )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "phase_id": phase_id,
        "cohort_id": cohort_id,
        "truth_precedence": list(TRUTH_PRECEDENCE),
        "lane_summaries": {
            SYNTHETIC_TRUTH_SOURCE: synthetic_summary,
            IMPORTED_DAILY_TRUTH_SOURCE: imported_daily_summary,
            IMPORTED_TRUTH_SOURCE: imported_intraday_summary,
            FORWARD_HOLDOUT_TRUTH_SOURCE: dict(forward_summary or {"available": False}),
        },
        "matched_support": {
            IMPORTED_DAILY_TRUTH_SOURCE: _matched_support_summary(imported_daily_comparison),
            IMPORTED_TRUTH_SOURCE: _matched_support_summary(imported_intraday_comparison),
        },
        "lane_checks": lane_checks,
        "lane_caveats": lane_caveats,
        "support_audit": support_audit,
        "authoritative_truth_source": authoritative,
        "recommended_next_stage": next_stage,
        "evidence_state": evidence_state,
        "validation_outcome": (support_audit.get("overall") or {}).get("validation_outcome"),
        "veto_reasons": [],
    }


def build_baseline_compatibility(
    *,
    compare_to: Optional[Path],
    required_baseline_id: Optional[str],
    cohort_id: Optional[str],
    batch_id: Optional[str],
    comparison_generated: bool,
    comparison_error: Optional[str] = None,
) -> dict[str, Any]:
    compatible = None
    reasons: list[str] = []
    if required_baseline_id and compare_to is None and str(cohort_id or "").strip() != str(required_baseline_id or "").strip():
        reasons.append(
            f"Phase or batch expects baseline '{required_baseline_id}', but no compare-to run was supplied."
        )
    if comparison_error:
        reasons.append(comparison_error)
        compatible = False
    elif comparison_generated:
        compatible = True
    return {
        "required_baseline_id": required_baseline_id,
        "cohort_id": cohort_id,
        "batch_id": batch_id,
        "baseline_run_dir": str(compare_to) if compare_to is not None else None,
        "comparison_generated": comparison_generated,
        "compatible": compatible,
        "reasons": reasons,
    }


def build_decision_packet(
    *,
    slug: str,
    evidence_bundle: dict[str, Any],
    primary_result: dict[str, Any],
    stability_report: dict[str, Any],
    policy_report: dict[str, Any],
    falsification_report: dict[str, Any],
    baseline_compatibility: dict[str, Any],
) -> dict[str, Any]:
    authoritative = str(evidence_bundle.get("authoritative_truth_source") or SYNTHETIC_TRUTH_SOURCE)
    authoritative_summary = dict((evidence_bundle.get("lane_summaries") or {}).get(authoritative) or {})
    authoritative_checks = dict((evidence_bundle.get("lane_checks") or {}).get(authoritative) or {})
    lane_caveats = dict(evidence_bundle.get("lane_caveats") or {})
    authoritative_lane_caveat = dict(lane_caveats.get(authoritative) or {})
    support_audit = dict(evidence_bundle.get("support_audit") or {})
    support_overall = dict(support_audit.get("overall") or {})
    stage = str(evidence_bundle.get("recommended_next_stage") or "rejected")
    supporting: list[str] = []
    counters: list[str] = []
    block_reasons: list[str] = []

    if authoritative_summary.get("available"):
        supporting.append(
            f"{authoritative} evidence is available with {authoritative_summary.get('total_trades', 0)} trade(s)."
        )
    if authoritative_checks.get("sufficient"):
        supporting.append(f"{authoritative} cleared its sufficiency bar.")
    else:
        counters.extend(authoritative_checks.get("reasons") or [])
        if authoritative != FORWARD_HOLDOUT_TRUTH_SOURCE:
            block_reasons.append("insufficient_support")

    stability_status = str(stability_report.get("overall_status") or "block").strip().lower()
    promotion_status = str((policy_report.get("scan_policy") or {}).get("promotion_status") or "block").strip().lower()
    if stability_status == "block":
        block_reasons.append("stability_block")
        counters.append("Stability report remains blocked.")
    elif stability_status == "watch":
        counters.append("Stability report is still watch-only.")
    else:
        supporting.append("Stability report cleared promote-level status.")

    if promotion_status == "block":
        block_reasons.append("policy_block")
        counters.append("Live policy still resolves to block.")
    elif promotion_status == "watch":
        counters.append("Live policy remains watch-only.")
    else:
        supporting.append("Replay-backed policy would approve this cohort.")

    if authoritative == SYNTHETIC_TRUTH_SOURCE:
        block_reasons.append("synthetic_only")
        counters.append("Only synthetic research evidence supports this cohort.")
    if authoritative == IMPORTED_DAILY_TRUTH_SOURCE:
        block_reasons.append("daily_truth_cap")
        counters.append("Imported daily truth is stronger than synthetic, but it still caps confidence below intraday or forward holdout.")
    if authoritative_lane_caveat:
        counters.append(str(authoritative_lane_caveat.get("summary") or "").strip())

    if support_overall.get("validation_outcome") == "insufficient_support":
        block_reasons.append("insufficient_support")
        counters.extend(list(support_overall.get("reasons") or []))

    catastrophic_window_count = (falsification_report.get("acceptance_rule") or {}).get("catastrophic_window_count")
    if catastrophic_window_count not in (None, 0):
        block_reasons.append("catastrophic_windows")
        counters.append("Rolling-window falsification found catastrophic windows.")

    top_ticker_share = _safe_float((((falsification_report.get("concentration") or {}).get("dimensions") or {}).get("ticker") or {}).get("top_share_pct"))
    if top_ticker_share >= 70.0:
        block_reasons.append("ticker_concentration")
        counters.append(f"Ticker concentration is too high ({top_ticker_share:.1f}% top-share).")

    if baseline_compatibility.get("compatible") is False:
        block_reasons.append("baseline_incompatible")
        counters.extend(baseline_compatibility.get("reasons") or [])
    elif baseline_compatibility.get("compatible") is True:
        supporting.append("Baseline comparison is compatible and present.")

    forward_summary = dict((evidence_bundle.get("lane_summaries") or {}).get(FORWARD_HOLDOUT_TRUTH_SOURCE) or {})
    if not forward_summary.get("available"):
        counters.append("No forward holdout evidence has been recorded yet.")
    elif _safe_int(forward_summary.get("closed_review_count")) < MIN_FORWARD_CLOSED_REVIEWS_FOR_LIVE_REVIEW:
        counters.append("Forward holdout exists, but not enough closed reviewed positions are available yet.")

    profit_factor = _safe_float(authoritative_summary.get("profit_factor"))
    if profit_factor >= 1.0:
        supporting.append(f"Authoritative lane profit factor is {profit_factor:.2f}.")
    else:
        counters.append(f"Authoritative lane profit factor is only {profit_factor:.2f}.")

    verdict = "hold"
    if block_reasons and stage == "rejected":
        verdict = "reject"
    elif "policy_block" in block_reasons or "stability_block" in block_reasons:
        verdict = "reject"
    elif stage in {"synthetic_candidate", "imported_truth_candidate", "holdout_recording"}:
        verdict = "hold"
    elif stage == "live_review_candidate" and not block_reasons:
        verdict = "promote"
    elif evidence_bundle.get("validation_outcome") == "insufficient_support":
        verdict = "hold"

    next_action = "human_review"
    if "synthetic_only" in block_reasons:
        next_action = "import_truth_data"
    elif "daily_truth_cap" in block_reasons:
        next_action = "collect_intraday_or_forward_truth"
    elif "insufficient_support" in block_reasons:
        next_action = "collect_more_evidence"
    elif "baseline_incompatible" in block_reasons:
        next_action = "rerun_with_control"
    elif verdict == "reject":
        next_action = "research_new_hypothesis"
    elif stage == "holdout_recording":
        next_action = "continue_holdout_recording"

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "slug": slug,
        "recommended_verdict": verdict,
        "recommended_stage": stage,
        "evidence_state": evidence_bundle.get("evidence_state"),
        "validation_outcome": evidence_bundle.get("validation_outcome"),
        "authoritative_truth_source": authoritative,
        "normalized_block_reasons": sorted(set(block_reasons)),
        "strongest_supporting_evidence": supporting[:5],
        "strongest_counterargument": counters[:5],
        "baseline_compatibility": baseline_compatibility,
        "next_allowed_action": next_action,
        "lane_caveats": lane_caveats,
        "authoritative_lane_caveat": authoritative_lane_caveat or None,
        "support_audit": support_audit,
        "summary_metrics": {
            "profit_factor": authoritative_summary.get("profit_factor"),
            "avg_pnl_pct": authoritative_summary.get("avg_pnl_pct"),
            "directional_accuracy_pct": authoritative_summary.get("directional_accuracy_pct"),
            "quote_coverage_pct": authoritative_summary.get("quote_coverage_pct"),
        },
    }


def render_decision_md(packet: dict[str, Any], *, slug: str, closure: Optional[dict[str, Any]] = None) -> str:
    lines = [
        f"# Decision Packet: {slug}",
        "",
        "## Machine Recommendation",
        "",
        f"- Verdict: `{packet.get('recommended_verdict')}`",
        f"- Stage: `{packet.get('recommended_stage')}`",
        f"- Evidence state: `{packet.get('evidence_state')}`",
        f"- Validation outcome: `{packet.get('validation_outcome')}`",
        f"- Authoritative truth: `{packet.get('authoritative_truth_source')}`",
        f"- Next action: `{packet.get('next_allowed_action')}`",
        "",
        "## Support Audit",
        "",
    ]
    support_overall = dict((packet.get("support_audit") or {}).get("overall") or {})
    if support_overall:
        lines.extend(
            [
                f"- Available: `{support_overall.get('available')}`",
                f"- Sufficient: `{support_overall.get('sufficient')}`",
                f"- Outcome: `{support_overall.get('validation_outcome')}`",
            ]
        )
        reasons = list(support_overall.get("reasons") or [])
        if reasons:
            lines.append("- Reasons:")
            lines.extend(f"  - {item}" for item in reasons[:5])
    else:
        lines.append("- None recorded.")
    lines.extend(
        [
            "",
        "## Strongest Supporting Evidence",
        "",
        ]
    )
    supporting = list(packet.get("strongest_supporting_evidence") or [])
    if supporting:
        lines.extend(f"- {item}" for item in supporting)
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Strongest Counterargument", ""])
    counters = list(packet.get("strongest_counterargument") or [])
    if counters:
        lines.extend(f"- {item}" for item in counters)
    else:
        lines.append("- None recorded.")
    lines.extend(["", "## Normalized Block Reasons", ""])
    reasons = list(packet.get("normalized_block_reasons") or [])
    if reasons:
        lines.extend(f"- `{item}`" for item in reasons)
    else:
        lines.append("- None.")
    lane_caveat = dict(packet.get("authoritative_lane_caveat") or {})
    if lane_caveat:
        lines.extend(["", "## Lane Caveat", ""])
        summary = str(lane_caveat.get("summary") or "").strip()
        if summary:
            lines.append(f"- {summary}")
        for item in list(lane_caveat.get("details") or []):
            detail = str(item or "").strip()
            if detail:
                lines.append(f"- {detail}")
    if closure:
        lines.extend(
            [
                "",
                "## Human Closure",
                "",
                f"- Final verdict: `{closure.get('final_verdict')}`",
                f"- Approver: `{closure.get('approver')}`",
                f"- Advance queue state: `{closure.get('advance_queue_state')}`",
                f"- Recorded at: `{closure.get('recorded_at')}`",
                "",
                str(closure.get("rationale") or "").strip() or "No rationale supplied.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _collect_closures(root_dir: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    run_root = root_dir / "research_runs"
    if not run_root.exists():
        return items
    for run_dir in sorted((path for path in run_root.iterdir() if path.is_dir()), key=lambda path: path.name):
        closure_path = run_dir / "decision_closure.json"
        if not closure_path.exists():
            continue
        payload = _read_json(closure_path)
        payload["run_dir"] = str(run_dir)
        payload["slug"] = payload.get("slug") or run_dir.name.split("_", 2)[-1]
        items.append(payload)
    return sorted(items, key=lambda item: str(item.get("recorded_at") or ""))


def _load_queue_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"active": [], "frozen": [], "historical": []}
    payload = _read_json(path)
    for key in ("active", "frozen", "historical"):
        payload.setdefault(key, [])
    return payload


def render_queue_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Autoresearch Queue",
        "",
    ]
    for section in ("active", "frozen", "historical"):
        items = list(payload.get(section) or [])
        lines.append(f"## {section.title()}")
        lines.append("")
        if not items:
            lines.append("_None._")
            lines.append("")
            continue
        lines.append("| Slug | Status | Summary |")
        lines.append("| --- | --- | --- |")
        for item in items:
            slug = str(item.get("slug") or item.get("id") or "").strip()
            status = str(item.get("status") or "").strip() or section
            summary = str(item.get("summary") or item.get("hypothesis") or item.get("label") or "").strip()
            lines.append(f"| {slug} | {status} | {summary} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def generate_decision_log(root_dir: Path, *, output_path: Path = DEFAULT_DECISION_LOG_MD) -> str:
    closures = _collect_closures(root_dir)
    lines = [
        "# Autoresearch Decision Log",
        "",
        "Generated from `decision_closure.json` artifacts.",
        "",
        "| Date | Run slug | Recommendation | Summary |",
        "| --- | --- | --- | --- |",
    ]
    if not closures:
        lines.append("| - | - | - | No decision closures recorded yet. |")
    else:
        for item in sorted(closures, key=lambda entry: str(entry.get("recorded_at") or ""), reverse=True):
            lines.append(
                f"| {str(item.get('recorded_at') or '')[:10]} | {item.get('slug')} | {item.get('final_verdict')} | {str(item.get('rationale') or '').strip()} |"
            )
    text = "\n".join(lines).rstrip() + "\n"
    _write_text(output_path, text)
    return text


def generate_current_state(
    root_dir: Path,
    *,
    phase_manifest: dict[str, Any],
    queue_payload: dict[str, Any],
    output_md: Path = DEFAULT_CURRENT_STATE_MD,
    output_json: Path = DEFAULT_CURRENT_STATE_JSON,
) -> dict[str, Any]:
    closures = _collect_closures(root_dir)
    closure_map = {
        str(item.get("slug") or "").strip(): item
        for item in closures
        if str(item.get("slug") or "").strip()
    }
    run_root = root_dir / "research_runs"
    recent_runs = []
    if run_root.exists():
        for run_dir in sorted((path for path in run_root.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True)[:5]:
            manifest_path = run_dir / "manifest.json"
            packet_path = run_dir / "decision_packet.json"
            manifest = _read_json(manifest_path) if manifest_path.exists() else {}
            packet = _read_json(packet_path) if packet_path.exists() else {}
            recent_runs.append(
                {
                    "run_dir": str(run_dir),
                    "slug": manifest.get("slug") or run_dir.name.split("_", 2)[-1],
                    "status": manifest.get("status"),
                    "mode": manifest.get("mode") or "legacy",
                    "cohort_id": manifest.get("cohort_id"),
                    "recommended_verdict": (
                        (closure_map.get(manifest.get("slug") or run_dir.name.split("_", 2)[-1]) or {}).get("final_verdict")
                        or packet.get("recommended_verdict")
                        or "n/a"
                    ),
                    "recommended_stage": packet.get("recommended_stage") or "n/a",
                }
            )
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "phase_id": phase_manifest.get("phase_id"),
        "mode": phase_manifest.get("mode"),
        "freeze_search": phase_manifest.get("freeze_search"),
        "required_baseline_control": phase_manifest.get("required_baseline_control"),
        "allowed_truth_lanes": list(phase_manifest.get("allowed_truth_lanes") or []),
        "validation_scope_symbols": list(phase_manifest.get("required_watchlist_symbols") or []),
        "active_queue_count": len(queue_payload.get("active") or []),
        "frozen_queue_count": len(queue_payload.get("frozen") or []),
        "historical_queue_count": len(queue_payload.get("historical") or []),
        "recent_runs": recent_runs,
        "latest_closures": list(reversed(closures[-5:])),
    }
    _write_json(output_json, payload)

    lines = [
        "# Autoresearch Current State",
        "",
        f"- Phase: `{payload['phase_id']}`",
        f"- Mode: `{payload['mode']}`",
        f"- Freeze search: `{payload['freeze_search']}`",
        f"- Required baseline control: `{payload['required_baseline_control']}`",
        f"- Allowed truth lanes: `{', '.join(payload['allowed_truth_lanes'])}`",
        f"- Validation scope: `{', '.join(payload['validation_scope_symbols'])}`",
        f"- Active queue items: `{payload['active_queue_count']}`",
        f"- Frozen queue items: `{payload['frozen_queue_count']}`",
        f"- Historical queue items: `{payload['historical_queue_count']}`",
        "",
        "## Recent Runs",
        "",
    ]
    if recent_runs:
        for item in recent_runs:
            lines.append(
                f"- `{item['slug']}`: status `{item['status']}`, mode `{item['mode']}`, stage `{item.get('recommended_stage')}`, verdict `{item.get('recommended_verdict')}`"
            )
    else:
        lines.append("- None.")
    lines.extend(["", "## Latest Closures", ""])
    if closures:
        for item in list(reversed(closures[-5:])):
            lines.append(
                f"- `{item.get('slug')}`: `{item.get('final_verdict')}` on `{str(item.get('recorded_at') or '')[:10]}` by `{item.get('approver')}`"
            )
    else:
        lines.append("- No closure artifacts recorded yet.")
    _write_text(output_md, "\n".join(lines).rstrip() + "\n")
    return payload


def update_queue_with_closure(
    queue_payload: dict[str, Any],
    *,
    slug: str,
    verdict: str,
    rationale: str,
    advance_queue_state: bool,
) -> dict[str, Any]:
    output = {
        "active": list(queue_payload.get("active") or []),
        "frozen": list(queue_payload.get("frozen") or []),
        "historical": list(queue_payload.get("historical") or []),
    }
    if not advance_queue_state:
        return output

    for section in ("active", "frozen"):
        remaining = []
        moved = None
        for item in output[section]:
            item_slug = str(item.get("slug") or item.get("id") or "").strip()
            if item_slug == slug and moved is None:
                moved = dict(item)
                moved["status"] = verdict
                moved["summary"] = rationale
            else:
                remaining.append(item)
        output[section] = remaining
        if moved is not None:
            output["historical"].append(moved)
            break
    return output


def write_operator_state(
    *,
    root_dir: Path,
    phase_manifest_path: str | Path | None,
    queue_json_path: str | Path | None = None,
) -> None:
    paths = _docs_paths(root_dir)
    manifest_path = Path(phase_manifest_path) if phase_manifest_path else DEFAULT_PHASE_MANIFEST
    queue_path = Path(queue_json_path) if queue_json_path else paths["queue_json"]
    phase_manifest = load_phase_manifest(manifest_path)
    queue_payload = _load_queue_payload(queue_path)
    _write_text(paths["queue_md"], render_queue_md(queue_payload))
    generate_decision_log(root_dir, output_path=paths["decision_log_md"])
    generate_current_state(
        root_dir,
        phase_manifest=phase_manifest,
        queue_payload=queue_payload,
        output_md=paths["current_state_md"],
        output_json=paths["current_state_json"],
    )


def record_decision_closure(
    *,
    root_dir: Path,
    run_dir: Path,
    final_verdict: str,
    approver: str,
    rationale: str,
    advance_queue_state: bool,
    phase_manifest_path: str | Path | None = None,
    queue_json_path: str | Path | None = None,
) -> dict[str, Any]:
    paths = _docs_paths(root_dir)
    manifest = _read_json(run_dir / "manifest.json")
    slug = manifest.get("slug") or run_dir.name.split("_", 2)[-1]
    closure = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "slug": slug,
        "run_dir": str(run_dir),
        "final_verdict": str(final_verdict).strip().lower(),
        "approver": str(approver).strip() or "unknown",
        "rationale": str(rationale).strip(),
        "advance_queue_state": bool(advance_queue_state),
    }
    _write_json(run_dir / "decision_closure.json", closure)

    packet = _read_json(run_dir / "decision_packet.json") if (run_dir / "decision_packet.json").exists() else {}
    _write_text(run_dir / "decision.md", render_decision_md(packet, slug=slug, closure=closure))

    queue_path = Path(queue_json_path) if queue_json_path else paths["queue_json"]
    queue_payload = _load_queue_payload(queue_path)
    updated_queue = update_queue_with_closure(
        queue_payload,
        slug=slug,
        verdict=closure["final_verdict"],
        rationale=closure["rationale"],
        advance_queue_state=bool(advance_queue_state),
    )
    _write_json(queue_path, updated_queue)
    write_operator_state(
        root_dir=root_dir,
        phase_manifest_path=phase_manifest_path or DEFAULT_PHASE_MANIFEST,
        queue_json_path=queue_path,
    )
    return closure
