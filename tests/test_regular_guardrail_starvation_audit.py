from __future__ import annotations

from pathlib import Path

from scripts.audit_regular_guardrail_starvation import (
    _summarize_scan_result,
    _status_from_overall,
    markdown_report,
    write_outputs,
)


def test_summarize_scan_result_flags_guardrail_starvation():
    result = {
        "candidate_count": 2,
        "returned_count": 0,
        "candidate_audit_picks": [
            {
                "ticker": "AAPL",
                "guardrail_decision": "blocked",
                "guardrail_reasons": ["debit too high"],
            },
            {
                "ticker": "MSFT",
                "guardrail_decision": "blocked",
                "guardrail_reasons": ["wide spread"],
            },
        ],
        "scan_funnel": {"raw_candidates": 2, "guardrail_filtered_out": 2},
    }

    summary = _summarize_scan_result("short_term", result, top_limit=3)

    assert summary["starvation_flag"] is True
    assert summary["candidate_decision_counts"] == {"blocked": 2}
    assert summary["block_rate_pct"] == 100.0


def test_status_distinguishes_upstream_zero_candidates_from_guardrail_starvation():
    assert (
        _status_from_overall(
            {
                "playbooks_completed": 2,
                "candidate_count_total": 0,
                "zero_candidate_playbooks": ["short_term", "swing"],
                "starvation_playbooks": [],
            },
            [],
        )
        == "upstream_zero_candidate_scan_pressure"
    )
    assert (
        _status_from_overall(
            {
                "playbooks_completed": 2,
                "candidate_count_total": 2,
                "zero_candidate_playbooks": [],
                "starvation_playbooks": ["short_term"],
            },
            [],
        )
        == "guardrail_starvation_detected"
    )


def test_write_outputs_creates_latest_json_and_markdown(tmp_path: Path):
    report = {
        "generated_at_utc": "2026-06-01T00:00:00Z",
        "overall": {
            "status": "upstream_zero_candidate_scan_pressure",
            "playbooks_completed": 13,
            "playbooks_requested": 13,
            "candidate_count_total": 0,
            "returned_count_total": 0,
            "candidate_decision_counts": {},
            "starvation_playbooks": [],
            "zero_candidate_playbooks": ["short_term"],
            "top_drop_counts": [{"value": "option_liquidity", "count": 96}],
            "top_upstream_drop_details": [
                {
                    "drop_key": "option_liquidity",
                    "detail": "illiquid_quote",
                    "count": 32,
                    "tickers": ["AAPL"],
                }
            ],
        },
        "settings": {"market_open_at_run": False},
    }
    doc_path = tmp_path / "audit.md"

    artifacts = write_outputs(report, output_dir=tmp_path, doc_path=doc_path)

    assert Path(artifacts["latest_json"]).exists()
    assert doc_path.exists()
    assert "not promoted guardrail starvation" in markdown_report(report)
