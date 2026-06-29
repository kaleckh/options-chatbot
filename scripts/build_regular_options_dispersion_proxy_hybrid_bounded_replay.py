from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_dispersion_proxy_hybrid_bounded_replay"
CONCEPT_ID = "index_constituent_dispersion_proxy_defined_risk_hybrid_v1"
DEFAULT_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-dispersion-proxy-hybrid-replay-readiness" / "latest.json"
DEFAULT_PROXY = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-dispersion-concentration-proxy" / "latest.json"
DEFAULT_CANDIDATE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-dispersion-proxy-hybrid-bounded-replay" / "candidate_rows.jsonl"
DEFAULT_OPTIONS_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-dispersion-proxy-hybrid-bounded-replay"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-dispersion-proxy-hybrid-bounded-replay.md"

CONTRACT_MULTIPLIER = 100.0
PER_CONTRACT_FEE_USD = 0.65
ROUND_TRIP_CONTRACT_SIDES = 8

READ_ONLY_FLAGS = {
    "read_only": True,
    "research_only": True,
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
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
    "do_not_import_quotes",
    "do_not_mutate_options_history_db",
    "do_not_append_forward_cohort_rows",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_submit_broker_orders",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_count_historical_rows_as_forward_proof",
    "do_not_use_midpoint_last_eod_manual_synthetic_or_lookahead_prices",
)

REQUIRED_CANDIDATE_FIELDS = (
    "pair_id",
    "proxy_date_et",
    "entry_date_et",
    "entry_minute_et",
    "exit_date_et",
    "exit_minute_et",
    "index_debit_long_contract",
    "index_debit_short_contract",
    "constituent_credit_short_contract",
    "constituent_credit_long_contract",
)

TRUSTED_EXECUTABLE_QUOTE_SOURCES = {
    "opra_nbbo",
    "trusted_opra_nbbo",
    "trusted_intraday_opra_nbbo",
    "thetadata_opra_nbbo_1m",
    "alpaca_opra",
    "alpaca_opra_daily_snapshot",
}


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
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["report_id"] = payload.get("report_id")
    meta["status_value"] = payload.get("status")
    return payload, meta


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "status": "missing", "row_count": 0, "malformed_rows": 0}
    if not path.exists():
        return [], meta
    rows: list[dict[str, Any]] = []
    malformed = 0
    try:
        lines = path.read_text(encoding="utf8").splitlines()
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    for raw in lines:
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            malformed += 1
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    meta["malformed_rows"] = malformed
    return rows, meta


