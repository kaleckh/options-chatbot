from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_macro_event_long_strangle_replay_readiness"
CONCEPT_ID = "low_mid_vix_macro_event_long_strangle_v1"
EXPECTED_STRUCTURE = "defined_risk_long_straddles_or_strangles_only"

DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-preregistered-macro-event-long-strangle-playbook"
    / "latest.json"
)
DEFAULT_EVENT_CALENDAR = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-calendar" / "latest.json"
DEFAULT_VIX_BUCKET = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-macro-event-long-strangle-replay-readiness"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-macro-event-long-strangle-replay-readiness.md"

REQUIRED_EVENT_CATEGORIES = (
    "fomc_rate_decision",
    "fomc_minutes",
    "cpi",
    "pce",
    "nonfarm_payrolls",
    "scheduled_fed_chair_testimony",
)
INITIAL_RESEARCH_UNIVERSE = ("SPY", "QQQ")
FUTURE_EXTENSION_UNIVERSE = ("IWM", "DIA")
REQUIRED_DENOMINATOR_STATUSES = (
    "no_event",
    "no_candidate",
    "rejected_event_calendar_missing",
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
    "duplicate_strict_new_identity",
    "replay_gate_blocked",
)
STRICT_NEW_IDENTITY_FIELDS = (
    "concept_id",
    "event_id",
    "event_category",
    "event_timestamp_utc",
    "underlying",
    "entry_timestamp_utc",
    "expiration",
    "call_occ_symbol",
    "put_occ_symbol",
    "call_strike",
    "put_strike",
    "side",
    "quantity_ratio",
    "quote_timestamp_basis",
)
EVENT_LEAKAGE_KEYS = {
    "event_outcome",
    "outcome",
    "actual",
    "surprise",
    "realized_move",
    "realized_vol",
    "realized_volatility",
    "future_iv",
    "post_event_iv",
    "option_return",
    "option_pnl",
    "pnl",
    "net_pnl",
    "net_pnl_usd",
    "return_after_event",
}

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
    "historical_replay_performed": False,
    "readiness_audit_performed": True,
}

