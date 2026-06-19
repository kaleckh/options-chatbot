from __future__ import annotations

import json
from pathlib import Path

from scripts import build_regular_options_evidence_blocker_burndown as burndown


NOW = "2026-06-18T00:00:00Z"


def _write_json(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"generated_at_utc": NOW, **payload}
    path.write_text(json.dumps(data), encoding="utf8")
    return path


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "tournament": tmp_path / "tournament.json",
        "robust_edge": tmp_path / "robust_edge.json",
        "repair": tmp_path / "repair.json",
        "attempts": tmp_path / "attempts.json",
        "profit": tmp_path / "profit.json",
    }


def _base_payloads(tmp_path: Path) -> dict[str, Path]:
    paths = _paths(tmp_path)
    _write_json(
        paths["tournament"],
        {
            "overall_status": "paper_shadow_only",
            "blocked_candidate_count": 1,
            "existing_promotion_ready": False,
            "candidate_rankings": [],
            "best_candidate_if_any": {"lane_id": "volatility_expansion_observation", "decision": "paper_shadow_candidate"},
            "data_coverage_summary": {"promotion_ready": False},
        },
    )
    _write_json(
        paths["robust_edge"],
        {
            "overall_status": "paper_shadow_only",
            "candidate_rankings": [],
            "best_candidate_if_any": {"lane_id": "volatility_expansion_observation", "decision": "paper_shadow_candidate"},
            "data_coverage_summary": {"promotion_ready": False},
        },
    )
    _write_json(
        paths["repair"],
        {
            "status": "repair_burndown_ready",
            "active_exact_repair_targets": [],
            "source_replay_required_targets": [],
            "diagnostic_lookahead_only_targets": [],
            "exhausted_current_source_targets": [],
        },
    )
    _write_json(paths["attempts"], {"status": "repair_attempt_readback", "latest_attempts": []})
    _write_json(paths["profit"], {"status": "research_paper_capture_queue", "evidence_repair_queue": [], "quarantine_queue": []})
    return paths


def _build(paths: dict[str, Path]) -> dict:
    return burndown.build_report(
        tournament_path=paths["tournament"],
        robust_edge_path=paths["robust_edge"],
        repair_burndown_path=paths["repair"],
        repair_attempts_path=paths["attempts"],
        profit_capture_queue_path=paths["profit"],
        generated_at_utc=NOW,
    )


