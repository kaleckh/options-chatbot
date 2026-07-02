from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY_CONTRACT = ROOT / "data" / "contracts" / "regular-options-frozen-filtered-policy-v1.json"
DEFAULT_CONSUMPTION_REGISTRY = ROOT / "data" / "contracts" / "regular-options-audit-window-consumption-registry.json"
DEFAULT_OUTPUT = ROOT / "data" / "contracts" / "regular-options-out-of-sample-extension-v1.json"

REPORT_ID = "regular_options_out_of_sample_extension_contract"
CONTRACT_ID = "regular_options_out_of_sample_extension_v1"
FREEZE_TOKEN = "freeze_out_of_sample_extension_v1"

REQUESTED_START_MONTH = "2022-01"
REQUESTED_END_MONTH = "2024-05"
REQUESTED_START_DATE = "2022-01-01"
REQUESTED_END_DATE = "2024-05-31"

PROOF_SET_SYMBOLS = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "AAPL",
    "GOOGL",
    "UNH",
    "LLY",
    "JNJ",
    "XOM",
    "CVX",
    "COP",
    "NEM",
)

FALSE_FLAGS = {
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "forward_rows_are_profitability_proof": False,
    "scanner_policy_changed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "options_history_db_mutated": False,
    "protected_holdout_consumed": False,
    "lane_promotion_authorized": False,
}