FORBIDDEN_ACTIONS = (
    "broker_orders",
    "live_validation",
    "auto_track",
    "scanner_release",
    "strategy_logic_change",
    "stop_or_sizing_change",
    "proof_bar_relaxation",
    "quote_import",
    "evidence_database_mutation",
    "protected_holdout_consumption",
    "promotion",
    "historical_rows_as_forward_proof",
    "source_midpoint_eod_stale_display_manual_last_model_synthetic_or_lookahead_proof",
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


def _load_json(path: Path, *, required: bool) -> tuple[Any, dict[str, Any]]:
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
    meta["status"] = "loaded"
    if isinstance(payload, dict):
        meta["generated_at_utc"] = payload.get("generated_at_utc")
        meta["report_id"] = payload.get("report_id")
    return payload, meta


def _normalize_category(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    synonyms = {
        "nfp": "nonfarm_payrolls",
        "non_farm_payrolls": "nonfarm_payrolls",
        "fed_chair_testimony": "scheduled_fed_chair_testimony",
        "fed_chair": "scheduled_fed_chair_testimony",
        "chair_testimony": "scheduled_fed_chair_testimony",
        "fomc": "fomc_rate_decision",
    }
    return synonyms.get(text, text)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _extract_events(calendar_payload: Any) -> list[dict[str, Any]]:
    if isinstance(calendar_payload, list):
        return [event for event in calendar_payload if isinstance(event, dict)]
    payload = _as_dict(calendar_payload)
    for key in ("events", "macro_events", "calendar"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [event for event in rows if isinstance(event, dict)]
    return []


def _event_timestamp(event: dict[str, Any]) -> datetime | None:
    for key in ("event_timestamp_utc", "event_time_utc", "timestamp_utc", "event_timestamp", "scheduled_for_utc"):
        parsed = _parse_dt(event.get(key))
        if parsed:
            return parsed
    return None


def _event_known_at(event: dict[str, Any]) -> datetime | None:
    for key in ("known_at_utc", "announced_at_utc", "published_at_utc", "as_of_utc", "calendar_known_at_utc"):
        parsed = _parse_dt(event.get(key))
        if parsed:
            return parsed
    return None


def _find_leakage_keys(value: Any, *, prefix: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key).lower()
            path = f"{prefix}.{key}" if prefix else str(key)
            if key_text in EVENT_LEAKAGE_KEYS:
                hits.append(path)
            hits.extend(_find_leakage_keys(nested, prefix=path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            hits.extend(_find_leakage_keys(item, prefix=f"{prefix}[{index}]"))
    return hits


def _playbook_concept(playbook: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(playbook.get("concept"))


def _preregistration_reasons(playbook: dict[str, Any]) -> list[str]:
    concept = _playbook_concept(playbook)
    reasons: list[str] = []
    if playbook.get("status") != "preregistered_design_only":
        reasons.append("unexpected_status")
    if playbook.get("concept_id") != CONCEPT_ID:
        reasons.append("unexpected_concept_id")
    if playbook.get("structure") != EXPECTED_STRUCTURE:
        reasons.append("unexpected_structure")
    if playbook.get("accepted_profitability") is not False:
        reasons.append("accepted_profitability_not_false")
    if playbook.get("historical_replay_performed") is not False:
        reasons.append("historical_replay_performed_not_false")
    if playbook.get("lane_implementation_performed") is not False:
        reasons.append("lane_implementation_performed_not_false")
    if tuple(concept.get("initial_research_universe", ())) != INITIAL_RESEARCH_UNIVERSE:
        reasons.append("unexpected_initial_research_universe")
    if tuple(concept.get("future_extension_universe", ())) != FUTURE_EXTENSION_UNIVERSE:
        reasons.append("unexpected_future_extension_universe")
    if _normalize_categories(concept.get("event_categories")) != set(REQUIRED_EVENT_CATEGORIES):
        reasons.append("unexpected_event_categories")
    return reasons


def _normalize_categories(values: Any) -> set[str]:
    return {_normalize_category(value) for value in _as_list(values)}


def _event_calendar_assessment(payload: Any, meta: dict[str, Any]) -> dict[str, Any]:
    if meta.get("status") != "loaded":
        return {
            "status": "blocked",
            "blockers": ["missing_point_in_time_macro_event_calendar"],
            "event_count": 0,
            "covered_categories": [],
            "missing_categories": list(REQUIRED_EVENT_CATEGORIES),
            "leakage_keys": [],
            "point_in_time_failures": [],
        }
    payload_dict = _as_dict(payload)
    if payload_dict.get("status") == "blocked_macro_event_calendar_source_missing":
        return {
            "status": "blocked",
            "blockers": ["macro_event_calendar_source_missing"],
            "event_count": payload_dict.get("event_count", 0),
            "covered_categories": payload_dict.get("covered_categories", []),
            "missing_categories": payload_dict.get("missing_categories", list(REQUIRED_EVENT_CATEGORIES)),
            "leakage_keys": [],
            "point_in_time_failures": [],
        }
    if payload_dict.get("status") == "blocked_macro_event_calendar_validation":
        return {
            "status": "blocked",
            "blockers": ["macro_event_calendar_validation_failed"],
            "event_count": payload_dict.get("event_count", 0),
            "covered_categories": payload_dict.get("covered_categories", []),
            "missing_categories": payload_dict.get("missing_categories", list(REQUIRED_EVENT_CATEGORIES)),
            "leakage_keys": [],
            "point_in_time_failures": payload_dict.get("rejected_rows", []),
        }
    events = _extract_events(payload)
    covered = {_normalize_category(event.get("event_category") or event.get("category") or event.get("type")) for event in events}
    missing = sorted(set(REQUIRED_EVENT_CATEGORIES) - covered)
    leakage = _find_leakage_keys(events)
    point_in_time_failures: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        timestamp = _event_timestamp(event)
        known_at = _event_known_at(event)
        if not timestamp or not known_at or known_at > timestamp:
            point_in_time_failures.append(
                {
                    "index": index,
                    "event_id": event.get("event_id"),
                    "event_category": _normalize_category(event.get("event_category") or event.get("category")),
                    "reason": "missing_or_late_known_at_or_event_timestamp",
                }
            )
    blockers: list[str] = []
    if missing:
        blockers.append("missing_required_macro_event_categories")
    if point_in_time_failures:
        blockers.append("event_timestamp_not_point_in_time_before_candidate_entry")
    if leakage:
        blockers.append("event_calendar_leakage_fields_present")
    return {
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "event_count": len(events),
        "covered_categories": sorted(covered),
        "missing_categories": missing,
        "leakage_keys": leakage,
        "point_in_time_failures": point_in_time_failures,
    }


def _vix_bucket_assessment(
    vix_payload: Any,
    vix_meta: dict[str, Any],
    feature_payload: Any,
    feature_meta: dict[str, Any],
) -> dict[str, Any]:
    vix_dict = _as_dict(vix_payload)
    if vix_meta.get("status") == "loaded":
        status = vix_dict.get("status")
        available = vix_dict.get("point_in_time_vix_low_mid_bucket_available") is True
        blockers = [str(item) for item in _as_list(vix_dict.get("blockers"))]
        if status == "point_in_time_vix_bucket_ready" and available and not blockers:
            return {
                "status": "ready",
                "blockers": [],
                "vix_bucket_status": status,
                "point_in_time_vix_low_mid_bucket_available": True,
                "coverage_pct": vix_dict.get("coverage_pct"),
                "source_rows_count": vix_dict.get("source_rows_count"),
            }
        return {
            "status": "blocked",
            "blockers": blockers or ["missing_point_in_time_vix_bucket"],
            "vix_bucket_status": status,
            "point_in_time_vix_low_mid_bucket_available": False,
            "coverage_pct": vix_dict.get("coverage_pct"),
            "source_rows_count": vix_dict.get("source_rows_count"),
        }

    blockers: list[str] = []
    payload_dict = _as_dict(feature_payload)
    if feature_meta.get("status") != "loaded":
        blockers.append("missing_point_in_time_vix_bucket")
    elif not _has_vix_bucket(payload_dict):
        blockers.append("missing_point_in_time_vix_bucket")
    return {
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "feature_store_status": payload_dict.get("status"),
        "point_in_time_vix_low_mid_bucket_available": not blockers,
    }


def _has_vix_bucket(payload: dict[str, Any]) -> bool:
    if payload.get("point_in_time_vix_low_mid_bucket_available") is True:
        return True
    if payload.get("vix_bucket_point_in_time_available") is True:
        return True
    if payload.get("point_in_time_vix_bucket") in {"low", "mid", "low_mid", "low/mid"}:
        return True
    feature_contract = _as_dict(payload.get("feature_contract"))
    features = _as_list(feature_contract.get("features")) + _as_list(payload.get("features"))
    normalized = {str(item).lower() for item in features}
    return bool({"point_in_time_vix_bucket", "vix_bucket", "vix_low_mid_bucket"} & normalized)


def _holdout_assessment(payload: Any, meta: dict[str, Any]) -> dict[str, Any]:
    blockers = [] if meta.get("status") == "loaded" else ["missing_protected_holdout_guard"]
    return {
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
        "contract_loaded": meta.get("status") == "loaded",
        "protected_holdout_consumed": False,
    }


def _overall_status(preregistration_valid: bool, blockers: list[str]) -> str:
    if not preregistration_valid:
        return "invalid_preregistered_playbook_state"
    if blockers:
        return "blocked_macro_event_long_strangle_replay_readiness"
    return "ready_for_bounded_read_only_replay_nomination"


def _smallest_next_slice(blockers: list[str]) -> dict[str, str] | None:
    if not blockers:
        return None
    first = blockers[0]
    suggestions = {
        "missing_point_in_time_macro_event_calendar": "Build a read-only point-in-time macro-event calendar artifact for FOMC, CPI, PCE, payrolls, and Fed Chair testimony; do not replay or trade.",
        "missing_required_macro_event_categories": "Extend the point-in-time macro-event calendar fixture/artifact to cover the missing preregistered categories only.",
        "event_timestamp_not_point_in_time_before_candidate_entry": "Harden the macro-event calendar schema so event category and timestamp have known-at provenance before candidate entry.",
        "event_calendar_leakage_fields_present": "Strip or quarantine outcome, realized-move, future-IV, option-return, and P&L fields from candidate-generation inputs.",
        "missing_point_in_time_vix_bucket": "Add a read-only point-in-time VIX low/mid bucket readback; do not import quotes or mutate evidence stores.",
        "point_in_time_vix_source_missing": "Add trusted local-or-contract-declared point-in-time VIX source rows covering the requested feature-store dates; do not import quotes or mutate evidence stores.",
        "missing_vix_bucket_threshold_policy": "Add a frozen read-only VIX bucket threshold policy before accepting any VIX bucket readback.",
        "vix_bucket_date_coverage_incomplete": "Extend point-in-time VIX bucket coverage to every requested shared feature-store date before replay nomination.",
        "point_in_time_vix_row_validation_failed": "Fix rejected VIX bucket rows so provenance, known-at, leakage, and bucket fields pass the validator.",
        "missing_protected_holdout_guard": "Wire the protected-holdout contract into the readiness gate before any aggregation or replay.",
    }
    return {"blocker": first, "smallest_future_codex_slice": suggestions.get(first, "Clear exactly this named blocker with a read-only artifact before replay.")}


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    event_calendar_path: Path = DEFAULT_EVENT_CALENDAR,
    vix_bucket_path: Path = DEFAULT_VIX_BUCKET,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    playbook_payload, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    playbook = _as_dict(playbook_payload)
    event_calendar_payload, event_calendar_meta = _load_json(event_calendar_path, required=False)
    vix_bucket_payload, vix_bucket_meta = _load_json(vix_bucket_path, required=False)
    feature_store_payload, feature_store_meta = _load_json(feature_store_path, required=False)
    holdout_payload, holdout_meta = _load_json(holdout_contract_path, required=False)

    preregistration_reasons = (
        _preregistration_reasons(playbook) if playbook_meta.get("status") == "loaded" else ["missing_preregistered_playbook"]
    )
    preregistration_valid = not preregistration_reasons
    event_calendar = _event_calendar_assessment(event_calendar_payload, event_calendar_meta)
    vix_bucket = _vix_bucket_assessment(vix_bucket_payload, vix_bucket_meta, feature_store_payload, feature_store_meta)
    holdout = _holdout_assessment(holdout_payload, holdout_meta)

    blockers: list[str] = []
    if preregistration_valid:
        for assessment in (event_calendar, vix_bucket, holdout):
            blockers.extend(str(item) for item in _as_list(assessment.get("blockers")))

    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _overall_status(preregistration_valid, blockers),
        **READ_ONLY_FLAGS,
        "scope": "read_only_macro_event_long_strangle_replay_readiness_audit",
        "concept_id": playbook.get("concept_id"),
        "structure": playbook.get("structure"),
        "source_artifacts": {
            "preregistered_macro_event_long_strangle_playbook": playbook_meta,
            "macro_event_calendar": event_calendar_meta,
            "point_in_time_vix_bucket": vix_bucket_meta,
            "feature_store": feature_store_meta,
            "forward_holdout_contract": holdout_meta,
        },
        "preregistration_validation": {
            "valid": preregistration_valid,
            "reasons": preregistration_reasons,
            "required_status": "preregistered_design_only",
            "required_concept_id": CONCEPT_ID,
            "required_structure": EXPECTED_STRUCTURE,
        },
        "initial_research_universe": list(INITIAL_RESEARCH_UNIVERSE),
        "future_extension_universe": list(FUTURE_EXTENSION_UNIVERSE),
        "required_event_categories": list(REQUIRED_EVENT_CATEGORIES),
        "event_calendar_readiness": event_calendar,
        "vix_bucket_readiness": vix_bucket,
        "protected_holdout_readiness": holdout,
        "proof_formulas": {
            "entry_debit": "call_ask + put_ask for one straddle/strangle unit, using exact OPRA/NBBO ask on each long leg",
            "exit_value": "call_bid + put_bid for one straddle/strangle unit, using exact OPRA/NBBO bid on each long leg",
            "expiry_settlement_value": "max(0, underlying_settlement - call_strike) + max(0, put_strike - underlying_settlement)",
            "net_pnl_usd": "(exit_or_settlement_value - entry_debit) * 100 - fees_and_slippage",
        },
        "required_denominator_statuses": list(REQUIRED_DENOMINATOR_STATUSES),
        "strict_new_identity_schema": list(STRICT_NEW_IDENTITY_FIELDS),
        "candidate_entry_policy_invariants": [
            "event category and event timestamp must be known before candidate entry",
            "candidate entry must not read event outcome, realized move, realized volatility, future IV, option return, or P&L",
            "initial replay universe is SPY and QQQ only; IWM and DIA require a later proof-surface recheck",
            "VIX low/mid bucket must be point-in-time before entry",
            "all thresholds, DTE buckets, strike rules, liquidity gates, exits, and expiry settlement rules must be frozen before replay",
        ],
        "future_replay_pnl_convention": "Exact completed rows require contract-multiplier net USD P&L after fees and slippage, from side-aware bid/ask entry and side-aware exit or explicit expiry intrinsic settlement.",
        "future_replay_minimums": {
            "historical_exact_rows": 200,
            "latest_audit_exact_rows": 30,
            "quote_coverage_floor": 0.90,
            "pf_lower_bound_floor": 1.0,
            "stress_pf_floor": 1.0,
            "net_usd_pnl_must_be_positive": True,
        },
        "falsification_criteria": [
            "fewer than 200 historical exact rows after implementation",
            "fewer than 30 latest-audit exact rows",
            "quote coverage below 90 percent",
            "bootstrap PF lower bound less than or equal to 1.0",
            "stress PF below 1.0",
            "net USD P&L less than or equal to 0",
            "material single-ticker, event-category, month, date, or winner dependence",
            "event-calendar provenance, expiry settlement, strict-new identity, margin/max-loss, or protected-holdout handling unresolved",
        ],
        "blockers": blockers,
        "smallest_next_blocker_clearing_slice": _smallest_next_slice(blockers),
        "allowed_next_step": (
            "Send this readiness artifact back to GPT-5.5 Pro for continue/stop. A later bounded read-only replay "
            "requires a separate Codex task, and still cannot enable live validation, auto-track, broker orders, "
            "quote import, evidence mutation, protected-holdout consumption, scanner release, proof-bar changes, or promotion."
        ),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report["status"] not in {
        "ready_for_bounded_read_only_replay_nomination",
        "blocked_macro_event_long_strangle_replay_readiness",
        "invalid_preregistered_playbook_state",
    }:
        raise ValueError(f"unexpected status: {report['status']}")
    if report["preregistration_validation"]["valid"]:
        if report.get("concept_id") != CONCEPT_ID:
            raise ValueError("unexpected concept_id")
        if report.get("structure") != EXPECTED_STRUCTURE:
            raise ValueError("unexpected structure")
        missing_statuses = set(REQUIRED_DENOMINATOR_STATUSES) - set(report["required_denominator_statuses"])
        if missing_statuses:
            raise ValueError(f"missing denominator statuses: {sorted(missing_statuses)}")
        missing_identity = set(STRICT_NEW_IDENTITY_FIELDS) - set(report["strict_new_identity_schema"])
        if missing_identity:
            raise ValueError(f"missing strict-new identity fields: {sorted(missing_identity)}")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Macro-Event Long Strangle Replay Readiness",
        "",
        "This report is generated from `scripts/build_regular_options_macro_event_long_strangle_replay_readiness.py`. It is a read-only readiness audit for the preregistered macro-event long straddle/strangle concept. It does not run replay, import quotes, mutate evidence stores, create trades, enable live validation or auto-track, submit broker orders, change scanner or strategy logic, consume protected holdout, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Structure: `{report.get('structure')}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical replay performed: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Readiness audit performed: `{_fmt_bool(report['readiness_audit_performed'])}`.",
        "",
        "## Readiness",
        "",
        f"- Event calendar: `{report['event_calendar_readiness']['status']}`.",
        f"- VIX bucket: `{report['vix_bucket_readiness']['status']}`.",
        f"- Protected holdout guard: `{report['protected_holdout_readiness']['status']}`.",
        "",
        "## Blockers",
        "",
    ]
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Required Event Categories",
            "",
            *[f"- `{item}`" for item in _as_list(report.get("required_event_categories"))],
            "",
            "## Proof Formulas",
            "",
        ]
    )
    for key, value in _as_dict(report.get("proof_formulas")).items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Denominator Statuses", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("required_denominator_statuses")))
    lines.extend(["", "## Strict-New Identity", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("strict_new_identity_schema")))
    lines.extend(["", "## Smallest Next Slice", ""])
    smallest = report.get("smallest_next_blocker_clearing_slice")
    lines.append(json.dumps(smallest, indent=2, sort_keys=True) if smallest else "No blocker-clearing slice required before nomination.")
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
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
    parser = argparse.ArgumentParser(description="Build a read-only macro-event long strangle replay readiness audit.")
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--event-calendar", type=Path, default=DEFAULT_EVENT_CALENDAR)
    parser.add_argument("--vix-bucket", type=Path, default=DEFAULT_VIX_BUCKET)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        preregistered_playbook_path=args.preregistered_playbook,
        event_calendar_path=args.event_calendar,
        vix_bucket_path=args.vix_bucket,
        feature_store_path=args.feature_store,
        holdout_contract_path=args.holdout_contract,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["preregistration_validation"]["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
