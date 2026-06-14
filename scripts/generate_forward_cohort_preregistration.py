from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.forward_cohort_preregistration import DEFAULT_FORWARD_COHORT_PREREGISTRATION
from supervised_scan import (
    AI_COMMODITY_INFRA_OBSERVATION_COHORT_ID,
    BULLISH_PULLBACK_PROFIT_REPAIR_KEEP_TICKERS,
    SCAN_PLAYBOOKS,
    VOLATILITY_EXPANSION_OBSERVATION_COHORT_ID,
)
from us_equity_market_calendar import add_market_days


CONTRACT_PATH = DEFAULT_FORWARD_COHORT_PREREGISTRATION
DOC_PATH = ROOT / "docs" / "forward-cohort-preregistration.md"
FREEZE_DATE = date(2026, 6, 14)
MARKET_DAY_COUNT = 30
EVAL_DATE = add_market_days(FREEZE_DATE, MARKET_DAY_COUNT)
LANE_VOLATILITY = VOLATILITY_EXPANSION_OBSERVATION_COHORT_ID
LANE_BULLISH_CARRIER = "bullish_pullback_observation"
FROZEN_LANES = (LANE_VOLATILITY, LANE_BULLISH_CARRIER)


GUARDRAIL_KEYS = (
    "target_dte",
    "max_new_positions_per_day",
    "max_scan_picks_per_ticker",
    "max_sector_open_positions",
    "max_regime_open_positions",
    "block_same_ticker",
    "allowed_asset_classes",
    "allowed_tickers",
    "scan_tickers",
    "allowed_market_regimes",
    "allowed_directions",
    "scan_allowed_directions",
    "allowed_strategy_types",
    "signal_variant",
    "min_quality_score",
    "max_debit_pct_of_width",
    "max_fill_degradation_vs_mid_pct",
    "max_worst_leg_bid_ask_spread_pct",
    "calibration_playbook",
    "max_concurrent_positions",
    "max_correlated_index_positions",
    "daily_loss_limit_pct",
    "weekly_loss_limit_pct",
    "max_position_cost_risk_pct",
    "max_portfolio_cost_risk_pct",
    "forced_size_tier",
    "forced_cohort_id",
    "forced_cohort_role",
    "required_candidate_execution_label",
    "profitability_repair_allowed_tickers",
    "profitability_repair_min_ret5",
    "profitability_repair_max_debit_pct_of_width",
)


