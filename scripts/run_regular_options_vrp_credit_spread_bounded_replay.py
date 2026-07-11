from __future__ import annotations

# ruff: noqa: E402

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import (
    build_regular_options_vrp_credit_spread_structure_harness as structure_harness,
)


REPORT_ID = "regular_options_vrp_credit_spread_bounded_replay"
CONCEPT_ID = structure_harness.CONCEPT_ID
EXPECTED_STRUCTURE = structure_harness.EXPECTED_STRUCTURE

DEFAULT_PREREGISTERED_PLAYBOOK = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-preregistered-vrp-credit-spread-playbook"
    / "latest.json"
)
DEFAULT_STRUCTURE_HARNESS = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-vrp-credit-spread-structure-harness"
    / "latest.json"
)
DEFAULT_HOLDOUT_CONTRACT = ROOT / "data" / "contracts" / "forward-holdout-contract.json"
DEFAULT_QUOTES_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-vrp-credit-spread-bounded-replay"
)
DEFAULT_DOCS_REPORT = (
    ROOT / "docs" / "regular-options-vrp-credit-spread-bounded-replay.md"
)

READ_ONLY_FLAGS = {
    "read_only": True,
    "accepted_profitability": False,
    "historical_replay_performed": False,
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
}

FORBIDDEN_ACTIONS = (
    "do_not_create_broker_orders",
    "do_not_prepare_orders",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_run_or_change_production_scanners",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_import_quotes",
    "do_not_mutate_evidence_stores",
    "do_not_append_forward_cohort_rows",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_claim_accepted_profitability",
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


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "error": None,
    }
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
    meta["report_id"] = payload.get("report_id")
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["source_status"] = payload.get("status")
    return payload, meta


