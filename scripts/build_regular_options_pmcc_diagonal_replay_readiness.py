from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_pmcc_diagonal_replay_readiness"
CONCEPT_ID = "low_mid_vix_index_pmcc_diagonal_income_v1"
EXPECTED_STRUCTURE = "defined_risk_pmcc_style_call_diagonals_only"

DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT / "data" / "profitability-lab" / "regular-options-preregistered-pmcc-diagonal-playbook" / "latest.json"
)
DEFAULT_FEATURE_STORE = ROOT / "data" / "profitability-lab" / "regular-options-feature-store" / "latest.json"
DEFAULT_POINT_IN_TIME_VIX_BUCKET = (
    ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-vix-bucket" / "latest.json"
)
DEFAULT_BASE_CLEAN_STACK_IDENTITY_LEDGER = (
    ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger" / "latest.json"
)
DEFAULT_FORWARD_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_OPTIONS_HISTORY_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-pmcc-diagonal-replay-readiness"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-pmcc-diagonal-replay-readiness.md"

READ_ONLY_FLAGS = {
    "read_only": True,
    "research_only": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
    "replay_performed": False,
    "lane_implementation_performed": False,
    "scanner_policy_changed": False,
    "production_scanner_changed": False,
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
    "historical_rows_are_forward_proof": False,
    "undefined_or_uncapped_short_call_risk_allowed": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_implement_scanner_or_playbook_logic",
    "do_not_run_pmcc_replay",
    "do_not_create_trades",
    "do_not_prepare_or_submit_broker_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_import_quotes",
    "do_not_mutate_options_history_db",
    "do_not_mutate_evidence_stores",
    "do_not_consume_protected_holdout",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_promote_any_lane",
    "do_not_allow_naked_or_undefined_risk_short_calls",
    "do_not_invent_point_in_time_trend_vix_or_known_at_inputs",
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
    meta["generated_at_utc"] = payload.get("generated_at_utc") or payload.get("last_updated")
    meta["report_id"] = payload.get("report_id") or payload.get("contract_id")
    meta["status_value"] = payload.get("status")
    return payload, meta


def _contains_all(payload: dict[str, Any], terms: tuple[str, ...]) -> bool:
    text = json.dumps(payload, sort_keys=True).lower()
    return all(term.lower() in text for term in terms)


def _assessment(
    *,
    prerequisite_id: str,
    label: str,
    critical: bool,
    status: str,
    blocker: str | None,
    evidence: list[dict[str, Any]],
    note: str,
) -> dict[str, Any]:
    return {
        "prerequisite_id": prerequisite_id,
        "label": label,
        "critical": critical,
        "status": status,
        "blocker": blocker if status != "ready" else None,
        "evidence": evidence,
        "note": note,
    }


def _preregistration_valid(playbook: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    concept = _as_dict(playbook.get("concept"))
    if playbook.get("report_id") != "regular_options_preregistered_pmcc_diagonal_playbook":
        reasons.append("unexpected_report_id")
    if playbook.get("concept_id") != CONCEPT_ID:
        reasons.append("unexpected_concept_id")
    if playbook.get("status") != "preregistered_design_only":
        reasons.append("unexpected_status")
    if playbook.get("structure") != EXPECTED_STRUCTURE:
        reasons.append("unexpected_structure")
    if playbook.get("accepted_profitability") is not False:
        reasons.append("accepted_profitability_not_false")
    if playbook.get("historical_replay_performed") is not False:
        reasons.append("historical_replay_performed_not_false")
    if playbook.get("lane_implementation_performed") is not False:
        reasons.append("lane_implementation_performed_not_false")
    if playbook.get("undefined_or_uncapped_short_call_risk_allowed") is not False:
        reasons.append("undefined_or_uncapped_short_call_risk_not_false")
    if concept and concept.get("undefined_or_uncapped_short_call_risk_allowed") is not False:
        reasons.append("concept_undefined_or_uncapped_short_call_risk_not_false")
    return not reasons, reasons


def _safe_relative_db_uri(path: Path) -> str:
    return f"file:{path.resolve().as_posix()}?mode=ro"


def inspect_options_history_db(path: Path) -> dict[str, Any]:
    inventory: dict[str, Any] = {
        "path": _rel(path),
        "exists": path.exists(),
        "read_only_confirmed": False,
        "status": "missing" if not path.exists() else "unread",
        "trusted_call_quote_row_count": 0,
        "underlyings_with_trusted_calls": [],
        "long_dte_call_row_count": 0,
        "short_dte_call_row_count": 0,
        "pmcc_diagonal_quote_surface_status": "missing",
    }
    if not path.exists():
        return inventory
    try:
        with sqlite3.connect(_safe_relative_db_uri(path), uri=True) as conn:
            conn.execute("PRAGMA query_only = ON")
            inventory["read_only_confirmed"] = True
            row = conn.execute(
                """
                SELECT
                  COUNT(*) AS total_rows,
                  COUNT(DISTINCT q.underlying) AS underlying_count,
                  SUM(CASE WHEN julianday(q.expiry) - julianday(q.quote_date_et) >= 120 THEN 1 ELSE 0 END) AS long_rows,
                  SUM(CASE WHEN julianday(q.expiry) - julianday(q.quote_date_et) BETWEEN 14 AND 60 THEN 1 ELSE 0 END) AS short_rows
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
                WHERE b.source_label = 'thetadata_opra_nbbo_1m'
                  AND b.data_trust = 'trusted'
                  AND q.snapshot_kind = 'intraday'
                  AND q.underlying IN ('SPY','QQQ')
                  AND q.option_type = 'call'
                  AND q.bid IS NOT NULL
                  AND q.ask IS NOT NULL
                  AND q.ask > 0
                """
            ).fetchone()
            underlyings = [
                item[0]
                for item in conn.execute(
                    """
                    SELECT DISTINCT q.underlying
                    FROM option_quote_snapshots q
                    JOIN import_batches b ON b.id = q.source_batch_id
                    WHERE b.source_label = 'thetadata_opra_nbbo_1m'
                      AND b.data_trust = 'trusted'
                      AND q.snapshot_kind = 'intraday'
                      AND q.underlying IN ('SPY','QQQ')
                      AND q.option_type = 'call'
                      AND q.bid IS NOT NULL
                      AND q.ask IS NOT NULL
                      AND q.ask > 0
                    ORDER BY q.underlying
                    """
                ).fetchall()
            ]
    except sqlite3.Error as exc:
        inventory["status"] = "sqlite_error"
        inventory["error"] = type(exc).__name__
        return inventory
    total_rows = int(row[0] or 0) if row else 0
    long_rows = int(row[2] or 0) if row else 0
    short_rows = int(row[3] or 0) if row else 0
    inventory.update(
        {
            "status": "loaded",
            "trusted_call_quote_row_count": total_rows,
            "underlyings_with_trusted_calls": underlyings,
            "long_dte_call_row_count": long_rows,
            "short_dte_call_row_count": short_rows,
            "pmcc_diagonal_quote_surface_status": "ready"
            if set(underlyings) == {"QQQ", "SPY"} and long_rows > 0 and short_rows > 0
            else "blocked",
        }
    )
    return inventory


def _vix_status(vix_bucket: dict[str, Any], vix_meta: dict[str, Any]) -> tuple[str, str | None, list[dict[str, Any]], str]:
    evidence = [{"path": vix_meta["path"], "matched_terms": [str(vix_bucket.get("status"))]}]
    if vix_bucket.get("point_in_time_vix_low_mid_bucket_available") is True and not vix_bucket.get("blockers"):
        return "ready", None, evidence, "Point-in-time VIX low/mid bucket artifact is ready."
    if vix_meta.get("status") == "loaded":
        evidence[0]["blockers"] = vix_bucket.get("blockers")
        return "blocked", "point_in_time_vix_bucket_blocked", evidence, "Existing VIX bucket artifact is loaded but blocked."
    return "missing", "missing_point_in_time_vix_bucket", evidence, "No point-in-time VIX bucket artifact is available."


def _trend_regime_status(playbook: dict[str, Any], feature_store: dict[str, Any]) -> tuple[str, str, list[dict[str, Any]], str]:
    playbook_has_requirement = _contains_all(playbook, ("trend", "known point-in-time"))
    feature_has_inputs = _contains_all(feature_store, ("underlying_return", "trend")) or _contains_all(
        feature_store, ("market_regime", "tradable_after_time")
    )
    evidence = [
        {"path": _rel(DEFAULT_PREREGISTERED_PLAYBOOK), "matched_terms": ["trend"] if playbook_has_requirement else []},
        {"path": _rel(DEFAULT_FEATURE_STORE), "matched_terms": ["trend_inputs"] if feature_has_inputs else []},
    ]
    if feature_has_inputs:
        return "ready", "", evidence, "Point-in-time trend/regime inputs appear available."
    return (
        "blocked",
        "missing_point_in_time_trend_or_regime_inputs",
        evidence,
        "The preregistered PMCC design requires point-in-time trend/regime inputs, but the current feature store is quote-surface only.",
    )


def _build_prerequisite_assessments(
    *,
    playbook: dict[str, Any],
    feature_store: dict[str, Any],
    vix_bucket: dict[str, Any],
    vix_meta: dict[str, Any],
    base_ledger: dict[str, Any],
    base_ledger_meta: dict[str, Any],
    holdout_meta: dict[str, Any],
    db_inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    trend_status, trend_blocker, trend_evidence, trend_note = _trend_regime_status(playbook, feature_store)
    vix_status, vix_blocker, vix_evidence, vix_note = _vix_status(vix_bucket, vix_meta)
    quote_ready = db_inventory.get("pmcc_diagonal_quote_surface_status") == "ready"
    base_ready = (
        base_ledger_meta.get("status") == "loaded"
        and base_ledger.get("status") == "base_clean_stack_identity_ledger_ready"
        and base_ledger.get("unique_identity_count") == 157
        and base_ledger.get("duplicate_identity_count") == 0
    )
    holdout_ready = holdout_meta.get("status") == "loaded"
    formulas_ready = _contains_all(
        playbook,
        ("entry_debit", "roll_debit_or_credit", "exit_value_with_open_short", "net_pnl_usd"),
    )
    assignment_ready = _contains_all(playbook, ("assignment", "ex-dividend", "expiration", "roll"))
    max_loss_ready = _contains_all(playbook, ("max_loss_usd", "required collateral", "undefined-risk"))
    denominator_ready = _contains_all(
        playbook,
        (
            "no_candidate",
            "missing_leg_quote",
            "exact_entry_captured",
            "short_call_roll_captured",
            "assignment_or_ex_dividend_blocked",
            "exact_exit_captured",
            "missing_exit",
        ),
    )
    return [
        _assessment(
            prerequisite_id="valid_preregistered_pmcc_playbook",
            label="Valid preregistered PMCC playbook",
            critical=True,
            status="ready",
            blocker=None,
            evidence=[{"path": _rel(DEFAULT_PREREGISTERED_PLAYBOOK), "matched_terms": [CONCEPT_ID, EXPECTED_STRUCTURE]}],
            note="The design artifact is loaded and validates separately before these checks run.",
        ),
        _assessment(
            prerequisite_id="point_in_time_trend_or_regime_inputs",
            label="Point-in-time trend or regime inputs",
            critical=True,
            status=trend_status,
            blocker=trend_blocker or None,
            evidence=trend_evidence,
            note=trend_note,
        ),
        _assessment(
            prerequisite_id="point_in_time_vix_bucket",
            label="Point-in-time VIX low/mid bucket",
            critical=True,
            status=vix_status,
            blocker=vix_blocker,
            evidence=vix_evidence,
            note=vix_note,
        ),
        _assessment(
            prerequisite_id="trusted_pmcc_diagonal_quote_surface",
            label="Trusted OPRA/NBBO long-call and short-call quote surface",
            critical=True,
            status="ready" if quote_ready else "blocked",
            blocker=None if quote_ready else "missing_trusted_pmcc_diagonal_quote_surface",
            evidence=[db_inventory],
            note="Read-only DB inspection checks trusted SPY/QQQ call rows in both long-DTE and short-DTE buckets.",
        ),
        _assessment(
            prerequisite_id="side_aware_diagonal_formulas_registered",
            label="Side-aware diagonal entry, roll, exit, and expiry formulas",
            critical=True,
            status="ready" if formulas_ready else "blocked",
            blocker=None if formulas_ready else "missing_side_aware_diagonal_formula_registration",
            evidence=[{"path": _rel(DEFAULT_PREREGISTERED_PLAYBOOK), "matched_terms": ["entry_debit", "roll_debit_or_credit", "net_pnl_usd"]}],
            note="This only proves formulas are preregistered; it does not run replay.",
        ),
        _assessment(
            prerequisite_id="short_call_roll_assignment_ex_dividend_handling",
            label="Short-call roll, assignment, ex-dividend, and expiration handling",
            critical=True,
            status="ready" if assignment_ready else "blocked",
            blocker=None if assignment_ready else "missing_short_call_roll_assignment_ex_dividend_handling",
            evidence=[{"path": _rel(DEFAULT_PREREGISTERED_PLAYBOOK), "matched_terms": ["assignment", "ex-dividend", "expiration", "roll"]}],
            note="The current slice records readiness only; future replay still needs implementation.",
        ),
        _assessment(
            prerequisite_id="max_loss_collateral_convention",
            label="Max-loss and collateral convention",
            critical=True,
            status="ready" if max_loss_ready else "blocked",
            blocker=None if max_loss_ready else "missing_pmcc_max_loss_or_collateral_convention",
            evidence=[{"path": _rel(DEFAULT_PREREGISTERED_PLAYBOOK), "matched_terms": ["max_loss_usd", "required collateral"]}],
            note="Undefined or uncapped short-call exposure remains forbidden.",
        ),
        _assessment(
            prerequisite_id="full_denominator_mapping",
            label="Full denominator status mapping",
            critical=True,
            status="ready" if denominator_ready else "blocked",
            blocker=None if denominator_ready else "missing_full_denominator_mapping",
            evidence=[{"path": _rel(DEFAULT_PREREGISTERED_PLAYBOOK), "matched_terms": ["denominator_statuses"]}],
            note="Denominator registration is not replay or profitability proof.",
        ),
        _assessment(
            prerequisite_id="strict_new_dedupe_against_base_clean_stack",
            label="Strict-new dedupe against the 157-row clean base stack",
            critical=True,
            status="ready" if base_ready else "blocked",
            blocker=None if base_ready else "missing_strict_new_dedupe_against_base_clean_stack",
            evidence=[{"path": base_ledger_meta["path"], "matched_terms": [str(base_ledger.get("status"))]}],
            note="Future PMCC rows must remain strict-new before count claims.",
        ),
        _assessment(
            prerequisite_id="protected_holdout_guard",
            label="Protected-holdout guard",
            critical=True,
            status="ready" if holdout_ready else "missing",
            blocker=None if holdout_ready else "missing_protected_holdout_guard",
            evidence=[{"path": holdout_meta["path"], "matched_terms": [str(holdout_meta.get("status"))]}],
            note="This readiness slice does not consume protected holdout.",
        ),
        _assessment(
            prerequisite_id="proof_boundary_labeling",
            label="Proof-boundary labeling",
            critical=True,
            status="ready",
            blocker=None,
            evidence=[{"path": "generated_report", "matched_terms": ["readiness is not replay", "not profitability", "not forward proof", "not promotion"]}],
            note="The generated artifact carries fail-closed proof-boundary labels.",
        ),
    ]


def _overall_status(assessments: list[dict[str, Any]], prereg_valid: bool) -> str:
    if not prereg_valid:
        return "blocked_invalid_pmcc_diagonal_preregistration"
    if any(row["critical"] and row["status"] != "ready" for row in assessments):
        return "blocked_pmcc_diagonal_replay_readiness"
    return "pmcc_diagonal_replay_readiness_ready"


def _smallest_next_blocker(blockers: list[str]) -> str | None:
    priority = [
        "missing_point_in_time_trend_or_regime_inputs",
        "point_in_time_vix_bucket_blocked",
        "missing_point_in_time_vix_bucket",
        "missing_trusted_pmcc_diagonal_quote_surface",
        "missing_side_aware_diagonal_formula_registration",
        "missing_short_call_roll_assignment_ex_dividend_handling",
        "missing_pmcc_max_loss_or_collateral_convention",
    ]
    for item in priority:
        if item in blockers:
            return item
    return blockers[0] if blockers else None


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    feature_store_path: Path = DEFAULT_FEATURE_STORE,
    point_in_time_vix_bucket_path: Path = DEFAULT_POINT_IN_TIME_VIX_BUCKET,
    base_clean_stack_identity_ledger_path: Path = DEFAULT_BASE_CLEAN_STACK_IDENTITY_LEDGER,
    forward_holdout_contract_path: Path = DEFAULT_FORWARD_HOLDOUT_CONTRACT,
    options_history_db_path: Path = DEFAULT_OPTIONS_HISTORY_DB,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    feature_store, feature_store_meta = _load_json(feature_store_path, required=True)
    vix_bucket, vix_bucket_meta = _load_json(point_in_time_vix_bucket_path, required=False)
    base_ledger, base_ledger_meta = _load_json(base_clean_stack_identity_ledger_path, required=False)
    holdout_contract, holdout_meta = _load_json(forward_holdout_contract_path, required=False)
    db_inventory = inspect_options_history_db(options_history_db_path)
    prereg_valid, prereg_reasons = (
        _preregistration_valid(playbook) if playbook_meta["status"] == "loaded" else (False, ["missing_preregistration_artifact"])
    )
    assessments = (
        _build_prerequisite_assessments(
            playbook=playbook,
            feature_store=feature_store,
            vix_bucket=vix_bucket,
            vix_meta=vix_bucket_meta,
            base_ledger=base_ledger,
            base_ledger_meta=base_ledger_meta,
            holdout_meta=holdout_meta,
            db_inventory=db_inventory,
        )
        if prereg_valid
        else []
    )
    blockers = [
        row["blocker"]
        for row in assessments
        if row.get("critical") and row.get("status") != "ready" and row.get("blocker")
    ]
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": _overall_status(assessments, prereg_valid),
        **READ_ONLY_FLAGS,
        "scope": "read_only_pmcc_diagonal_replay_readiness_audit",
        "concept_id": playbook.get("concept_id") if playbook else None,
        "structure": playbook.get("structure") if playbook else None,
        "initial_research_universe": _as_dict(playbook.get("concept")).get("initial_research_universe"),
        "future_extension_universe": _as_dict(playbook.get("concept")).get("future_extension_universe"),
        "source_artifacts": {
            "preregistered_pmcc_diagonal_playbook": playbook_meta,
            "feature_store": feature_store_meta,
            "point_in_time_vix_bucket": vix_bucket_meta,
            "base_clean_stack_identity_ledger": base_ledger_meta,
            "forward_holdout_contract": holdout_meta,
            "options_history_db": db_inventory,
        },
        "preregistration_validation": {
            "valid": prereg_valid,
            "reasons": prereg_reasons,
            "required_report_id": "regular_options_preregistered_pmcc_diagonal_playbook",
            "required_concept_id": CONCEPT_ID,
            "required_status": "preregistered_design_only",
            "required_structure": EXPECTED_STRUCTURE,
            "undefined_or_uncapped_short_call_risk_allowed_required": False,
        },
        "critical_prerequisites": assessments,
        "blockers": blockers,
        "smallest_next_blocker_clearing_slice": _smallest_next_blocker(blockers),
        "holdout_contract_loaded": bool(holdout_contract),
        "allowed_next_step": (
            "Return this readiness artifact to GPT-5.5 Pro for continue/stop. Do not proceed to PMCC replay inside "
            "this task. If ready, the next loop decision is a separate bounded no-write research replay decision; if "
            "blocked, park PMCC on the exact blockers and select the next materially different branch."
        ),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report["preregistration_validation"]["valid"]:
        if report.get("concept_id") != CONCEPT_ID:
            raise ValueError("unexpected concept_id")
        if report.get("structure") != EXPECTED_STRUCTURE:
            raise ValueError("unexpected structure")
        if report.get("undefined_or_uncapped_short_call_risk_allowed") is not False:
            raise ValueError("undefined_or_uncapped_short_call_risk_allowed must be false")
        required_ids = {
            "valid_preregistered_pmcc_playbook",
            "point_in_time_trend_or_regime_inputs",
            "point_in_time_vix_bucket",
            "trusted_pmcc_diagonal_quote_surface",
            "side_aware_diagonal_formulas_registered",
            "short_call_roll_assignment_ex_dividend_handling",
            "max_loss_collateral_convention",
            "full_denominator_mapping",
            "strict_new_dedupe_against_base_clean_stack",
            "protected_holdout_guard",
            "proof_boundary_labeling",
        }
        seen = {row.get("prerequisite_id") for row in report["critical_prerequisites"]}
        missing = required_ids - seen
        if missing:
            raise ValueError(f"missing prerequisite assessments: {sorted(missing)}")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options PMCC Diagonal Replay Readiness",
        "",
        "This report is generated from `scripts/build_regular_options_pmcc_diagonal_replay_readiness.py`. It is a read-only readiness audit for a preregistered PMCC-style defined-risk call diagonal concept. It does not run replay, create trades, import quotes, mutate evidence stores, consume protected holdout, change scanner/strategy/stops/sizing/proof bars, enable live validation or auto-track, prepare or submit broker orders, allow naked or undefined-risk short calls, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Structure: `{report.get('structure')}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Historical replay performed: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Replay performed: `{_fmt_bool(report['replay_performed'])}`.",
        f"- Smallest next blocker-clearing slice: `{report.get('smallest_next_blocker_clearing_slice')}`.",
        "",
        "## Preregistration Validation",
        "",
        f"- Valid: `{_fmt_bool(report['preregistration_validation']['valid'])}`.",
        f"- Reasons: `{json.dumps(report['preregistration_validation']['reasons'])}`.",
        "",
        "## Critical Prerequisites",
        "",
        "| Prerequisite | Status | Blocker | Evidence |",
        "| --- | --- | --- | --- |",
    ]
    for row in _as_list(report.get("critical_prerequisites")):
        row = _as_dict(row)
        evidence_paths = ", ".join(f"`{item.get('path')}`" for item in _as_list(row.get("evidence"))[:4])
        lines.append(
            f"| {row.get('label')} | `{row.get('status')}` | `{row.get('blocker')}` | {evidence_paths or '-'} |"
        )
    lines.extend(["", "## Blockers", ""])
    if report.get("blockers"):
        lines.extend(f"- `{item}`" for item in _as_list(report.get("blockers")))
    else:
        lines.append("- None.")
    lines.extend(["", "## Boundary", "", report["allowed_next_step"], "", "## Forbidden Actions", ""])
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
    parser = argparse.ArgumentParser(description="Build a read-only PMCC diagonal replay readiness audit.")
    parser.add_argument("--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK)
    parser.add_argument("--feature-store", type=Path, default=DEFAULT_FEATURE_STORE)
    parser.add_argument("--point-in-time-vix-bucket", type=Path, default=DEFAULT_POINT_IN_TIME_VIX_BUCKET)
    parser.add_argument("--base-clean-stack-identity-ledger", type=Path, default=DEFAULT_BASE_CLEAN_STACK_IDENTITY_LEDGER)
    parser.add_argument("--forward-holdout-contract", type=Path, default=DEFAULT_FORWARD_HOLDOUT_CONTRACT)
    parser.add_argument("--options-history-db", type=Path, default=DEFAULT_OPTIONS_HISTORY_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        preregistered_playbook_path=args.preregistered_playbook,
        feature_store_path=args.feature_store,
        point_in_time_vix_bucket_path=args.point_in_time_vix_bucket,
        base_clean_stack_identity_ledger_path=args.base_clean_stack_identity_ledger,
        forward_holdout_contract_path=args.forward_holdout_contract,
        options_history_db_path=args.options_history_db,
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