def _json_text(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _policy_subset(playbook_id: str) -> dict[str, Any]:
    playbook = copy.deepcopy(SCAN_PLAYBOOKS[playbook_id])
    return {key: playbook.get(key) for key in GUARDRAIL_KEYS if key in playbook}


def _snapshot_for_lane(playbook_id: str) -> dict[str, Any]:
    policy = _policy_subset(playbook_id)
    text = _json_text(policy)
    return {
        "source": f"supervised_scan.SCAN_PLAYBOOKS[{playbook_id!r}]",
        "sha256": _sha256_text(text),
        "policy": policy,
    }


def _parked_regular_lanes() -> list[str]:
    return [
        lane
        for lane in sorted(SCAN_PLAYBOOKS)
        if lane not in set(FROZEN_LANES) and lane != AI_COMMODITY_INFRA_OBSERVATION_COHORT_ID
    ]


def build_contract() -> dict[str, Any]:
    source_file = ROOT / "supervised_scan.py"
    bullish_carrier_symbols = list(BULLISH_PULLBACK_PROFIT_REPAIR_KEEP_TICKERS)
    volatility_symbols = list(SCAN_PLAYBOOKS[LANE_VOLATILITY].get("allowed_tickers") or [])
    parked_lanes = _parked_regular_lanes()
    return {
        "contract_id": "forward-cohort-preregistration",
        "version": 1,
        "status": "active",
        "runtime_use": True,
        "last_updated": FREEZE_DATE.isoformat(),
        "generated_by": "scripts/generate_forward_cohort_preregistration.py",
        "scope": "regular_options_forward_cohort",
        "cohort": {
            "frozen": True,
            "freeze_date": FREEZE_DATE.isoformat(),
            "eval_date": EVAL_DATE.isoformat(),
            "market_day_count": MARKET_DAY_COUNT,
            "date_basis": "candidate_entry_date_after_freeze_date",
            "timezone": "America/New_York",
            "fresh_rows_collected": {lane: 0 for lane in FROZEN_LANES},
        },
        "lanes": [
            {
                "lane_id": LANE_VOLATILITY,
                "label": SCAN_PLAYBOOKS[LANE_VOLATILITY].get("label"),
                "cohort_role": "frozen_regular_lane",
                "symbols": volatility_symbols,
                "guardrails_source": f"supervised_scan.SCAN_PLAYBOOKS[{LANE_VOLATILITY!r}]",
                "policy_snapshot_sha256": _snapshot_for_lane(LANE_VOLATILITY)["sha256"],
            },
            {
                "lane_id": LANE_BULLISH_CARRIER,
                "label": "Bullish Pullback Carrier Set",
                "cohort_role": "clean_bullish_pullback_carrier_set",
                "symbols": bullish_carrier_symbols,
                "guardrails_source": (
                    "supervised_scan.SCAN_PLAYBOOKS['bullish_pullback_observation'] plus "
                    "supervised_scan.BULLISH_PULLBACK_PROFIT_REPAIR_KEEP_TICKERS"
                ),
                "policy_snapshot_sha256": _snapshot_for_lane(LANE_BULLISH_CARRIER)["sha256"],
            },
        ],
        "promotion_criteria": {
            "existing_promotion_bars": "unchanged_never_lowered",
            "additional_forward_bars": [
                "at_least_30_fresh_forward_exact_realized_pnl_rows_after_freeze_date_per_lane",
                "bootstrap_pf_lower_bound_5pct_above_1_0_on_forward_cohort",
                "regime_robust_true",
                "zero_winner_damage_findings",
            ],
            "evidence_allowed": "fresh_forward_exact_realized_opra_nbbo_rows_only",
            "evidence_not_allowed": [
                "research_backfill",
                "midpoint",
                "daily_eod",
                "stale_snapshot",
                "manual_mark",
                "synthetic_pnl",
            ],
        },
        "kill_criteria": {
            "per_frozen_lane": [
                "profit_factor_below_1_0_over_at_least_30_fresh_forward_exact_realized_rows",
                "fewer_than_10_fresh_forward_exact_realized_rows_by_eval_date_is_operational_kill_fix_funnel_and_refreeze",
            ],
            "program_negative_success": (
                "If both frozen lanes receive evidence-backed kill verdicts and the credit-side incubator "
                "study reaches a replay-backed verdict, document the definitive negative as success."
            ),
        },
        "suspension": {
            "status": "active",
            "parked_status": "parked_outside_forward_cohort",
            "parked_regular_lanes": parked_lanes,
            "parked_regular_lane_count": len(parked_lanes),
            "scans_enabled": False,
            "chores_enabled": False,
            "readback_line": (
                "All non-cohort regular lanes are parked outside the frozen forward cohort: no scans, "
                "no chores, and no promotion work until the cohort is evaluated or explicitly refrozen."
            ),
        },
        "byte_frozen_policy_snapshot": {
            "snapshot_format": "canonical_json_sha256_with_embedded_policy_payloads",
            "source_file": "supervised_scan.py",
            "source_file_sha256": _sha256_file(source_file),
            "lanes": {
                LANE_VOLATILITY: _snapshot_for_lane(LANE_VOLATILITY),
                LANE_BULLISH_CARRIER: _snapshot_for_lane(LANE_BULLISH_CARRIER),
            },
        },
        "source_evidence": [
            "docs/DECISIONS.md 2026-06-09 regular strategy direction",
            "docs/lane-lab-lanes.md active bullish pullback extensions",
            "docs/bullish-pullback-ticker-audit-2026-05-29.md current keep queue",
            "data/forward-tracking/lane_promotion_state_latest.json",
            "data/contracts/forward-holdout-contract.json",
        ],
        "non_goals": [
            "does_not_lower_existing_promotion_bars",
            "does_not_change_scanner_guardrails_for_frozen_lanes",
            "does_not_submit_broker_orders",
            "does_not_count_research_backfill_or_synthetic_pnl_as_forward_proof",
            "does_not_consume_protected_holdout_before_phase_5_champion_final_eval",
        ],
    }


def render_markdown(contract: dict[str, Any]) -> str:
    cohort = contract["cohort"]
    lines = [
        "# Forward Cohort Preregistration",
        "",
        "Generated by `scripts/generate_forward_cohort_preregistration.py`. Do not hand-edit this file.",
        "",
        f"- Contract id: `{contract['contract_id']}`",
        f"- Status: `{contract['status']}`",
        f"- Runtime use: `{str(contract['runtime_use']).lower()}`",
        f"- Freeze date: `{cohort['freeze_date']}`",
        f"- Eval date: `{cohort['eval_date']}`",
        f"- Market days: `{cohort['market_day_count']}`",
        f"- Date basis: `{cohort['date_basis']}`",
        "",
        "## Frozen Lanes",
        "",
    ]
    for lane in contract["lanes"]:
        lines.extend(
            [
                f"### {lane['lane_id']}",
                "",
                f"- Role: `{lane['cohort_role']}`",
                f"- Symbols: `{', '.join(lane['symbols'])}`",
                f"- Guardrails source: `{lane['guardrails_source']}`",
                f"- Policy snapshot SHA-256: `{lane['policy_snapshot_sha256']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Promotion Criteria",
            "",
            f"- Existing bars: `{contract['promotion_criteria']['existing_promotion_bars']}`",
        ]
    )
    lines.extend(f"- `{item}`" for item in contract["promotion_criteria"]["additional_forward_bars"])
    lines.extend(
        [
            "",
            "## Kill Criteria",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in contract["kill_criteria"]["per_frozen_lane"])
    lines.extend(
        [
            f"- Program negative success: {contract['kill_criteria']['program_negative_success']}",
            "",
            "## Parked Regular Lanes",
            "",
            f"- Status: `{contract['suspension']['parked_status']}`",
            f"- Count: `{contract['suspension']['parked_regular_lane_count']}`",
            f"- Scans enabled: `{contract['suspension']['scans_enabled']}`",
            f"- Chores enabled: `{contract['suspension']['chores_enabled']}`",
            f"- Readback: {contract['suspension']['readback_line']}",
            f"- Lanes: `{', '.join(contract['suspension']['parked_regular_lanes'])}`",
            "",
            "## Byte-Frozen Policy Snapshot",
            "",
            f"- Source file: `{contract['byte_frozen_policy_snapshot']['source_file']}`",
            f"- Source file SHA-256: `{contract['byte_frozen_policy_snapshot']['source_file_sha256']}`",
            f"- Snapshot format: `{contract['byte_frozen_policy_snapshot']['snapshot_format']}`",
            "",
            "## Source Evidence",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in contract["source_evidence"])
    lines.extend(["", "## Non-Goals", ""])
    lines.extend(f"- `{item}`" for item in contract["non_goals"])
    return "\n".join(lines).rstrip() + "\n"


def write_outputs() -> dict[str, str]:
    contract = build_contract()
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT_PATH.write_text(_json_text(contract), encoding="utf8")
    DOC_PATH.write_text(render_markdown(contract), encoding="utf8")
    return {"contract": str(CONTRACT_PATH), "doc": str(DOC_PATH)}


def check_outputs() -> list[str]:
    contract = build_contract()
    expected = {
        CONTRACT_PATH: _json_text(contract),
        DOC_PATH: render_markdown(contract),
    }
    failures: list[str] = []
    for path, text in expected.items():
        if not path.exists():
            failures.append(f"missing {path.relative_to(ROOT)}")
            continue
        if path.read_text(encoding="utf8") != text:
            failures.append(f"stale {path.relative_to(ROOT)}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the frozen regular-options forward cohort preregistration.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        failures = check_outputs()
        if failures:
            print("\n".join(failures), file=sys.stderr)
            return 1
        return 0
    print(json.dumps(write_outputs(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
