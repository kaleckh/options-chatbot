from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_flow_extreme_denominator_dedupe_bridge"
CONCEPT_ID = "index_flow_extreme_mean_reversion_ratio_backspread_v1"
STRUCTURE = "ratio_backspread_bounded"

DEFAULT_PRICING_CAPABILITY = (
    ROOT / "data" / "profitability-lab" / "regular-options-multi-leg-side-aware-pricing-capability" / "latest.json"
)
DEFAULT_FRONTIER = ROOT / "data" / "profitability-lab" / "regular-options-countable-throughput-frontier" / "latest.json"
DEFAULT_BASE_CLEAN_STACK_IDENTITY_LEDGER = (
    ROOT / "data" / "profitability-lab" / "regular-options-base-clean-stack-identity-ledger" / "latest.json"
)
DEFAULT_MANIFEST = ROOT / "tests" / "fixtures" / "regular_options_flow_extreme_denominator_dedupe" / "bridge_cases.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-flow-extreme-denominator-dedupe-bridge"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-flow-extreme-denominator-dedupe-bridge.md"

PROTECTED_HOLDOUT_START = "2026-06-05"

DENOMINATOR_STATUSES = (
    "candidate_not_generated_missing_flow_input",
    "candidate_not_generated_missing_vix_bucket",
    "candidate_rejected_missing_required_flow_fields",
    "candidate_rejected_missing_vix_bucket",
    "candidate_rejected_unbounded_or_undefined_risk",
    "candidate_rejected_missing_leg_quote",
    "candidate_rejected_zero_bid_or_untradable",
    "candidate_rejected_crossed_or_stale_quote",
    "candidate_duplicate_existing_base_stack",
    "candidate_duplicate_within_research_harness",
    "candidate_protected_holdout_overlap",
    "priced_fixture_not_proof_eligible",
    "readiness_candidate_priced_not_replayed",
    "no_pick_explicit",
    "blocked_source_missing",
)

IDENTITY_FIELDS = (
    "concept_id",
    "structure",
    "underlying",
    "signal_date",
    "planned_entry_timestamp",
    "option_rights",
    "expirations",
    "strikes",
    "leg_sides",
    "leg_ratios",
    "entry_policy",
    "exit_policy",
    "candidate_source_id",
)