def _connect_options_db(path: Path) -> tuple[sqlite3.Connection | None, dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return None, meta
    try:
        conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        meta["status"] = "loaded_read_only"
        return conn, meta
    except sqlite3.Error as exc:
        meta["status"] = "unreadable"
        meta["error"] = str(exc)
        return None, meta


def _trusted_quote(
    conn: sqlite3.Connection | None,
    *,
    contract_symbol: str,
    quote_date: str,
    max_minute: int | None,
) -> dict[str, Any] | None:
    if conn is None or not contract_symbol or not quote_date or max_minute is None:
        return None
    source_placeholders = ", ".join("?" for _ in TRUSTED_EXECUTABLE_QUOTE_SOURCES)
    params: list[Any] = [contract_symbol, quote_date, max_minute, *sorted(TRUSTED_EXECUTABLE_QUOTE_SOURCES)]
    query = f"""
        select q.bid, q.ask, q.quote_minute_et, q.source_batch_id, b.source_label
        from option_quote_snapshots q
        join import_batches b on b.id = q.source_batch_id
        where q.contract_symbol = ?
          and q.snapshot_kind = 'intraday'
          and q.quote_date_et = ?
          and b.data_trust = 'trusted'
          and q.bid is not null
          and q.ask is not null
          and q.quote_minute_et <= ?
          and lower(b.source_label) in ({source_placeholders})
        order by q.quote_minute_et desc
        limit 1
    """
    try:
        row = conn.execute(query, params).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return {
        "bid": float(row["bid"]),
        "ask": float(row["ask"]),
        "quote_minute_et": int(row["quote_minute_et"]),
        "source_batch_id": int(row["source_batch_id"]),
        "source_label": str(row["source_label"]),
    }


def _quote_status(*, quotes: tuple[dict[str, Any] | None, ...]) -> str:
    if any(quote is None for quote in quotes):
        return "missing_leg_quote"
    for quote in quotes:
        assert quote is not None
        if quote["bid"] <= 0 or quote["ask"] <= 0:
            return "zero_or_nonpositive_bid_ask"
        if quote["ask"] < quote["bid"]:
            return "crossed_quote"
    return "resolved"


def _minute(row: dict[str, Any], key: str) -> int | None:
    minute = row.get(key)
    try:
        return int(minute) if minute not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _candidate_blockers(row: dict[str, Any]) -> list[str]:
    blockers = [f"missing_candidate_field:{field}" for field in REQUIRED_CANDIDATE_FIELDS if not row.get(field)]
    concept = str(row.get("concept_id") or CONCEPT_ID)
    if concept != CONCEPT_ID:
        blockers.append("unexpected_concept_id")
    if row.get("protected_holdout_overlap") is True:
        blockers.append("protected_holdout_overlap")
    if row.get("undefined_or_uncapped_pair_risk_allowed") is True:
        blockers.append("undefined_or_uncapped_pair_risk")
    return blockers


def _resolve_candidate(row: dict[str, Any], conn: sqlite3.Connection | None) -> dict[str, Any]:
    pricing_blockers = set(_candidate_blockers(row))
    entry_date = str(row.get("entry_date_et") or "")
    exit_date = str(row.get("exit_date_et") or "")
    entry_minute = _minute(row, "entry_minute_et")
    exit_minute = _minute(row, "exit_minute_et")
    index_long = str(row.get("index_debit_long_contract") or "")
    index_short = str(row.get("index_debit_short_contract") or "")
    constituent_short = str(row.get("constituent_credit_short_contract") or "")
    constituent_long = str(row.get("constituent_credit_long_contract") or "")

    entry_index_long = _trusted_quote(conn, contract_symbol=index_long, quote_date=entry_date, max_minute=entry_minute)
    entry_index_short = _trusted_quote(conn, contract_symbol=index_short, quote_date=entry_date, max_minute=entry_minute)
    entry_constituent_short = _trusted_quote(conn, contract_symbol=constituent_short, quote_date=entry_date, max_minute=entry_minute)
    entry_constituent_long = _trusted_quote(conn, contract_symbol=constituent_long, quote_date=entry_date, max_minute=entry_minute)
    exit_index_long = _trusted_quote(conn, contract_symbol=index_long, quote_date=exit_date, max_minute=exit_minute)
    exit_index_short = _trusted_quote(conn, contract_symbol=index_short, quote_date=exit_date, max_minute=exit_minute)
    exit_constituent_short = _trusted_quote(conn, contract_symbol=constituent_short, quote_date=exit_date, max_minute=exit_minute)
    exit_constituent_long = _trusted_quote(conn, contract_symbol=constituent_long, quote_date=exit_date, max_minute=exit_minute)

    entry_status = _quote_status(
        quotes=(entry_index_long, entry_index_short, entry_constituent_short, entry_constituent_long)
    )
    exit_status = _quote_status(
        quotes=(exit_index_long, exit_index_short, exit_constituent_short, exit_constituent_long)
    )
    if entry_status != "resolved":
        pricing_blockers.add(f"entry_{entry_status}")
    if exit_status != "resolved":
        pricing_blockers.add(f"exit_{exit_status}")

    entry_cashflow = None
    exit_value = None
    net_pnl = None
    max_loss = _safe_float(row.get("pair_max_loss_usd"))
    collateral = _safe_float(row.get("required_collateral_usd"))
    if max_loss is None:
        pricing_blockers.add("missing_pair_max_loss_usd")
    if collateral is None:
        pricing_blockers.add("missing_required_collateral_usd")
    if entry_status == "resolved":
        assert entry_index_long and entry_index_short and entry_constituent_short and entry_constituent_long
        debit_entry = entry_index_long["ask"] - entry_index_short["bid"]
        credit_entry = entry_constituent_short["bid"] - entry_constituent_long["ask"]
        entry_cashflow = credit_entry - debit_entry
    if exit_status == "resolved":
        assert exit_index_long and exit_index_short and exit_constituent_short and exit_constituent_long
        debit_exit = exit_index_long["bid"] - exit_index_short["ask"]
        credit_exit_debit = exit_constituent_short["ask"] - exit_constituent_long["bid"]
        exit_value = debit_exit - credit_exit_debit
    if entry_cashflow is not None and exit_value is not None:
        fees = ROUND_TRIP_CONTRACT_SIDES * PER_CONTRACT_FEE_USD
        net_pnl = (entry_cashflow + exit_value) * CONTRACT_MULTIPLIER - fees
    priced_exact = not pricing_blockers and net_pnl is not None
    proof_blockers = (
        [
            "independent_holdout_check_not_implemented",
            "independent_max_loss_collateral_check_not_implemented",
            "fee_slippage_stress_not_implemented",
            "bounded_replay_statistical_gate_not_satisfied",
        ]
        if priced_exact
        else []
    )
    all_blockers = sorted(pricing_blockers.union(proof_blockers))
    return {
        "pair_id": row.get("pair_id"),
        "proxy_date_et": row.get("proxy_date_et"),
        "entry_date_et": entry_date,
        "entry_minute_et": entry_minute,
        "exit_date_et": exit_date,
        "exit_minute_et": exit_minute,
        "index_debit_long_contract": index_long,
        "index_debit_short_contract": index_short,
        "constituent_credit_short_contract": constituent_short,
        "constituent_credit_long_contract": constituent_long,
        "denominator_status": "priced_exact_research_only_insufficient_proof" if priced_exact else "blocked_replay_candidate",
        "blockers": all_blockers,
        "pricing_blockers": sorted(pricing_blockers),
        "proof_blockers": proof_blockers,
        "side_aware_entry_quote_status": entry_status,
        "side_aware_exit_quote_status": exit_status,
        "side_aware_quotes_resolved": entry_status == "resolved" and exit_status == "resolved",
        "pair_entry_cashflow": round(entry_cashflow, 4) if entry_cashflow is not None else None,
        "pair_exit_value": round(exit_value, 4) if exit_value is not None else None,
        "fees_usd": ROUND_TRIP_CONTRACT_SIDES * PER_CONTRACT_FEE_USD,
        "net_pnl_usd": round(net_pnl, 2) if net_pnl is not None else None,
        "pair_max_loss_usd": max_loss,
        "required_collateral_usd": collateral,
        "priced_exact": priced_exact,
        "proof_qualified": False,
        "historical_rows_are_forward_proof": False,
    }


def _proxy_denominator_rows(proxy: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _as_list(proxy.get("proxy_rows")):
        item = _as_dict(row)
        if item.get("blockers"):
            continue
        rows.append(
            {
                "pair_id": f"proxy:{item.get('proxy_date_et')}:{item.get('index_carrier')}",
                "proxy_date_et": item.get("proxy_date_et"),
                "index_carrier": item.get("index_carrier"),
                "denominator_status": "blocked_missing_pair_contract_selection_surface",
                "blockers": ["missing_dispersion_pair_candidate_rows"],
                "proof_qualified": False,
                "historical_rows_are_forward_proof": False,
            }
        )
    return rows


def _profit_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl = [float(row["net_pnl_usd"]) for row in rows if _safe_float(row.get("net_pnl_usd")) is not None]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "priced_exact_rows": len(pnl),
        "net_pnl_usd": round(sum(pnl), 2) if pnl else 0.0,
        "win_count": len(wins),
        "loss_count": len(losses),
        "profit_factor": round(gross_win / gross_loss, 4) if gross_loss > 0 else (None if gross_win <= 0 else "inf"),
        "pf_lower_bound": None,
        "stress_pf": None,
    }


def _smallest_blocker(rows: list[dict[str, Any]], blockers: list[str]) -> str | None:
    if blockers:
        return blockers[0]
    counts: Counter[str] = Counter()
    for row in rows:
        for blocker in _as_list(row.get("blockers")):
            counts[str(blocker)] += 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _status(blockers: list[str], metrics: dict[str, Any]) -> str:
    if blockers:
        return "blocked_dispersion_proxy_hybrid_bounded_replay"
    if int(metrics.get("priced_exact_rows") or 0) <= 0:
        return "blocked_dispersion_proxy_hybrid_bounded_replay"
    if _safe_float(metrics.get("net_pnl_usd")) is not None and float(metrics["net_pnl_usd"]) <= 0:
        return "falsified_dispersion_proxy_hybrid_bounded_replay"
    return "implemented_dispersion_proxy_hybrid_bounded_replay_research_only"


def build_report(
    *,
    readiness_path: Path = DEFAULT_READINESS,
    proxy_path: Path = DEFAULT_PROXY,
    candidate_rows_path: Path = DEFAULT_CANDIDATE_ROWS,
    options_db_path: Path = DEFAULT_OPTIONS_DB,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    readiness, readiness_meta = _load_json(readiness_path, required=True)
    proxy, proxy_meta = _load_json(proxy_path, required=True)
    candidate_rows, candidate_meta = _load_jsonl(candidate_rows_path)
    conn, options_db_meta = _connect_options_db(options_db_path)
    try:
        resolved_rows = [_resolve_candidate(row, conn) for row in candidate_rows]
    finally:
        if conn is not None:
            conn.close()
    if not candidate_rows:
        resolved_rows = _proxy_denominator_rows(proxy)

    readiness_ready = readiness.get("status") == "dispersion_proxy_hybrid_replay_readiness_ready" and not readiness.get("blockers")
    blockers: list[str] = []
    if not readiness_ready:
        blockers.append("dispersion_proxy_hybrid_readiness_not_ready")
    if proxy_meta.get("status") != "loaded":
        blockers.append("point_in_time_dispersion_proxy_artifact_missing")
    if candidate_meta.get("status") != "loaded" or not candidate_rows:
        blockers.append("missing_dispersion_pair_candidate_rows")
    if options_db_meta.get("status") != "loaded_read_only":
        blockers.append("options_history_db_unavailable_for_read_only_quote_lookup")
    if any(row.get("blockers") for row in resolved_rows):
        blockers.append("bounded_replay_rows_blocked")
    blockers = list(dict.fromkeys(blockers))

    metrics = _profit_metrics([row for row in resolved_rows if row.get("priced_exact") is True])
    counts = Counter(str(row.get("denominator_status") or "unknown") for row in resolved_rows)
    latest_four_or_post_freeze_rows = 0
    if int(metrics.get("priced_exact_rows") or 0) > 0:
        if int(metrics.get("priced_exact_rows") or 0) < 30:
            blockers.append("bounded_replay_priced_rows_below_30")
        if latest_four_or_post_freeze_rows < 30:
            blockers.append("bounded_replay_latest_four_or_post_freeze_rows_below_30")
        if metrics.get("pf_lower_bound") is None:
            blockers.append("bounded_replay_pf_lower_bound_missing")
        if metrics.get("stress_pf") is None:
            blockers.append("bounded_replay_stress_pf_missing")
        if not any(row.get("proof_qualified") is True for row in resolved_rows):
            blockers.append("bounded_replay_no_proof_qualified_rows")
    blockers = list(dict.fromkeys(blockers))
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        **READ_ONLY_FLAGS,
        "scope": "read_only_dispersion_proxy_hybrid_bounded_replay",
        "concept_id": CONCEPT_ID,
        "status": _status(blockers, metrics),
        "source_artifacts": {
            "readiness": readiness_meta,
            "point_in_time_dispersion_proxy": proxy_meta,
            "candidate_rows": candidate_meta,
            "options_history_db": options_db_meta,
        },
        "denominator_rows": len(resolved_rows),
        "denominator_status_counts": {key: counts[key] for key in sorted(counts)},
        "strict_new_exact_completed_rows": sum(1 for row in resolved_rows if row.get("denominator_status") == "strict_new_exact_completed"),
        "latest_four_or_post_freeze_rows": latest_four_or_post_freeze_rows,
        "priced_exact_rows": metrics["priced_exact_rows"],
        "quote_coverage_pct": round(metrics["priced_exact_rows"] / len(resolved_rows) * 100.0, 4) if resolved_rows else 0.0,
        "profit_metrics": metrics,
        "blockers": blockers,
        "smallest_next_blocker": _smallest_blocker(resolved_rows, blockers),
        "resolved_rows": resolved_rows[:200],
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    if report.get("accepted_profitability") is not False:
        raise ValueError("bounded replay cannot accept profitability")
    for row in _as_list(report.get("resolved_rows")):
        if _as_dict(row).get("historical_rows_are_forward_proof") is not False:
            raise ValueError("historical rows cannot be forward proof")


def render_markdown(report: dict[str, Any]) -> str:
    metrics = _as_dict(report.get("profit_metrics"))
    lines = [
        "# Regular Options Dispersion-Proxy Hybrid Bounded Replay",
        "",
        "This report is generated from `scripts/build_regular_options_dispersion_proxy_hybrid_bounded_replay.py`. It is read-only research. It uses only existing local artifacts and trusted quote rows if available; it does not import quotes, mutate evidence stores, append cohort rows, change scanner policy, enable live validation or auto-track, submit broker orders, consume protected holdout, lower proof bars, or promote any lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Denominator rows: `{report.get('denominator_rows')}`.",
        f"- Priced exact rows: `{report.get('priced_exact_rows')}`.",
        f"- Strict-new exact completed rows: `{report.get('strict_new_exact_completed_rows')}`.",
        f"- Quote coverage pct: `{report.get('quote_coverage_pct')}`.",
        f"- Net P&L USD: `{metrics.get('net_pnl_usd')}`.",
        f"- Profit factor: `{metrics.get('profit_factor')}`.",
        f"- PF lower bound: `{metrics.get('pf_lower_bound')}`.",
        f"- Smallest next blocker: `{report.get('smallest_next_blocker')}`.",
        "",
        "## Denominator Status Counts",
        "",
    ]
    counts = _as_dict(report.get("denominator_status_counts"))
    lines.extend(f"- `{key}`: `{value}`." for key, value in sorted(counts.items())) if counts else lines.append("- None.")
    lines.extend(["", "## Blockers", ""])
    blockers = _as_list(report.get("blockers"))
    lines.extend(f"- `{item}`." for item in blockers) if blockers else lines.append("- None.")
    lines.extend(
        [
            "",
            "## Current Evidence Boundary",
            "",
            "- The bounded replay is a research pricing harness, not accepted profitability.",
            "- Priced rows remain historical research rows unless independent holdout, max-loss/collateral, slippage/stress, statistical, and strict forward proof gates are satisfied.",
            "- Historical proxy rows are not forward proof, promotion evidence, or live/broker/autotrack permission.",
        ]
    )
    lines.extend(["", "## Forbidden Actions", ""])
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOCS_REPORT) -> dict[str, str]:
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
    parser = argparse.ArgumentParser(description="Build a read-only bounded replay for the dispersion-proxy hybrid branch.")
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--point-in-time-dispersion-proxy", type=Path, default=DEFAULT_PROXY)
    parser.add_argument("--candidate-rows", type=Path, default=DEFAULT_CANDIDATE_ROWS)
    parser.add_argument("--options-db", type=Path, default=DEFAULT_OPTIONS_DB)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    report = build_report(
        readiness_path=args.readiness,
        proxy_path=args.point_in_time_dispersion_proxy,
        candidate_rows_path=args.candidate_rows,
        options_db_path=args.options_db,
    )
    if not args.no_write:
        report["artifacts"] = write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
