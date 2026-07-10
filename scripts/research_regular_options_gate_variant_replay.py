from __future__ import annotations

import argparse
import hashlib
import json
import sys
from calendar import monthrange
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import (  # noqa: E402
    build_regular_options_historical_frozen_scanner_replay_adapter as adapter,
)
from scripts import run_fresh_window_2018_2021_quote_imports as import_driver  # noqa: E402
from scripts.build_regular_options_historical_profitability_filter_iteration import (  # noqa: E402
    _metrics,
)


REPORT_ID = "regular_options_gate_variant_replay"
DEFAULT_FAMILIES = (
    ROOT
    / "data"
    / "contracts"
    / "regular-options-filter-family-preregistration-draft-v1.json"
)
DEFAULT_WINDOW_CONTRACT = (
    ROOT
    / "data"
    / "contracts"
    / "regular-options-filter-family-fresh-window-contract-v1.json"
)
DEFAULT_IMPORT_MANIFEST = import_driver.DEFAULT_MANIFEST
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-filter-family-fresh-window"
    / "gate-variant-replay"
)

CONSUMED_WINDOWS = (
    ("2022-01", "2024-05"),
    ("2024-06", "2026-01"),
    ("2026-02", "2026-05"),
)
EXPECTED_SPLITS = {
    "family_train": ("2018-01", "2020-06"),
    "family_validation": ("2020-07", "2021-12"),
}
EXPECTED_FAMILY_GRIDS = [
    {"family_id": "F1a_ret20_threshold", "grid": [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0]},
    {
        "family_id": "F1b_ret5_pullback_band",
        "grid": [[-6.0, 0.25], [-4.0, 0.25], [-4.0, 1.0], [-2.0, 1.0], [-6.0, 2.0]],
    },
    {
        "family_id": "F1c_trend_term",
        "grid": ["price_gt_sma50", "price_gt_sma20", "none"],
    },
    {"family_id": "F2_session_time_alignment", "grid": [0, 15, 30, 60]},
]
VALIDATION_PENDING_BLOCKERS = (
    "missing_f2_session_time_alignment_scoring_path",
    "missing_top3_family_member_selection_path",
    "missing_formal_one_shot_family_validation_path",
    "missing_consumption_registry_append_path",
)