BANNED_IDENTITY_FIELDS = {
    "realized_pnl",
    "realized_pnl_usd",
    "net_pnl",
    "net_pnl_usd",
    "pnl_percent",
    "future_move",
    "source_mark",
    "exit_result",
    "exit_pnl",
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
    "fixture_source_not_proof_eligible": True,
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
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_count_fixture_rows_as_profitability_or_forward_proof",
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


def _fixture_rows(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(manifest.get("candidates"), list):
        return [_as_dict(row) for row in manifest["candidates"]]
    if isinstance(manifest.get("fixtures"), list):
        return [_as_dict(row) for row in manifest["fixtures"]]
    return []


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _normal_leg(leg: dict[str, Any]) -> dict[str, Any]:
    return {
        "option_right": _norm(leg.get("option_right") or leg.get("right")).lower(),
        "expiration": _norm(leg.get("expiration") or leg.get("expiry")),
        "strike": str(leg.get("strike")),
        "side": _norm(leg.get("side")).lower(),
        "ratio": str(leg.get("ratio") or leg.get("quantity")),
    }


def identity_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    legs = sorted(
        [_normal_leg(_as_dict(leg)) for leg in _as_list(candidate.get("legs"))],
        key=lambda item: (item["expiration"], item["strike"], item["option_right"], item["side"], item["ratio"]),
    )
    return {
        "concept_id": _norm(candidate.get("concept_id")),
        "structure": _norm(candidate.get("structure")),
        "underlying": _norm(candidate.get("underlying")).upper(),
        "signal_date": _norm(candidate.get("signal_date")),
        "planned_entry_timestamp": _norm(candidate.get("planned_entry_timestamp")),
        "option_rights": [leg["option_right"] for leg in legs],
        "expirations": [leg["expiration"] for leg in legs],
        "strikes": [leg["strike"] for leg in legs],
        "leg_sides": [leg["side"] for leg in legs],
        "leg_ratios": [leg["ratio"] for leg in legs],
        "entry_policy": _norm(candidate.get("entry_policy")),
        "exit_policy": _norm(candidate.get("exit_policy")),
        "candidate_source_id": _norm(candidate.get("candidate_source_id")),
    }


def identity_hash(candidate: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(identity_payload(candidate)).encode("utf8")).hexdigest()


def _missing_identity_fields(payload: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in IDENTITY_FIELDS:
        value = payload.get(field)
        if value in ("", [], None):
            missing.append(field)
    return missing


def _pricing_capability_status(capability: dict[str, Any], meta: dict[str, Any]) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if meta.get("status") != "loaded":
        return "blocked", ["missing_multi_leg_side_aware_pricing_capability"]
    if capability.get("report_id") != "regular_options_multi_leg_side_aware_pricing_capability":
        blockers.append("invalid_multi_leg_side_aware_pricing_capability")
    unsafe_flags = [
        flag
        for flag in (
            "accepted_profitability",
            "historical_replay_performed",
            "historical_rows_are_forward_proof",
            "live_validation_enabled",
            "auto_track_enabled",
            "broker_order_allowed",
            "quotes_imported",
            "evidence_stores_mutated",
            "options_history_db_mutated",
            "protected_holdout_consumed",
            "production_scanner_changed",
            "strategy_logic_changed",
            "stops_changed",
            "sizing_changed",
            "proof_bars_changed",
            "promotion_ready",
        )
        if capability.get(flag) is not False
    ]
    if unsafe_flags:
        blockers.append("unsafe_multi_leg_side_aware_pricing_capability")
    ratio = _as_dict(_as_dict(capability.get("structure_support")).get("ratio_backspread_bounded"))
    if (
        capability.get("status") != "multi_leg_side_aware_pricing_capability_available"
        or ratio.get("status") != "available"
        or ratio.get("denominator_mapping_status") != "ready"
        or capability.get("pricing_capability_blockers")
    ):
        blockers.append("multi_leg_side_aware_pricing_capability_not_ready")
    if capability.get("fixture_source_not_proof_eligible") is not True:
        blockers.append("pricing_fixture_source_not_isolated_from_proof")
    return ("ready", []) if not blockers else ("blocked", sorted(set(blockers)))


def _base_identity_status(base: dict[str, Any], meta: dict[str, Any]) -> tuple[str, set[str], list[str]]:
    if meta.get("status") != "loaded":
        return "blocked", set(), ["base_stack_identity_ledger_missing"]
    hashes = base.get("identity_hashes")
    clean_hashes = {str(item) for item in hashes if str(item)} if isinstance(hashes, list) else set()
    if base.get("report_id") == "regular_options_base_clean_stack_identity_ledger":
        blockers = list(base.get("blockers") or [])
        expected = int(base.get("expected_base_clean_stack_exact_rows") or 0)
        ledger_count = int(base.get("ledger_row_count") or 0)
        unique_count = int(base.get("unique_identity_count") or 0)
        unsafe_flags = [
            flag
            for flag in (
                "accepted_profitability",
                "historical_replay_performed",
                "replay_performed",
                "historical_rows_are_forward_proof",
                "live_validation_enabled",
                "auto_track_enabled",
                "broker_order_allowed",
                "quotes_imported",
                "evidence_stores_mutated",
                "protected_holdout_consumed",
                "production_scanner_changed",
                "strategy_logic_changed",
                "stops_changed",
                "sizing_changed",
                "proof_bars_changed",
                "promotion_ready",
            )
            if base.get(flag) is not False
        ]
        if base.get("read_only") is not True or base.get("research_only") is not True:
            blockers.append("base_clean_stack_identity_ledger_not_read_only")
        if base.get("status") != "base_clean_stack_identity_ledger_ready":
            blockers.append("base_clean_stack_identity_ledger_not_ready")
        if expected != 157 or ledger_count != 157 or unique_count != 157:
            blockers.append("base_clean_stack_identity_ledger_count_mismatch")
        if base.get("duplicate_identity_count") != 0:
            blockers.append("duplicate_base_identity_hashes")
        if base.get("missing_identity_field_row_count") != 0:
            blockers.append("missing_required_identity_fields")
        if base.get("future_or_outcome_field_dependency_count") != 0:
            blockers.append("future_field_dependency_detected")
        if base.get("protected_holdout_overlap_count") != 0:
            blockers.append("protected_holdout_overlap_detected")
        if unsafe_flags:
            blockers.append("unsafe_base_clean_stack_identity_ledger")
        if not clean_hashes:
            blockers.append("base_stack_identity_ledger_empty")
        if blockers:
            return "blocked", clean_hashes, sorted(set(str(item) for item in blockers))
        return "ready", clean_hashes, []
    if isinstance(hashes, list):
        if base.get("status") in (None, "ready", "base_stack_identity_ledger_ready") and clean_hashes:
            return "ready", clean_hashes, []
        return "blocked", clean_hashes, ["base_stack_identity_ledger_empty"]
    if base.get("report_id") == "regular_options_countable_throughput_frontier":
        if "strict_new_row_level_identity_ledger_missing" in _canonical_json(base):
            return "blocked", set(), ["base_stack_identity_ledger_missing", "strict_new_row_level_identity_ledger_missing"]
        return "blocked", set(), ["base_stack_identity_ledger_missing"]
    return "blocked", set(), ["base_stack_identity_ledger_missing"]


def _denominator_mapping_status(manifest: dict[str, Any], candidates: list[dict[str, Any]]) -> tuple[str, list[str]]:
    declared = manifest.get("denominator_status_contract")
    if declared is None:
        declared = DENOMINATOR_STATUSES
    present = {str(item) for item in _as_list(declared)}
    missing = [status for status in DENOMINATOR_STATUSES if status not in present]
    for candidate in candidates:
        candidate_declared = candidate.get("denominator_status_mapping")
        if candidate_declared is None:
            continue
        candidate_present = {str(item) for item in _as_dict(candidate_declared)}
        missing.extend(status for status in DENOMINATOR_STATUSES if status not in candidate_present)
    unique_missing = sorted(set(missing))
    return ("ready", []) if not unique_missing else ("blocked", unique_missing)


def _candidate_blockers(candidate: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if candidate.get("concept_id") != CONCEPT_ID:
        blockers.append("invalid_concept_id")
    if candidate.get("structure") != STRUCTURE:
        blockers.append("invalid_structure")
    if candidate.get("bounded_risk") is not True or candidate.get("undefined_risk_allowed") is not False:
        blockers.append("candidate_rejected_unbounded_or_undefined_risk")
    if candidate.get("fixture_source_not_proof_eligible") is not True:
        blockers.append("fixture_source_not_proof_eligible_not_true")
    if candidate.get("protected_holdout_overlap") is True or _norm(candidate.get("signal_date")) >= PROTECTED_HOLDOUT_START:
        blockers.append("candidate_protected_holdout_overlap")
    missing = _missing_identity_fields(payload)
    if missing:
        blockers.append("missing_identity_field")
        candidate["_missing_identity_fields"] = missing
    declared_identity_fields = {str(item) for item in _as_list(candidate.get("identity_fields"))}
    if declared_identity_fields.intersection(BANNED_IDENTITY_FIELDS):
        blockers.append("leaky_identity_or_future_field_present")
    return sorted(set(blockers))


def _evaluate_candidates(candidates: list[dict[str, Any]], base_hashes: set[str]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        payload = identity_payload(candidate)
        row_hash = hashlib.sha256(_canonical_json(payload).encode("utf8")).hexdigest()
        blockers = _candidate_blockers(candidate, payload)
        if row_hash in base_hashes:
            blockers.append("candidate_duplicate_existing_base_stack")
        if row_hash in seen:
            blockers.append("candidate_duplicate_within_research_harness")
        seen.add(row_hash)
        status = "readiness_candidate_priced_not_replayed" if not blockers else sorted(set(blockers))[0]
        rows.append(
            {
                "case_id": candidate.get("case_id") or candidate.get("candidate_id"),
                "status": status,
                "blockers": sorted(set(blockers)),
                "identity_hash": row_hash,
                "identity_payload": payload,
                "missing_identity_fields": candidate.get("_missing_identity_fields", []),
                "fixture_source_not_proof_eligible": True,
            }
        )
    return rows


def build_report(
    *,
    pricing_capability_path: Path = DEFAULT_PRICING_CAPABILITY,
    base_identity_ledger_path: Path = DEFAULT_BASE_CLEAN_STACK_IDENTITY_LEDGER,
    manifest_path: Path = DEFAULT_MANIFEST,
    as_of_date: str = "2026-06-04",
    concept_id: str = CONCEPT_ID,
    structure: str = STRUCTURE,
    no_write_requested: bool = False,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    pricing_capability, pricing_meta = _load_json(pricing_capability_path, required=True)
    base_identity_ledger, base_meta = _load_json(base_identity_ledger_path, required=False)
    manifest, manifest_meta = _load_json(manifest_path, required=True)
    candidates = _fixture_rows(manifest)
    pricing_status, pricing_blockers = _pricing_capability_status(pricing_capability, pricing_meta)
    base_status, base_hashes, base_blockers = _base_identity_status(base_identity_ledger, base_meta)
    denominator_status, missing_denominator_statuses = _denominator_mapping_status(manifest, candidates)
    rows = _evaluate_candidates(candidates, base_hashes)
    candidate_blockers = sorted({str(blocker) for row in rows for blocker in _as_list(row.get("blockers"))})
    blockers = sorted(
        set(pricing_blockers)
        | set(base_blockers)
        | ({"missing_denominator_status"} if missing_denominator_statuses else set())
        | set(candidate_blockers)
        | ({"missing_fixture_manifest_rows"} if not candidates else set())
        | ({"missing_fixture_manifest"} if manifest_meta.get("status") != "loaded" else set())
    )
    strict_new_ready = base_status == "ready" and not any(
        blocker in candidate_blockers
        for blocker in ("candidate_duplicate_existing_base_stack", "candidate_duplicate_within_research_harness", "missing_identity_field", "leaky_identity_or_future_field_present")
    )
    full_denominator_ready = denominator_status == "ready" and pricing_status == "ready"
    status = (
        "flow_extreme_denominator_dedupe_bridge_ready"
        if full_denominator_ready and strict_new_ready and not blockers
        else "blocked_flow_extreme_denominator_dedupe_bridge"
    )
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "status": status,
        **READ_ONLY_FLAGS,
        "no_write_requested": no_write_requested,
        "scope": "read_only_flow_extreme_full_denominator_and_strict_new_dedupe_bridge",
        "concept_id": concept_id,
        "structure": structure,
        "as_of_date": as_of_date,
        "protected_holdout_start": PROTECTED_HOLDOUT_START,
        "full_denominator_mapping_status": "ready" if full_denominator_ready else "blocked",
        "strict_new_dedupe_status": "ready" if strict_new_ready else "blocked",
        "pricing_capability_status": pricing_status,
        "base_identity_ledger_status": base_status,
        "base_identity_hash_count": len(base_hashes),
        "proof_row_count": 0,
        "identity_fields": list(IDENTITY_FIELDS),
        "banned_identity_fields": sorted(BANNED_IDENTITY_FIELDS),
        "denominator_status_contract": list(DENOMINATOR_STATUSES),
        "missing_denominator_statuses": missing_denominator_statuses,
        "candidate_results": rows,
        "candidate_status_counts": _count_statuses(rows),
        "bridge_blockers": blockers,
        "source_artifacts": {
            "multi_leg_side_aware_pricing_capability": pricing_meta,
            "base_clean_stack_identity_ledger": base_meta,
            "fixture_manifest": manifest_meta,
        },
        "accepted_profitability_reason": "This bridge defines denominator and strict-new identity mechanics only; it creates no proof rows and performs no replay.",
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _count_statuses(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get("status"))
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) != expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("concept_id") != CONCEPT_ID:
        raise ValueError("unexpected concept_id")
    if report.get("structure") != STRUCTURE:
        raise ValueError("unexpected structure")
    for status in DENOMINATOR_STATUSES:
        if status not in report.get("denominator_status_contract", []):
            raise ValueError(f"missing denominator status {status}")
    for field in IDENTITY_FIELDS:
        if field not in report.get("identity_fields", []):
            raise ValueError(f"missing identity field {field}")
    if report.get("proof_row_count") != 0 or report.get("accepted_profitability") is not False:
        raise ValueError("bridge cannot create proof rows or accepted profitability")


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Flow-Extreme Denominator/Dedupe Bridge",
        "",
        "This generated artifact is a read-only bridge for the flow-extreme ratio/backspread branch. It defines the full denominator status contract and strict-new opportunity identity hashing without running replay or counting fixture rows as proof.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Full denominator mapping: `{report['full_denominator_mapping_status']}`.",
        f"- Strict-new dedupe: `{report['strict_new_dedupe_status']}`.",
        f"- Proof rows: `{report['proof_row_count']}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Fixture source proof eligible: `{_fmt_bool(not report['fixture_source_not_proof_eligible'])}`.",
        "",
        "## Identity Fields",
        "",
    ]
    lines.extend(f"- `{item}`" for item in report["identity_fields"])
    lines.extend(["", "## Denominator Status Contract", ""])
    lines.extend(f"- `{item}`" for item in report["denominator_status_contract"])
    lines.extend(["", "## Candidate Fixture Results", "", "| Case | Status | Blockers |", "| --- | --- | --- |"])
    for row in _as_list(report.get("candidate_results")):
        row = _as_dict(row)
        blockers = ", ".join(f"`{item}`" for item in _as_list(row.get("blockers"))) or "-"
        lines.append(f"| `{row.get('case_id')}` | `{row.get('status')}` | {blockers} |")
    lines.extend(["", "## Bridge Blockers", ""])
    if report.get("bridge_blockers"):
        lines.extend(f"- `{item}`" for item in report["bridge_blockers"])
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
    parser = argparse.ArgumentParser(description="Build a read-only flow-extreme denominator/dedupe bridge artifact.")
    parser.add_argument("--multi-leg-side-aware-pricing-capability", type=Path, default=DEFAULT_PRICING_CAPABILITY)
    parser.add_argument("--base-identity-ledger", type=Path, default=DEFAULT_BASE_CLEAN_STACK_IDENTITY_LEDGER)
    parser.add_argument("--base-clean-stack-identity-ledger", type=Path, dest="base_identity_ledger")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--as-of-date", default="2026-06-04")
    parser.add_argument("--concept-id", default=CONCEPT_ID)
    parser.add_argument("--structure", default=STRUCTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        pricing_capability_path=args.multi_leg_side_aware_pricing_capability,
        base_identity_ledger_path=args.base_identity_ledger,
        manifest_path=args.manifest,
        as_of_date=args.as_of_date,
        concept_id=args.concept_id,
        structure=args.structure,
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