def _load_rows(path: Path | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if path is None:
        return [], {
            "path": None,
            "required": False,
            "exists": False,
            "status": "not_requested",
            "row_count": 0,
        }
    meta = {
        "path": _rel(path),
        "required": False,
        "exists": path.exists(),
        "status": "missing",
        "row_count": 0,
        "malformed_rows": 0,
    }
    if not path.exists():
        return [], meta
    rows: list[dict[str, Any]] = []
    malformed = 0
    text = path.read_text(encoding="utf8").strip()
    if not text:
        meta["status"] = "loaded"
        return rows, meta
    try:
        if text.startswith("["):
            payload = json.loads(text)
            rows = (
                [row for row in payload if isinstance(row, dict)]
                if isinstance(payload, list)
                else []
            )
            malformed = 0 if isinstance(payload, list) else 1
        else:
            for line in text.splitlines():
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    malformed += 1
    except json.JSONDecodeError:
        malformed += 1
    meta["status"] = "loaded" if malformed == 0 else "loaded_with_malformed_rows"
    meta["row_count"] = len(rows)
    meta["malformed_rows"] = malformed
    return rows, meta


def _preregistration_valid(playbook: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if playbook.get("concept_id") != CONCEPT_ID:
        reasons.append("unexpected_concept_id")
    if playbook.get("status") != "preregistered_design_only":
        reasons.append("unexpected_status")
    if playbook.get("structure") != EXPECTED_STRUCTURE:
        reasons.append("unexpected_structure")
    if playbook.get("accepted_profitability") is not False:
        reasons.append("accepted_profitability_not_false")
    return not reasons, reasons


def _protected_holdout_start(holdout: dict[str, Any]) -> str:
    return str(
        holdout.get("protected_holdout_start")
        or _as_dict(holdout.get("protected_range")).get("start_date")
        or structure_harness.PROTECTED_HOLDOUT_START
    )


def _candidate_geometry_ready(playbook: dict[str, Any]) -> bool:
    geometry = _as_dict(
        playbook.get("candidate_geometry")
        or _as_dict(playbook.get("concept")).get("candidate_geometry")
    )
    required = (
        "dte_min",
        "dte_max",
        "short_put_moneyness_or_delta",
        "long_put_distance",
        "exit_policy",
    )
    return all(
        key in geometry and geometry.get(key) not in (None, "") for key in required
    )


def _classify_rows(
    rows: list[dict[str, Any]], *, protected_holdout_start: str
) -> list[dict[str, Any]]:
    classified: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        result = structure_harness.classify_candidate(
            row, protected_holdout_start=protected_holdout_start
        )
        classified.append(
            {
                "row_number": index,
                "ticker": row.get("ticker") or row.get("underlying"),
                "entry_date": row.get("entry_date") or row.get("selection_date"),
                **result,
            }
        )
    return classified


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    exact = [
        row
        for row in rows
        if row.get("denominator_status") in {"exact_closed", "expired_settled"}
    ]
    pnl = [_safe_float(row.get("net_pnl_usd")) for row in exact]
    pnl = [value for value in pnl if value is not None]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    status_counts = Counter(str(row.get("denominator_status")) for row in rows)
    ticker_counts = Counter(str(row.get("ticker")) for row in exact)
    month_counts = Counter(str(row.get("entry_date") or "")[:7] for row in exact)
    return {
        "total_denominator_rows": len(rows),
        "denominator_counts": dict(sorted(status_counts.items())),
        "exact_closed_or_settled_rows": len(exact),
        "net_usd_total": round(sum(pnl), 2),
        "avg_net_usd": round(sum(pnl) / len(pnl), 2) if pnl else None,
        "win_rate": round(len(wins) / len(pnl), 4) if pnl else None,
        "point_profit_factor": round(gross_profit / gross_loss, 4)
        if gross_loss
        else None,
        "bootstrap_pf_lower_bound_5pct": None,
        "stress_pf": None,
        "quote_coverage": round(len(exact) / len(rows), 4) if rows else 0.0,
        "zero_bid_or_untradable_count": status_counts.get("zero_bid_untradable", 0),
        "missing_quote_count": status_counts.get("missing_required_quote", 0),
        "assignment_or_expiration_blocked_count": sum(
            1
            for row in rows
            if _as_dict(row.get("assignment_expiration")).get("blocker")
        ),
        "protected_holdout_blocked_count": status_counts.get(
            "protected_holdout_blocked", 0
        ),
        "largest_ticker_share": round(max(ticker_counts.values()) / len(exact), 4)
        if exact and ticker_counts
        else 0.0,
        "largest_entry_month_share": round(max(month_counts.values()) / len(exact), 4)
        if exact and month_counts
        else 0.0,
        "largest_winner_dependency": round(max(wins) / gross_profit, 4)
        if wins and gross_profit
        else 0.0,
    }


def _status_from_metrics(metrics: dict[str, Any], blockers: list[str]) -> str:
    if blockers:
        return "blocked_vrp_credit_spread_bounded_replay_gate"
    if (
        metrics["exact_closed_or_settled_rows"] >= 30
        and metrics["net_usd_total"] > 0
        and (metrics["point_profit_factor"] or 0) > 1.18
    ):
        return "historical_candidate_for_future_forward_shadow"
    return "falsified_vrp_credit_spread_replay"


def build_report(
    *,
    preregistered_playbook_path: Path = DEFAULT_PREREGISTERED_PLAYBOOK,
    structure_harness_path: Path = DEFAULT_STRUCTURE_HARNESS,
    holdout_contract_path: Path = DEFAULT_HOLDOUT_CONTRACT,
    quotes_db_path: Path = DEFAULT_QUOTES_DB,
    fixture_candidates_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated_at = generated_at_utc or _utc_now_iso()
    playbook, playbook_meta = _load_json(preregistered_playbook_path, required=True)
    harness_report, harness_meta = _load_json(structure_harness_path, required=True)
    holdout, holdout_meta = _load_json(holdout_contract_path, required=True)
    fixture_rows, fixture_meta = _load_rows(fixture_candidates_path)
    prereg_valid, prereg_reasons = (
        _preregistration_valid(playbook)
        if playbook_meta["status"] == "loaded"
        else (False, ["missing_preregistration_artifact"])
    )
    protected_start = _protected_holdout_start(holdout)
    blockers: list[str] = []
    replay_rows: list[dict[str, Any]] = []
    historical_replay_performed = False
    if not prereg_valid:
        blockers.extend(prereg_reasons)
    if harness_meta["status"] != "loaded":
        blockers.append("missing_vrp_credit_spread_structure_harness")
    elif harness_report.get("status") != "ready_for_bounded_read_only_vrp_replay":
        blockers.extend(
            str(item)
            for item in _as_list(harness_report.get("remaining_blockers"))
            if item
        )
    if not _candidate_geometry_ready(playbook):
        blockers.append("missing_preregistered_candidate_geometry")
    if not DEFAULT_QUOTES_DB.exists() and quotes_db_path == DEFAULT_QUOTES_DB:
        blockers.append("missing_existing_trusted_quote_store")
    if fixture_candidates_path is None and not blockers:
        blockers.append("missing_native_vrp_candidate_generation_engine")
    if fixture_rows and not blockers:
        replay_rows = _classify_rows(
            fixture_rows, protected_holdout_start=protected_start
        )
        historical_replay_performed = True
    elif fixture_rows and blockers:
        replay_rows = [
            {
                "denominator_status": "replay_gate_blocked",
                "blockers": blockers,
                "source_rows_not_replayed": len(fixture_rows),
            }
        ]
    metrics = _metrics(replay_rows)
    status = _status_from_metrics(metrics, sorted(set(blockers)))
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at,
        "status": status,
        **{
            **READ_ONLY_FLAGS,
            "historical_replay_performed": historical_replay_performed,
        },
        "scope": "read_only_vrp_credit_spread_bounded_replay_gate",
        "concept_id": playbook.get("concept_id") if playbook else None,
        "structure": playbook.get("structure") if playbook else None,
        "historical_window": _as_dict(
            playbook.get("historical_research_window")
            or _as_dict(playbook.get("concept")).get("historical_research_window")
        ),
        "protected_holdout_start": protected_start,
        "replay_gate_blockers": sorted(set(blockers)),
        "replay_rows": replay_rows,
        "metrics": metrics,
        "source_artifacts": {
            "preregistered_vrp_credit_spread_playbook": playbook_meta,
            "vrp_credit_spread_structure_harness": harness_meta,
            "forward_holdout_contract": holdout_meta,
            "existing_quotes_db": {
                "path": _rel(quotes_db_path),
                "exists": quotes_db_path.exists(),
                "status": "present" if quotes_db_path.exists() else "missing",
            },
            "fixture_candidates": fixture_meta,
        },
        "preregistration_validation": {
            "valid": prereg_valid,
            "reasons": prereg_reasons,
            "required_concept_id": CONCEPT_ID,
            "required_status": "preregistered_design_only",
            "required_structure": EXPECTED_STRUCTURE,
        },
        "proof_boundary": "historical replay rows are research nomination/falsification only and never accepted forward profitability proof",
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if key == "historical_replay_performed":
            continue
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if (
        report.get("accepted_profitability") is not False
        or report.get("promotion_ready") is not False
    ):
        raise ValueError(
            "historical replay gate cannot mark accepted profitability or promotion"
        )


def _fmt_bool(value: Any) -> str:
    return "true" if value is True else "false" if value is False else str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options VRP Credit Spread Bounded Replay",
        "",
        "This generated report is read-only. It gates a bounded VRP put-credit-spread replay behind preregistration, the completed structure harness, existing trusted quote data, and protected-holdout checks.",
        "",
        "## Summary",
        "",
        f"- Status: `{report['status']}`.",
        f"- Concept: `{report.get('concept_id')}`.",
        f"- Historical replay performed: `{_fmt_bool(report['historical_replay_performed'])}`.",
        f"- Accepted profitability: `{_fmt_bool(report['accepted_profitability'])}`.",
        f"- Quotes imported: `{_fmt_bool(report['quotes_imported'])}`.",
        f"- Protected holdout consumed: `{_fmt_bool(report['protected_holdout_consumed'])}`.",
        "",
        "## Replay Gate Blockers",
        "",
    ]
    if report.get("replay_gate_blockers"):
        lines.extend(
            f"- `{item}`" for item in _as_list(report.get("replay_gate_blockers"))
        )
    else:
        lines.append("- None.")
    metrics = _as_dict(report.get("metrics"))
    lines.extend(
        [
            "",
            "## Metrics",
            "",
            f"- Total denominator rows: `{metrics.get('total_denominator_rows')}`.",
            f"- Exact closed or settled rows: `{metrics.get('exact_closed_or_settled_rows')}`.",
            f"- Net USD total: `{metrics.get('net_usd_total')}`.",
            f"- Point PF: `{metrics.get('point_profit_factor')}`.",
            f"- Quote coverage: `{metrics.get('quote_coverage')}`.",
            "",
            "## Forbidden Actions",
            "",
        ]
    )
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
        path.write_text(
            json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n",
            encoding="utf8",
        )
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the read-only VRP credit-spread bounded replay gate."
    )
    parser.add_argument(
        "--preregistered-playbook", type=Path, default=DEFAULT_PREREGISTERED_PLAYBOOK
    )
    parser.add_argument(
        "--structure-harness", type=Path, default=DEFAULT_STRUCTURE_HARNESS
    )
    parser.add_argument(
        "--holdout-contract", type=Path, default=DEFAULT_HOLDOUT_CONTRACT
    )
    parser.add_argument("--quotes-db", type=Path, default=DEFAULT_QUOTES_DB)
    parser.add_argument("--fixture-candidates", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report(
        preregistered_playbook_path=args.preregistered_playbook,
        structure_harness_path=args.structure_harness,
        holdout_contract_path=args.holdout_contract,
        quotes_db_path=args.quotes_db,
        fixture_candidates_path=args.fixture_candidates,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(
            report, output_dir=args.output_dir, docs_report=args.docs_report
        )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report))
    return 0 if report["preregistration_validation"]["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