FALSE_FLAGS = {
    "read_only_research_harness": True,
    "research_only_not_forward_proof": True,
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "proof_bars_changed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "protected_holdout_consumed": False,
    "consumption_registry_appended": False,
    "selection_eligible": False,
    "evaluation_ready": False,
    "member_scores_valid_for_selection": False,
    "family_member_acceptance_authorized": False,
    "top3_selection_authorized": False,
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def _import_manifest_binding(import_manifest: Path, options_db: Path) -> dict[str, Any]:
    assessment: dict[str, Any] = {
        "required_chain_standard_version": import_driver.CHAIN_COMPLETENESS_STANDARD_VERSION,
        "import_manifest_path": _rel(import_manifest),
        "import_manifest_sha256": None,
        "manifest_status": None,
        "manifest_spec_hash": None,
        "manifest_database_identity_sha256": None,
        "selected_database_identity_sha256": None,
        "manifest_corpus_sha256": None,
        "database_corpus_sha256": None,
        "chain_status": None,
        "manifest_bound_corpus_ready": False,
        "chain_completeness_standard_satisfied": False,
        "binding_errors": [],
        "chain_standard_errors": [],
    }
    try:
        payload = _load_json(import_manifest)
        assessment["import_manifest_sha256"] = _file_sha256(import_manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        assessment["binding_errors"] = [
            f"import_manifest_unreadable:{type(exc).__name__}"
        ]
        assessment["chain_standard_errors"] = ["chain_completeness_proof_missing"]
        return assessment

    assessment["manifest_status"] = payload.get("status")
    assessment["manifest_spec_hash"] = payload.get("spec_hash")
    assessment["manifest_database_identity_sha256"] = (
        payload.get("database_identity") or {}
    ).get("identity_sha256")
    assessment["chain_status"] = (payload.get("chain_completeness") or {}).get("status")
    selected_identity = import_driver._database_identity(options_db)
    assessment["selected_database_identity_sha256"] = selected_identity.get(
        "identity_sha256"
    )
    exact_plan = payload.get("exact_plan")
    binding_errors: list[str] = []
    if not isinstance(exact_plan, dict):
        binding_errors.append("import_manifest_exact_plan_missing")
    else:
        binding_errors.extend(
            import_driver.manifest_validation_errors(
                payload, exact_plan, require_complete=True
            )
        )
        if not binding_errors:
            binding_errors.extend(
                import_driver.revalidate_complete_manifest_database(
                    payload, exact_plan, db_path=options_db
                )
            )
    corpus_binding = payload.get("downstream_corpus_binding") or {}
    assessment["manifest_corpus_sha256"] = corpus_binding.get(
        "manifest_eligible_row_set_sha256"
    )
    assessment["database_corpus_sha256"] = corpus_binding.get(
        "database_eligible_row_set_sha256"
    )
    assessment["binding_errors"] = sorted(set(binding_errors))
    assessment["manifest_bound_corpus_ready"] = not binding_errors
    chain_errors = import_driver.chain_completeness_standard_errors(payload)
    assessment["chain_standard_errors"] = chain_errors
    assessment["chain_completeness_standard_satisfied"] = (
        not binding_errors and not chain_errors
    )
    return assessment


def _split_bounds(split: dict[str, Any]) -> tuple[str, str]:
    start_month = str(split["start_month"])
    end_month = str(split["end_month"])
    start_year, start_month_number = (int(part) for part in start_month.split("-"))
    end_year, end_month_number = (int(part) for part in end_month.split("-"))
    split_start = date(start_year, start_month_number, 1).isoformat()
    split_end = date(
        end_year, end_month_number, monthrange(end_year, end_month_number)[1]
    ).isoformat()
    return split_start, split_end


def _write_report(
    report: dict[str, Any], *, output_dir: Path, split_name: str, json_output: bool
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{split_name}_latest.json"
    out_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8"
    )
    if json_output:
        print(
            json.dumps(
                {key: value for key, value in report.items() if key != "results"},
                indent=2,
                sort_keys=True,
            )
        )
    print(f"wrote {out_path}")
    return out_path


def _month_overlaps_consumed(start_month: str, end_month: str) -> bool:
    return any(
        start_month <= c_end and end_month >= c_start
        for c_start, c_end in CONSUMED_WINDOWS
    )


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _member_params(family: dict[str, Any], member: Any) -> dict[str, Any]:
    family_id = str(family.get("family_id"))
    if family_id == "F1a_ret20_threshold":
        return {
            "ret20_min": float(member),
            "ret5_band": (-4.0, 0.25),
            "trend_anchor": "price_gt_sma50",
        }
    if family_id == "F1b_ret5_pullback_band":
        low, high = member
        return {
            "ret20_min": 2.0,
            "ret5_band": (float(low), float(high)),
            "trend_anchor": "price_gt_sma50",
        }
    if family_id == "F1c_trend_term":
        return {
            "ret20_min": 2.0,
            "ret5_band": (-4.0, 0.25),
            "trend_anchor": str(member),
        }
    raise ValueError(
        f"family {family_id} is not scoreable by this harness (F2 requires the emission-time surface)"
    )


def _make_gate(
    params: dict[str, Any], member_id: str
) -> Callable[..., tuple[str | None, list[str], dict[str, Any]]]:
    ret20_min = float(params["ret20_min"])
    ret5_low, ret5_high = params["ret5_band"]
    trend_anchor = str(params["trend_anchor"])

    def gate(
        *, lane: str, symbol: str, feature: dict[str, Any] | None, candidate_date: date
    ) -> tuple[str | None, list[str], dict[str, Any]]:
        evidence: dict[str, Any] = {
            "gate_variant_member": member_id,
            "gate_variant_params": dict(params),
        }
        if lane != "bullish_pullback_observation":
            # families are defined against the pullback gate only; other lanes emit no candidates
            return None, [], evidence
        if not feature or not adapter._feature_ready(
            feature, candidate_date=candidate_date
        ):
            return None, ["missing_point_in_time_market_regime_inputs"], evidence
        prior_close = _safe_float(feature.get("prior_close"))
        sma50 = _safe_float(feature.get("prior_50_trading_day_sma"))
        sma20 = _safe_float(feature.get("prior_20_trading_day_sma"))
        ret20 = _safe_float(feature.get("prior_20_trading_day_return_pct"))
        ret5 = _safe_float(feature.get("prior_5_trading_day_return_pct"))
        evidence.update(
            {
                "prior_close": prior_close,
                "known_at_utc": feature.get("known_at_utc"),
                "prior_20_trading_day_return_pct": ret20,
                "prior_5_trading_day_return_pct": ret5,
                "prior_50_trading_day_sma": sma50,
                "prior_20_trading_day_sma": sma20,
            }
        )
        required = {
            "prior_close": prior_close,
            "prior_20_trading_day_return_pct": ret20,
            "prior_5_trading_day_return_pct": ret5,
        }
        if trend_anchor == "price_gt_sma50":
            required["prior_50_trading_day_sma"] = sma50
        elif trend_anchor == "price_gt_sma20":
            required["prior_20_trading_day_sma"] = sma20
        missing = sorted(name for name, value in required.items() if value is None)
        if missing:
            return (
                None,
                [f"missing_gate_variant_feature_{name}" for name in missing],
                evidence,
            )
        trend_ok = True
        if trend_anchor == "price_gt_sma50":
            trend_ok = prior_close > sma50
        elif trend_anchor == "price_gt_sma20":
            trend_ok = prior_close > sma20
        bullish = trend_ok and ret20 > ret20_min and ret5_low < ret5 < ret5_high
        return ("call" if bullish else None), [], evidence

    return gate


def run_member(
    *,
    family: dict[str, Any],
    member: Any,
    member_index: int,
    split_start: str,
    split_end: str,
    as_of_date: str,
    adapter_paths: dict[str, Path],
    bootstrap_draws: int,
) -> dict[str, Any]:
    member_id = f"{family['family_id']}[{member_index}]"
    params = _member_params(family, member)
    report = adapter.build_report(
        forward_cohort_path=adapter_paths["forward_cohort"],
        feature_store_path=adapter_paths["feature_store"],
        market_regime_inputs_path=adapter_paths["market_regime_inputs"],
        vix_bucket_path=adapter_paths["vix_bucket"],
        input_surface_tracker_path=adapter_paths["input_surface_tracker"],
        earnings_calendar_path=adapter_paths["earnings_calendar"],
        options_db_path=adapter_paths["options_db"],
        window_start=split_start,
        window_end=split_end,
        as_of_date=as_of_date,
        gate_fn=_make_gate(params, member_id),
    )
    research_materializer_ready = report.get("research_materializer_ready") is True
    research_materializer_blockers = sorted(
        str(item)
        for item in (report.get("research_materializer_blockers") or [])
        if str(item)
    )
    selected = [
        row
        for row in report.get("selected_candidates") or []
        if row.get("net_pnl_usd") is not None
    ]
    diagnostic_metrics = (
        _metrics(
            selected,
            branch_id=f"{REPORT_ID}:{member_id}",
            bootstrap_draws=bootstrap_draws,
        )
        if research_materializer_ready and selected
        else {}
    )
    return {
        "member_id": member_id,
        "family_id": family["family_id"],
        "member": member,
        "params": params,
        "adapter_status": report.get("status"),
        "adapter_blockers": report.get("blockers"),
        "research_materializer_ready": research_materializer_ready,
        "research_materializer_blockers": research_materializer_blockers,
        "production_proof_or_nomination_blockers": sorted(
            str(item)
            for item in (report.get("proof_or_nomination_blockers") or [])
            if str(item)
        ),
        "production_parity_mismatches": report.get("production_parity_mismatches")
        or [],
        "scanner_parity": report.get("scanner_parity") is True,
        "production_scanner_replay": report.get("production_scanner_replay") is True,
        "daily_row_count": report.get("daily_candidate_decision_row_count"),
        "diagnostic_selected_candidate_count": len(
            report.get("selected_candidates") or []
        ),
        "diagnostic_priced_candidate_count": len(selected),
        "diagnostic_metrics": diagnostic_metrics,
        "analysis_class": "diagnostic_only",
        "member_score_valid_for_selection": False,
        "family_member_accepted": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Research-only preregistered gate-variant replay over the fresh filter-family window."
    )
    parser.add_argument("--families", type=Path, default=DEFAULT_FAMILIES)
    parser.add_argument("--window-contract", type=Path, default=DEFAULT_WINDOW_CONTRACT)
    parser.add_argument("--import-manifest", type=Path, default=DEFAULT_IMPORT_MANIFEST)
    parser.add_argument(
        "--family-id",
        default=None,
        help="run one family; default runs all scoreable families",
    )
    parser.add_argument(
        "--split", choices=["family_train", "family_validation"], default="family_train"
    )
    parser.add_argument("--bootstrap-draws", type=int, default=10000)
    parser.add_argument(
        "--forward-cohort", type=Path, default=adapter.DEFAULT_FORWARD_COHORT
    )
    parser.add_argument("--feature-store", type=Path, required=True)
    parser.add_argument("--market-regime-inputs", type=Path, required=True)
    parser.add_argument("--vix-bucket", type=Path, required=True)
    parser.add_argument("--input-surface-tracker", type=Path, required=True)
    parser.add_argument("--earnings-calendar", type=Path, required=True)
    parser.add_argument("--options-db", type=Path, default=adapter.DEFAULT_OPTIONS_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    families_doc = _load_json(args.families)
    window_contract = _load_json(args.window_contract)
    split = window_contract["split_rule"][args.split]
    split_start, split_end = _split_bounds(split)
    as_of_date = split_end

    expected_start_month, expected_end_month = EXPECTED_SPLITS[args.split]
    selection_criterion = window_contract.get("pre_declared_selection_criterion") or {}
    expected_bootstrap_draws = int(selection_criterion.get("bootstrap_draws") or 0)
    families = list(families_doc.get("families") or [])
    actual_family_grids = [
        {
            "family_id": str(family.get("family_id") or ""),
            "grid": list(family.get("grid") or []),
        }
        for family in families
    ]
    family_member_count = sum(len(family.get("grid") or []) for family in families)
    f2_families = [
        family
        for family in families
        if str(family.get("family_id")) == "F2_session_time_alignment"
    ]
    manifest_binding = _import_manifest_binding(args.import_manifest, args.options_db)
    input_binding = {
        "families_contract_path": _rel(args.families),
        "families_contract_sha256": _file_sha256(args.families),
        "window_contract_path": _rel(args.window_contract),
        "window_contract_sha256": _file_sha256(args.window_contract),
        "family_grid_sha256": _canonical_sha256(actual_family_grids),
        "expected_family_grid_sha256": _canonical_sha256(EXPECTED_FAMILY_GRIDS),
        "family_member_count": family_member_count,
        "expected_bootstrap_draws": expected_bootstrap_draws,
        "requested_bootstrap_draws": int(args.bootstrap_draws),
        "split_months": {
            "start_month": str(split["start_month"]),
            "end_month": str(split["end_month"]),
        },
        "split_dates": {"start": split_start, "end": split_end, "as_of": as_of_date},
        "import_manifest": manifest_binding,
    }
    binding_blockers: set[str] = set()
    if (str(split["start_month"]), str(split["end_month"])) != (
        expected_start_month,
        expected_end_month,
    ):
        binding_blockers.add(
            f"split_contract_mismatch:{args.split}:{split['start_month']}:{split['end_month']}"
        )
    if args.split == "family_train" and (split_start, split_end, as_of_date) != (
        "2018-01-01",
        "2020-06-30",
        "2020-06-30",
    ):
        binding_blockers.add(
            "family_train_bounds_not_exact_2018-01-01_through_2020-06-30"
        )
    if (
        int(args.bootstrap_draws) != expected_bootstrap_draws
        or expected_bootstrap_draws != 10000
    ):
        binding_blockers.add(
            f"bootstrap_draws_not_frozen_10000:contract={expected_bootstrap_draws}:requested={args.bootstrap_draws}"
        )
    if actual_family_grids != EXPECTED_FAMILY_GRIDS:
        binding_blockers.add("preregistered_family_grid_content_or_order_mismatch")
    if (
        family_member_count != 19
        or len(f2_families) != 1
        or len(f2_families[0].get("grid") or []) != 4
    ):
        binding_blockers.add(
            "preregistered_family_grid_not_exact_19_members_with_4_f2_members"
        )
    if (
        families_doc.get("contract_id")
        != "regular_options_filter_family_preregistration_draft_v1"
    ):
        binding_blockers.add("families_contract_id_mismatch")
    if (
        window_contract.get("contract_id")
        != "regular_options_filter_family_fresh_window_v1"
    ):
        binding_blockers.add("fresh_window_contract_id_mismatch")
    window = window_contract.get("window") or {}
    if (window.get("requested_start_date"), window.get("requested_end_date")) != (
        "2018-01-01",
        "2021-12-31",
    ):
        binding_blockers.add("fresh_window_contract_bounds_mismatch")
    if (
        window_contract.get("split_rule", {}).get("split_fixed_before_import")
        is not True
    ):
        binding_blockers.add("fresh_window_split_not_recorded_fixed_before_import")
    if args.family_id:
        binding_blockers.add(
            f"partial_family_filter_not_contract_complete:{args.family_id}"
        )
    if manifest_binding.get("manifest_bound_corpus_ready") is not True:
        binding_blockers.add("manifest_bound_downstream_quote_corpus_not_established")
        binding_blockers.update(
            f"import_manifest_binding:{item}"
            for item in (manifest_binding.get("binding_errors") or [])
        )

    chain_standard_satisfied = (
        manifest_binding.get("chain_completeness_standard_satisfied") is True
    )
    chain_blockers: set[str] = set()
    if not chain_standard_satisfied:
        chain_blockers.add("provider_chain_completeness_not_established")
        chain_blockers.update(
            f"chain_standard:{item}"
            for item in (manifest_binding.get("chain_standard_errors") or [])
        )

    if _month_overlaps_consumed(split["start_month"], split["end_month"]):
        binding_blockers.add("requested_split_overlaps_consumed_selection_window")
    if args.split == "family_validation":
        formal_blockers = sorted(
            {
                *binding_blockers,
                "missing_top3_family_member_selection_path",
                "missing_formal_one_shot_family_validation_path",
                "missing_consumption_registry_append_path",
            }
        )
        report = {
            "report_id": REPORT_ID,
            "status": "blocked_formal_family_validation_path",
            "generated_at_utc": _utc_now_iso(),
            "split": args.split,
            "split_window": {
                "start": split_start,
                "end": split_end,
                "as_of": as_of_date,
            },
            "input_binding": input_binding,
            "member_count": 0,
            "research_materializer_ready": False,
            "diagnostic_materializer_ready": False,
            "contract_complete": False,
            "family_validation_scored": False,
            "blockers": sorted(set(formal_blockers) | chain_blockers),
            "validation_pending_blockers": sorted(
                set(formal_blockers) | chain_blockers
            ),
            "chain_completeness_standard": manifest_binding,
            "results": [],
            "backup_retirement_authorized": False,
            "seal_retirement_authorized": False,
            **FALSE_FLAGS,
        }
        _write_report(
            report,
            output_dir=args.output_dir,
            split_name=args.split,
            json_output=args.json_output,
        )
        return 1

    adapter_paths = {
        "forward_cohort": args.forward_cohort,
        "feature_store": args.feature_store,
        "market_regime_inputs": args.market_regime_inputs,
        "vix_bucket": args.vix_bucket,
        "input_surface_tracker": args.input_surface_tracker,
        "earnings_calendar": args.earnings_calendar,
        "options_db": args.options_db,
    }
    results: list[dict[str, Any]] = []
    unscored_families: list[dict[str, Any]] = []
    for family in families:
        if args.family_id and family.get("family_id") != args.family_id:
            continue
        if str(family.get("family_id")) == "F2_session_time_alignment":
            unscored_families.append(
                {
                    "family_id": "F2_session_time_alignment",
                    "grid_member_count": len(family.get("grid") or []),
                    "reason": "missing_f2_session_time_alignment_scoring_path",
                }
            )
            continue
        if binding_blockers:
            continue
        for index, member in enumerate(family.get("grid") or []):
            results.append(
                run_member(
                    family=family,
                    member=member,
                    member_index=index,
                    split_start=split_start,
                    split_end=split_end,
                    as_of_date=as_of_date,
                    adapter_paths=adapter_paths,
                    bootstrap_draws=args.bootstrap_draws,
                )
            )
            print(
                json.dumps(
                    {
                        "event": "gate_variant_member_diagnostic_materialized",
                        "analysis_class": "diagnostic_only",
                        "member_id": results[-1]["member_id"],
                        "diagnostic_selected": results[-1][
                            "diagnostic_selected_candidate_count"
                        ],
                        "diagnostic_priced": results[-1][
                            "diagnostic_priced_candidate_count"
                        ],
                    }
                ),
                flush=True,
            )

    research_blockers: set[str] = set(binding_blockers)
    if not results:
        research_blockers.add("no_scoreable_gate_variant_members")
    production_blockers: set[str] = set()
    parity_disclosures: list[dict[str, Any]] = []
    for result in results:
        if result.get("research_materializer_ready") is not True:
            member_blockers = [
                str(item)
                for item in (result.get("research_materializer_blockers") or [])
                if str(item)
            ]
            if member_blockers:
                research_blockers.update(member_blockers)
            else:
                research_blockers.add(
                    f"research_materializer_not_ready:{result['member_id']}"
                )
        production_blockers.update(
            str(item)
            for item in (result.get("production_proof_or_nomination_blockers") or [])
            if str(item)
        )
        parity_disclosures.append(
            {
                "member_id": result["member_id"],
                "scanner_parity": result.get("scanner_parity") is True,
                "production_scanner_replay": result.get("production_scanner_replay")
                is True,
                "mismatches": result.get("production_parity_mismatches") or [],
            }
        )
    ordered_blockers = sorted(research_blockers)
    research_materializer_ready = bool(results) and not ordered_blockers
    validation_pending_blockers = sorted(
        set(VALIDATION_PENDING_BLOCKERS) | chain_blockers
    )
    report_blockers = sorted(set(ordered_blockers) | chain_blockers)
    if not research_materializer_ready:
        report_status = "blocked_gate_variant_replay"
    elif not chain_standard_satisfied:
        report_status = "diagnostic_only_incomplete_quote_surface"
    else:
        report_status = "diagnostic_only_incomplete_family_train"
    report = {
        "report_id": REPORT_ID,
        "status": report_status,
        "analysis_class": "diagnostic_only",
        "generated_at_utc": _utc_now_iso(),
        "split": args.split,
        "split_window": {"start": split_start, "end": split_end, "as_of": as_of_date},
        "families_contract": _rel(args.families),
        "window_contract": _rel(args.window_contract),
        "input_binding": input_binding,
        "member_count": len(results),
        "expected_diagnostic_f1_member_count": 15,
        "research_materializer_ready": research_materializer_ready,
        "diagnostic_materializer_ready": research_materializer_ready,
        "research_materializer_blockers": ordered_blockers,
        "production_proof_or_nomination_blockers": sorted(production_blockers),
        "production_parity_disclosures": parity_disclosures,
        "unscored_families": unscored_families,
        "contract_complete": False,
        "family_train_diagnostics_complete": research_materializer_ready,
        "family_train_complete": False,
        "family_validation_scored": False,
        "top3_selected": False,
        "validation_pending_blockers": validation_pending_blockers,
        "blockers": report_blockers,
        "chain_completeness_standard": manifest_binding,
        "results": results,
        "backup_retirement_authorized": False,
        "seal_retirement_authorized": False,
        **FALSE_FLAGS,
    }
    _write_report(
        report,
        output_dir=args.output_dir,
        split_name=args.split,
        json_output=args.json_output,
    )
    return 1 if report_blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())