def test_missing_tournament_artifact_fails_closed(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    paths["tournament"].unlink()
    report = _build(paths)
    assert report["overall_status"] == "blocked_missing_readbacks"
    assert report["live_entry_allowed"] is False


def test_missing_robust_edge_artifact_fails_closed(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    paths["robust_edge"].unlink()
    report = _build(paths)
    assert report["overall_status"] == "blocked_missing_readbacks"
    assert report["auto_track_allowed"] is False


def test_malformed_json_fails_closed_without_crashing(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    paths["tournament"].write_text("{", encoding="utf8")
    report = _build(paths)
    assert report["overall_status"] == "blocked_missing_readbacks"
    assert report["source_artifacts"]["hypothesis_tournament"]["status"] == "malformed"


def test_zero_bid_blocker_becomes_tradability_failure_do_not_repair(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    _write_json(
        paths["repair"],
        {
            "active_exact_repair_targets": [
                {
                    "lane_id": "lane_a",
                    "symbol": "CVX",
                    "contract_symbol": "CVX260101C00100000",
                    "missing_quote_date": "2026-01-01",
                    "burndown_status": "active_unattempted_exact_repair",
                    "unpriced_reason": "zero_bid_exit_rate_above_2",
                }
            ]
        },
    )
    report = _build(paths)
    row = report["do_not_repeat_queue"][0]
    assert row["blocker_type"] == "zero_bid_tradability_failure"
    assert row["repair_actionability"] == "blocked_zero_bid_tradability"
    assert row["expected_value_class"] == "do_not_repair"


def test_lookahead_only_blocker_is_diagnostic_not_exact_proof(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    _write_json(
        paths["repair"],
        {
            "diagnostic_lookahead_only_targets": [
                {
                    "lane_id": "lane_a",
                    "symbol": "NEM",
                    "contract_symbol": "NEM260101C00100000",
                    "missing_quote_date": "2026-01-01",
                    "burndown_status": "diagnostic_lookahead_only_not_exact_proof",
                }
            ]
        },
    )
    report = _build(paths)
    row = report["diagnostic_only_queue"][0]
    assert row["blocker_type"] == "lookahead_only_not_proof"
    assert row["is_exact_proof_repair"] is False
    assert row["expected_value_class"] == "diagnostic_only"


def test_exhausted_current_source_has_do_not_repeat_reason(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    _write_json(
        paths["repair"],
        {
            "exhausted_current_source_targets": [
                {
                    "lane_id": "lane_a",
                    "symbol": "AAPL",
                    "contract_symbol": "AAPL260101C00100000",
                    "missing_quote_date": "2026-01-01",
                    "burndown_status": "excluded_current_source_exhausted",
                }
            ]
        },
    )
    report = _build(paths)
    row = report["do_not_repeat_queue"][0]
    assert row["repair_actionability"] == "blocked_exhausted_source"
    assert "current source" in row["do_not_repeat_reason"]


def test_unexhausted_exact_missing_quote_gets_proof_value_repair(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    _write_json(
        paths["repair"],
        {
            "active_exact_repair_targets": [
                {
                    "lane_id": "lane_a",
                    "symbol": "CAT",
                    "contract_symbol": "CAT260101C00100000",
                    "missing_quote_date": "2026-01-01",
                    "missing_leg_role": "exit",
                    "source_artifact": "data/options-validation/runs/example.json",
                    "burndown_status": "active_unattempted_exact_repair",
                    "evidence_repair_priority": "high",
                }
            ]
        },
    )
    report = _build(paths)
    row = report["ranked_repair_queue"][0]
    assert row["blocker_type"] == "repairable_unpriced_exit"
    assert row["expected_value_class"] == "high_proof_value"
    assert row["is_exact_proof_repair"] is True
    assert "--plan-only" in row["safe_plan_only_command"]


def test_source_replay_rows_rank_before_import_attempts(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    _write_json(
        paths["repair"],
        {
            "source_replay_required_targets": [
                {
                    "lane_id": "lane_a",
                    "symbol": "AAPL",
                    "contract_symbol": "AAPL260101C00100000",
                    "missing_quote_date": "2026-01-01",
                    "burndown_status": "source_replay_required_before_graduation",
                    "evidence_repair_priority": "high",
                }
            ],
            "active_exact_repair_targets": [
                {
                    "lane_id": "lane_b",
                    "symbol": "CAT",
                    "contract_symbol": "CAT260101C00100000",
                    "missing_quote_date": "2026-01-01",
                    "missing_leg_role": "exit",
                    "source_artifact": "data/options-validation/runs/example.json",
                    "burndown_status": "active_unattempted_exact_repair",
                    "evidence_repair_priority": "high",
                }
            ],
        },
    )
    report = _build(paths)
    assert report["ranked_repair_queue"][0]["repair_actionability"] == "source_replay_first"


def test_quarantined_no_chase_lane_is_low_or_not_actionable(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    _write_json(
        paths["profit"],
        {
            "quarantine_queue": [
                {"lane_id": "bad_lane", "symbol": "QQQ", "repair_actionability": "quarantine_do_not_repair"}
            ]
        },
    )
    report = _build(paths)
    row = next(item for item in report["diagnostic_only_queue"] + report["do_not_repeat_queue"] + report["ranked_repair_queue"] if item["lane_id"] == "bad_lane")
    assert row["blocker_type"] == "quarantine_no_chase"
    assert row["repair_actionability"] == "not_worth_repair"


def test_holdout_gap_and_pf_lower_bound_gap_are_reported_separately(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    _write_json(
        paths["tournament"],
        {
            "overall_status": "paper_shadow_only",
            "candidate_rankings": [
                {"candidate_id": "combined", "lane_id": "combined", "holdout_rows": 28, "profit_factor_lower_bound": 0.61}
            ],
        },
    )
    report = _build(paths)
    assert report["holdout_gap_summary"]["gap_rows"] == 2
    assert report["pf_lower_bound_gap_summary"]["current_profit_factor_lower_bound"] == 0.61
    assert report["pf_lower_bound_gap_summary"]["count_repair_is_not_pf_repair"] is True


def test_report_does_not_output_mutating_commands_as_executed_actions(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    report = _build(paths)
    commands = "\n".join(report["recommended_safe_command_order"])
    assert "--plan-only" in commands
    assert "--dry-run" in commands
    assert "submit" not in commands.lower()
    assert "broker" not in commands.lower()


def test_script_never_allows_broker_live_or_auto_track(tmp_path: Path) -> None:
    paths = _base_payloads(tmp_path)
    report = _build(paths)
    assert report["broker_order_allowed"] is False
    assert report["live_entry_allowed"] is False
    assert report["auto_track_allowed"] is False
    assert report["current_algorithm_status"]["broker_order_allowed"] is False