PROHIBITED_ACTIONS = [
    "do_not_import_quotes_from_phase_15_1_contract",
    "do_not_mutate_options_history_db_from_phase_15_1_contract",
    "do_not_mutate_evidence_stores_from_phase_15_1_contract",
    "do_not_consume_protected_holdout_from_phase_15_1_contract",
    "do_not_change_scanner_policy_from_out_of_sample_window",
    "do_not_change_filter_threshold_from_out_of_sample_window",
    "do_not_add_new_filter_family_from_out_of_sample_window",
    "do_not_change_stops_sizing_or_proof_bars_from_phase_15_1_contract",
    "do_not_enable_live_validation_or_auto_track_from_phase_15_1_contract",
    "do_not_submit_broker_orders_from_phase_15_1_contract",
    "do_not_promote_lanes_from_phase_15_1_contract",
    "do_not_treat_historical_rows_as_forward_profitability_proof",
]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError as exc:
        raise SystemExit(f"missing required policy contract: {_rel(path)}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"policy contract must be a JSON object: {_rel(path)}")
    return data


def _conditions_sha256(conditions: list[dict[str, Any]]) -> str:
    canonical = json.dumps(conditions, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validated_policy_contract(path: Path) -> dict[str, Any]:
    policy = _load_json(path)
    policy_id = policy.get("policy_id")
    conditions = policy.get("conditions")
    conditions_hash = policy.get("conditions_sha256")
    if policy_id != "historical_filtered_candidate_policy_v1":
        raise SystemExit(f"unexpected policy_id in {_rel(path)}: {policy_id!r}")
    if not isinstance(conditions, list) or not all(isinstance(item, dict) for item in conditions):
        raise SystemExit(f"policy contract is missing condition objects: {_rel(path)}")
    if not isinstance(conditions_hash, str) or not conditions_hash:
        raise SystemExit(f"policy contract is missing conditions_sha256: {_rel(path)}")
    recomputed_hash = _conditions_sha256(conditions)
    if recomputed_hash != conditions_hash:
        raise SystemExit(
            "policy contract conditions_sha256 mismatch: "
            f"recorded={conditions_hash} recomputed={recomputed_hash}"
        )
    return policy


def build_contract(
    *,
    policy_contract_path: Path = DEFAULT_POLICY_CONTRACT,
    consumption_registry_path: Path = DEFAULT_CONSUMPTION_REGISTRY,
    frozen_at_utc: str | None = None,
) -> dict[str, Any]:
    policy_contract_path = Path(policy_contract_path)
    consumption_registry_path = Path(consumption_registry_path)
    policy = _validated_policy_contract(policy_contract_path)
    policy_hash = _file_sha256(policy_contract_path)
    conditions_hash = str(policy["conditions_sha256"])

    contract: dict[str, Any] = {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "frozen_at_utc": frozen_at_utc or _utc_now_iso(),
        "read_only": True,
        "research_only": True,
        "evaluation_only": True,
        "target_window": {
            "requested_start_month": REQUESTED_START_MONTH,
            "requested_end_month": REQUESTED_END_MONTH,
            "requested_start_date": REQUESTED_START_DATE,
            "requested_end_date": REQUESTED_END_DATE,
            "provider_received_start_month": None,
            "provider_received_end_month": None,
            "provider_received_status": "pending_phase_15_2_import",
            "deepest_provider_window_observed": None,
            "record_requested_vs_received_on_import": True,
        },
        "proof_set": {
            "name": "frozen_13_symbol_proof_set",
            "symbol_count": len(PROOF_SET_SYMBOLS),
            "symbols": list(PROOF_SET_SYMBOLS),
        },
        "source_policy_contract": {
            "path": _rel(policy_contract_path),
            "sha256": policy_hash,
            "report_id": policy.get("report_id"),
            "policy_id": policy.get("policy_id"),
            "filter_id": policy.get("filter_id"),
            "conditions_sha256": conditions_hash,
        },
        "frozen_policy": {
            "policy_id": policy.get("policy_id"),
            "filter_id": policy.get("filter_id"),
            "conditions_sha256": conditions_hash,
            "conditions": policy["conditions"],
        },
        "evaluation_scope": {
            "mode": "evaluation_only",
            "new_window_only": True,
            "filter_modification_prohibited": True,
            "threshold_change_prohibited": True,
            "new_filter_family_prohibited": True,
            "existing_24_month_dataset_selection_forbidden": True,
            "evaluation_window_must_not_overlap_existing_24_month_selection_dataset": True,
            "phase_15_2_import_not_started_by_this_contract": True,
            "window_consumption_registry_path": _rel(consumption_registry_path),
            "registry_disposition_on_evaluation": "consumed_for_evaluation",
            "registry_append_required_immediately_upon_evaluation": True,
        },
        "gates": {
            "cluster_key": "ticker:ISO-week",
            "cluster_date_field": "entry_date",
            "bootstrap_draws": 10000,
            "percent_cluster_pf_lb_5pct_must_be_gt": 1.0,
            "usd_cluster_pf_lb_5pct_must_be_gt": 1.0,
            "total_net_pnl_usd_must_be_gt": 0.0,
            "window": "new_out_of_sample_window_only",
        },
        "fee_model": {
            "source": "scripts/build_regular_options_historical_frozen_scanner_replay_adapter.py",
            "fee_per_contract_leg_usd": 0.65,
            "round_trip_leg_count": 4,
            "legs_per_vertical_spread": 2,
            "contract_multiplier": 100,
            "total_fees_usd_formula": "4 * fee_per_contract_leg_usd",
            "exit_value_formula": "max(0, long_bid - short_ask)",
            "net_pnl_usd_formula": "(exit_value - entry_debit) * 100 - total_fees_usd",
        },
        "interpretation": {
            "train_percent_cluster_pf_lb": 0.93,
            "train_usd_cluster_pf_lb": 0.80,
            "pre_registered_expectation": "uncertain",
            "failure_verdict": "park_filter_hypothesis_tracker_may_continue",
            "passing_verdict": "historically_consistent_still_awaiting_forward_bar",
            "neither_outcome_authorizes_trading": True,
        },
        "prohibited_actions": PROHIBITED_ACTIONS,
    }
    contract.update(FALSE_FLAGS)
    return contract


def write_contract(contract: dict[str, Any], output_path: Path = DEFAULT_OUTPUT) -> None:
    output_path = Path(output_path)
    if output_path.exists():
        raise SystemExit(f"refusing to overwrite existing contract: {_rel(output_path)}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-token", required=True)
    parser.add_argument("--policy-contract", type=Path, default=DEFAULT_POLICY_CONTRACT)
    parser.add_argument("--consumption-registry", type=Path, default=DEFAULT_CONSUMPTION_REGISTRY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.freeze_token != FREEZE_TOKEN:
        raise SystemExit("refusing to freeze out-of-sample extension contract without the Phase 15.1 token")

    contract = build_contract(
        policy_contract_path=args.policy_contract,
        consumption_registry_path=args.consumption_registry,
    )
    if not args.no_write:
        write_contract(contract, args.output)

    if args.json:
        print(json.dumps(contract, indent=2, sort_keys=True))
    else:
        verb = "validated" if args.no_write else "wrote"
        print(f"{verb} {_rel(args.output)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
