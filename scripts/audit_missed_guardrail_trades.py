from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER_DB = ROOT / "data" / "options-validation" / "forward_tracking_authoritative.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "missed-guardrail-trades"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_json(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or str(value).strip() == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or str(value).strip() == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _date_text(value: Any) -> str:
    return str(value or "")[:10]


def _inclusive_end_utc(date_to: date) -> str:
    return (date_to + timedelta(days=1)).isoformat()


def _read_session_events(conn: sqlite3.Connection, session_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not session_ids:
        return {}
    placeholders = ",".join("?" for _ in session_ids)
    events: dict[int, dict[str, Any]] = defaultdict(dict)
    rows = conn.execute(
        f"""
        SELECT session_id, event_type, payload_json
        FROM forward_events
        WHERE session_id IN ({placeholders})
          AND event_type IN ('scan_snapshot', 'tracked_positions_snapshot')
        ORDER BY id
        """,
        tuple(session_ids),
    ).fetchall()
    for row in rows:
        session_id = int(row["session_id"])
        event_type = str(row["event_type"] or "")
        events[session_id][event_type] = _safe_json(row["payload_json"], {} if event_type == "scan_snapshot" else [])
    return events


def _position_recommendation(position: dict[str, Any]) -> str:
    latest_review = position.get("latest_review") if isinstance(position.get("latest_review"), dict) else {}
    value = (
        position.get("last_recommendation")
        or latest_review.get("recommendation")
        or ""
    )
    return str(value or "").strip().upper() or "UNKNOWN"


def _tracked_position_summary(positions: Any, exposure: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in list(positions or []) if isinstance(row, dict)]
    open_rows = [row for row in rows if str(row.get("status") or "").strip().lower() != "closed"]
    recommendation_counts = Counter(_position_recommendation(row) for row in open_rows)
    ticker_counts = Counter(str(row.get("ticker") or "").strip().upper() for row in open_rows if str(row.get("ticker") or "").strip())
    direction_counts = Counter(str(row.get("direction") or "").strip().lower() for row in open_rows if str(row.get("direction") or "").strip())

    if not rows:
        return {
            "snapshot_available": False,
            "open_positions": _safe_int(exposure.get("open_positions")),
            "open_sell_recommendations": None,
            "open_recommendation_counts": {},
            "open_ticker_counts": dict(exposure.get("ticker_counts") or {}),
            "open_direction_counts": {},
        }

    return {
        "snapshot_available": True,
        "open_positions": len(open_rows),
        "open_sell_recommendations": int(recommendation_counts.get("SELL", 0)),
        "open_recommendation_counts": dict(sorted(recommendation_counts.items())),
        "open_ticker_counts": dict(sorted(ticker_counts.items())),
        "open_direction_counts": dict(sorted(direction_counts.items())),
    }


def _candidate_details_available(scan_snapshot: dict[str, Any]) -> bool:
    for key in ("candidate_audit_picks", "ranked_picks", "watch_picks", "blocked_picks", "raw_picks", "candidate_picks"):
        value = scan_snapshot.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _likely_guardrail_causes(
    *,
    playbook: dict[str, Any],
    exposure: dict[str, Any],
    tracked_summary: dict[str, Any],
) -> list[str]:
    causes: list[str] = []
    open_positions = _safe_int(exposure.get("open_positions"), _safe_int(tracked_summary.get("open_positions")))
    opened_today = _safe_int(exposure.get("opened_today"))
    max_concurrent = _safe_int(playbook.get("max_concurrent_positions"), 0)
    max_new = _safe_int(playbook.get("max_new_positions_per_day"), 0)
    if max_concurrent > 0 and open_positions >= max_concurrent:
        causes.append("max_concurrent_positions")
    if max_new > 0 and opened_today >= max_new:
        causes.append("daily_new_position_cap")

    account_size = _safe_float(playbook.get("account_size"), 10_000.0) or 10_000.0
    open_cost_risk = _safe_float(exposure.get("open_cost_risk_usd"), 0.0) or 0.0
    portfolio_cap_pct = _safe_float(playbook.get("max_portfolio_cost_risk_pct"), 0.0) or 0.0
    if portfolio_cap_pct > 0 and open_cost_risk >= account_size * portfolio_cap_pct / 100.0:
        causes.append("portfolio_cost_risk_cap")

    open_sell = tracked_summary.get("open_sell_recommendations")
    if isinstance(open_sell, int) and open_sell > 0:
        if open_sell >= max(open_positions, 1):
            causes.append("sell_recommendations_not_auto_closed")
        else:
            causes.append("open_sell_recommendations_not_auto_closed")
    if not causes and open_positions > 0:
        causes.append("open_position_exposure")
    return causes


def _session_row(row: sqlite3.Row, events: dict[str, Any]) -> dict[str, Any]:
    notes = _safe_json(row["notes_json"], {})
    scan_snapshot = events.get("scan_snapshot")
    if not isinstance(scan_snapshot, dict):
        scan_snapshot = {}
    tracked_positions = events.get("tracked_positions_snapshot")
    if not isinstance(tracked_positions, list):
        tracked_positions = []

    scan_funnel = scan_snapshot.get("scan_funnel") or notes.get("scan_funnel") or {}
    playbook = scan_snapshot.get("playbook") if isinstance(scan_snapshot.get("playbook"), dict) else {}
    if not playbook:
        playbook = notes.get("playbook") if isinstance(notes.get("playbook"), dict) else {}
    playbook_id = str(row["playbook"] or playbook.get("id") or "").strip()
    exposure = scan_snapshot.get("exposure_snapshot") if isinstance(scan_snapshot.get("exposure_snapshot"), dict) else {}
    if not exposure:
        exposure = notes.get("exposure_snapshot") if isinstance(notes.get("exposure_snapshot"), dict) else {}
    guardrail_counts = scan_snapshot.get("guardrail_decision_counts") or notes.get("guardrail_decision_counts") or {}
    policy_counts = scan_snapshot.get("policy_decision_counts") or notes.get("policy_decision_counts") or {}

    raw_candidates = _safe_int(
        scan_funnel.get("raw_candidates"),
        _safe_int(scan_snapshot.get("candidate_count"), _safe_int(notes.get("candidate_count"))),
    )
    returned_picks = _safe_int(
        scan_funnel.get("returned_picks"),
        _safe_int(scan_snapshot.get("returned_count"), _safe_int(row["scan_picks_count"])),
    )
    guardrail_blocked = _safe_int(
        (scan_funnel.get("guardrail_counts") or {}).get("blocked")
        if isinstance(scan_funnel.get("guardrail_counts"), dict)
        else None,
        _safe_int(guardrail_counts.get("blocked")),
    )
    policy_blocked = _safe_int(
        (scan_funnel.get("policy_counts") or {}).get("blocked")
        if isinstance(scan_funnel.get("policy_counts"), dict)
        else None,
        _safe_int(policy_counts.get("blocked")),
    )
    policy_watch = _safe_int(
        (scan_funnel.get("policy_counts") or {}).get("watch")
        if isinstance(scan_funnel.get("policy_counts"), dict)
        else None,
        _safe_int(policy_counts.get("watch")),
    )
    tracked_summary = _tracked_position_summary(tracked_positions, exposure)
    missed_candidate_appearances = guardrail_blocked if returned_picks == 0 else max(guardrail_blocked - returned_picks, 0)
    details_available = _candidate_details_available(scan_snapshot)
    likely_causes = _likely_guardrail_causes(
        playbook=playbook,
        exposure=exposure,
        tracked_summary=tracked_summary,
    )
    global_cap_sufficient = missed_candidate_appearances > 0 and "max_concurrent_positions" in likely_causes

    return {
        "session_id": int(row["id"]),
        "recorded_at_utc": row["recorded_at_utc"],
        "scan_date": _date_text(row["recorded_at_utc"]),
        "source_label": row["source_label"],
        "playbook": playbook_id,
        "run_id": row["run_id"],
        "evidence_class": row["evidence_class"],
        "eligibility_status": row["eligibility_status"],
        "raw_candidates": raw_candidates,
        "returned_picks": returned_picks,
        "guardrail_blocked_candidates": guardrail_blocked,
        "policy_blocked_candidates": policy_blocked,
        "policy_watch_candidates": policy_watch,
        "missed_candidate_appearances": missed_candidate_appearances,
        "policy_applied": bool(scan_snapshot.get("policy_applied") or notes.get("policy_applied")),
        "policy_error": scan_snapshot.get("policy_error") or notes.get("policy_error"),
        "scan_funnel": scan_funnel,
        "drop_counts": dict((scan_funnel or {}).get("drop_counts") or {}),
        "exposure_snapshot": exposure,
        "tracked_position_summary": tracked_summary,
        "candidate_details_available": details_available,
        "recoverability": (
            "candidate_details_persisted"
            if details_available
            else "counts_only_exact_candidate_identities_not_recoverable"
        ),
        "likely_guardrail_causes": likely_causes,
        "global_cap_sufficient_to_block": global_cap_sufficient,
    }


def load_audit_sessions(
    *,
    db_path: Path,
    date_from: date,
    date_to: date,
    source_label: str = "scheduled_scan",
) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Ledger DB not found: {db_path}")
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                id,
                recorded_at_utc,
                source_label,
                playbook,
                scan_picks_count,
                reviewed_positions_count,
                notes_json,
                run_id,
                run_mode,
                evidence_class,
                eligibility_status
            FROM forward_sessions
            WHERE source_label = ?
              AND recorded_at_utc >= ?
              AND recorded_at_utc < ?
            ORDER BY recorded_at_utc, id
            """,
            (source_label, date_from.isoformat(), _inclusive_end_utc(date_to)),
        ).fetchall()
        events_by_session = _read_session_events(conn, [int(row["id"]) for row in rows])
    return [_session_row(row, events_by_session.get(int(row["id"]), {})) for row in rows]


def _summarize_group(sessions: list[dict[str, Any]]) -> dict[str, Any]:
    recoverability_counts = Counter(str(session.get("recoverability") or "unknown") for session in sessions)
    cause_counts = Counter(
        cause
        for session in sessions
        if _safe_int(session.get("missed_candidate_appearances")) > 0
        for cause in list(session.get("likely_guardrail_causes") or [])
    )
    return {
        "sessions": len(sessions),
        "raw_candidates": sum(_safe_int(session.get("raw_candidates")) for session in sessions),
        "returned_picks": sum(_safe_int(session.get("returned_picks")) for session in sessions),
        "guardrail_blocked_candidates": sum(_safe_int(session.get("guardrail_blocked_candidates")) for session in sessions),
        "missed_candidate_appearances": sum(_safe_int(session.get("missed_candidate_appearances")) for session in sessions),
        "sessions_with_candidate_details": sum(1 for session in sessions if bool(session.get("candidate_details_available"))),
        "sessions_global_cap_sufficient_to_block": sum(1 for session in sessions if bool(session.get("global_cap_sufficient_to_block"))),
        "recoverability_counts": dict(sorted(recoverability_counts.items())),
        "likely_guardrail_cause_counts": dict(sorted(cause_counts.items())),
    }


def build_audit(
    *,
    db_path: Path,
    date_from: date,
    date_to: date,
    source_label: str = "scheduled_scan",
) -> dict[str, Any]:
    sessions = load_audit_sessions(
        db_path=db_path,
        date_from=date_from,
        date_to=date_to,
        source_label=source_label,
    )
    sessions_with_misses = [
        session for session in sessions
        if _safe_int(session.get("missed_candidate_appearances")) > 0
    ]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_playbook: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for session in sessions:
        by_date[str(session.get("scan_date") or "unknown")].append(session)
        by_playbook[str(session.get("playbook") or "unknown")].append(session)

    historical_options = _historical_options_coverage(date_from=date_from, date_to=date_to)
    exact_replay_available = bool(
        historical_options.get("covers_requested_window")
        and historical_options.get("underlyings_cover_live_universe")
    )
    return {
        "generated_at_utc": _utc_now_iso(),
        "ledger_db_path": str(db_path),
        "source_label": source_label,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "method": "ledger_funnel_audit",
        "summary": {
            **_summarize_group(sessions),
            "sessions_with_missed_candidates": len(sessions_with_misses),
            "exact_replay_available": exact_replay_available,
            "candidate_identity_recovery": (
                "available"
                if any(session.get("candidate_details_available") for session in sessions)
                else "not_available_counts_only"
            ),
        },
        "by_date": {
            key: _summarize_group(value)
            for key, value in sorted(by_date.items())
        },
        "by_playbook": {
            key: _summarize_group(value)
            for key, value in sorted(by_playbook.items())
        },
        "sessions": sessions,
        "historical_options_coverage": historical_options,
        "conclusions": _build_conclusions(sessions, historical_options),
    }


def _historical_options_coverage(*, date_from: date, date_to: date) -> dict[str, Any]:
    db_path = ROOT / "data" / "options-validation" / "options_history.db"
    if not db_path.exists():
        return {
            "db_path": str(db_path),
            "available": False,
            "covers_requested_window": False,
            "underlyings_cover_live_universe": False,
            "requested_date_from": date_from.isoformat(),
            "requested_date_to": date_to.isoformat(),
            "message": "Historical options DB is missing.",
        }
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                """
                SELECT
                    q.snapshot_kind,
                    COUNT(*) AS quote_rows,
                    COUNT(DISTINCT q.underlying) AS underlying_count,
                    GROUP_CONCAT(DISTINCT q.underlying) AS underlyings,
                    MIN(q.quote_date_et) AS first_quote_date,
                    MAX(q.quote_date_et) AS last_quote_date,
                    COUNT(DISTINCT q.quote_date_et) AS quote_date_count
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
                WHERE b.data_trust = 'trusted'
                GROUP BY q.snapshot_kind
                ORDER BY q.snapshot_kind
                """
            ).fetchall()
            coverage_rows = conn.execute(
                """
                SELECT
                    q.underlying,
                    COUNT(*) AS quote_rows,
                    MIN(q.quote_date_et) AS first_quote_date,
                    MAX(q.quote_date_et) AS last_quote_date,
                    COUNT(DISTINCT q.quote_date_et) AS quote_date_count
                FROM option_quote_snapshots q
                JOIN import_batches b ON b.id = q.source_batch_id
                WHERE b.data_trust = 'trusted'
                GROUP BY q.underlying
                ORDER BY q.underlying
                """
            ).fetchall()
        except sqlite3.OperationalError:
            rows = conn.execute(
                """
                SELECT
                    snapshot_kind,
                    COUNT(*) AS quote_rows,
                    COUNT(DISTINCT underlying) AS underlying_count,
                    GROUP_CONCAT(DISTINCT underlying) AS underlyings,
                    MIN(quote_date_et) AS first_quote_date,
                    MAX(quote_date_et) AS last_quote_date,
                    COUNT(DISTINCT quote_date_et) AS quote_date_count
                FROM option_quote_snapshots
                GROUP BY snapshot_kind
                ORDER BY snapshot_kind
                """
            ).fetchall()
            coverage_rows = conn.execute(
                """
                SELECT
                    underlying,
                    COUNT(*) AS quote_rows,
                    MIN(quote_date_et) AS first_quote_date,
                    MAX(quote_date_et) AS last_quote_date,
                    COUNT(DISTINCT quote_date_et) AS quote_date_count
                FROM option_quote_snapshots
                GROUP BY underlying
                ORDER BY underlying
                """
            ).fetchall()
    snapshots = [dict(row) for row in rows]
    coverage_by_underlying = {
        str(row["underlying"] or "").strip().upper(): {
            "quote_rows": _safe_int(row["quote_rows"]),
            "first_quote_date": row["first_quote_date"],
            "last_quote_date": row["last_quote_date"],
            "quote_date_count": _safe_int(row["quote_date_count"]),
            "covers_requested_window": bool(
                row["first_quote_date"]
                and row["last_quote_date"]
                and str(row["first_quote_date"]) <= date_from.isoformat()
                and str(row["last_quote_date"]) >= date_to.isoformat()
            ),
        }
        for row in coverage_rows
        if str(row["underlying"] or "").strip()
    }
    first_date = min((str(item.get("first_quote_date") or "") for item in snapshots if item.get("first_quote_date")), default="")
    latest_date = max((str(item.get("last_quote_date") or "") for item in snapshots), default="")
    underlyings = sorted({
        symbol.strip().upper()
        for item in snapshots
        for symbol in str(item.get("underlyings") or "").split(",")
        if symbol.strip()
    })
    live_needed = {"SPY", "QQQ", "IWM", "DIA", "XLK", "GOOGL", "NVDA", "AMZN", "JPM"}
    per_underlying_window_covered = all(
        bool((coverage_by_underlying.get(symbol) or {}).get("covers_requested_window"))
        for symbol in live_needed
    )
    return {
        "db_path": str(db_path),
        "available": True,
        "snapshots": snapshots,
        "requested_date_from": date_from.isoformat(),
        "requested_date_to": date_to.isoformat(),
        "first_quote_date": first_date or None,
        "latest_quote_date": latest_date or None,
        "available_underlyings": underlyings,
        "covers_requested_window": bool(
            first_date
            and latest_date
            and first_date <= date_from.isoformat()
            and latest_date >= date_to.isoformat()
            and per_underlying_window_covered
        ),
        "underlyings_cover_live_universe": live_needed.issubset(set(underlyings)),
        "missing_live_underlyings": sorted(live_needed - set(underlyings)),
        "live_universe_coverage_by_underlying": {
            symbol: coverage_by_underlying.get(symbol, {"missing": True, "covers_requested_window": False})
            for symbol in sorted(live_needed)
        },
    }


def _build_conclusions(
    sessions: list[dict[str, Any]],
    historical_options: dict[str, Any],
) -> list[str]:
    summary = _summarize_group(sessions)
    conclusions: list[str] = []
    if summary["missed_candidate_appearances"] > 0:
        conclusions.append(
            (
                f"Scheduled scans saw {summary['raw_candidates']} raw candidate appearances "
                f"and guardrails blocked {summary['guardrail_blocked_candidates']} of them."
            )
        )
    if summary["sessions_global_cap_sufficient_to_block"] > 0:
        conclusions.append(
            (
                f"Max-concurrent/open-exposure caps were sufficient to block candidates in "
                f"{summary['sessions_global_cap_sufficient_to_block']} session(s)."
            )
        )
    cause_counts = summary.get("likely_guardrail_cause_counts") or {}
    if cause_counts.get("sell_recommendations_not_auto_closed") or cause_counts.get("open_sell_recommendations_not_auto_closed"):
        conclusions.append("Open SELL recommendations were present and not auto-closed during the missed window.")
    if summary["sessions_with_candidate_details"] == 0 and sessions:
        conclusions.append("The ledger persisted funnel counts, not blocked candidate identities, so exact missed contracts cannot be recovered from the ledger.")
    if not historical_options.get("covers_requested_window"):
        conclusions.append(
            (
                "Trusted historical options quotes do not cover the requested "
                f"{historical_options.get('requested_date_from')} to {historical_options.get('requested_date_to')} window, "
                "so exact option-chain replay is unavailable locally."
            )
        )
    return conclusions


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(item) for item in row) + " |")
    return "\n".join(out)


def render_markdown(audit: dict[str, Any]) -> str:
    summary = audit["summary"]
    lines = [
        "# Missed Guardrail Trade Audit",
        "",
        f"Generated: `{audit['generated_at_utc']}`",
        f"Window: `{audit['date_from']}` to `{audit['date_to']}`",
        f"Ledger: `{audit['ledger_db_path']}`",
        "",
        "## Summary",
        "",
        _markdown_table(
            ["Metric", "Value"],
            [
                ["Sessions audited", summary["sessions"]],
                ["Raw candidate appearances", summary["raw_candidates"]],
                ["Guardrail-blocked appearances", summary["guardrail_blocked_candidates"]],
                ["Returned/tracked picks", summary["returned_picks"]],
                ["Missed candidate appearances", summary["missed_candidate_appearances"]],
                ["Sessions with recoverable candidate details", summary["sessions_with_candidate_details"]],
                ["Candidate identity recovery", summary["candidate_identity_recovery"]],
                ["Exact replay available locally", summary["exact_replay_available"]],
            ],
        ),
        "",
        "## By Date",
        "",
        _markdown_table(
            ["Date", "Sessions", "Raw", "Blocked", "Returned", "Missed"],
            [
                [
                    date_key,
                    item["sessions"],
                    item["raw_candidates"],
                    item["guardrail_blocked_candidates"],
                    item["returned_picks"],
                    item["missed_candidate_appearances"],
                ]
                for date_key, item in audit["by_date"].items()
            ],
        ),
        "",
        "## By Playbook",
        "",
        _markdown_table(
            ["Playbook", "Sessions", "Raw", "Blocked", "Returned", "Missed", "Main Causes"],
            [
                [
                    playbook,
                    item["sessions"],
                    item["raw_candidates"],
                    item["guardrail_blocked_candidates"],
                    item["returned_picks"],
                    item["missed_candidate_appearances"],
                    ", ".join(item["likely_guardrail_cause_counts"].keys()) or "unknown",
                ]
                for playbook, item in audit["by_playbook"].items()
            ],
        ),
        "",
        "## Conclusions",
        "",
    ]
    lines.extend(f"- {item}" for item in audit.get("conclusions") or [])
    lines.extend(
        [
            "",
            "## Recovery Limits",
            "",
            "- These rows are missed candidate appearances, not proven unique tradable fills.",
            "- The historical ledger did not persist blocked candidate details in this window.",
            "- Reconstructed candidates must be labeled `research_backfill` or `missed_due_to_guardrails`, not live production proof.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_audit(audit: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"missed_guardrail_trades_{audit['date_from']}_{audit['date_to']}_{stamp}.json"
    md_path = output_dir / f"missed_guardrail_trades_{audit['date_from']}_{audit['date_to']}_{stamp}.md"
    json_path.write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf8")
    md_path.write_text(render_markdown(audit), encoding="utf8")
    (output_dir / "latest.json").write_text(json.dumps(audit, indent=2, sort_keys=True), encoding="utf8")
    (output_dir / "latest.md").write_text(render_markdown(audit), encoding="utf8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit scheduled scans that were reduced to zero by guardrails.")
    parser.add_argument("--date-from", default="2026-04-24")
    parser.add_argument("--date-to", default="2026-05-08")
    parser.add_argument("--source-label", default="scheduled_scan")
    parser.add_argument("--ledger-db", default=str(DEFAULT_LEDGER_DB))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--no-write", action="store_true", help="Print summary without writing report files.")
    args = parser.parse_args(argv)

    date_from = date.fromisoformat(str(args.date_from))
    date_to = date.fromisoformat(str(args.date_to))
    audit = build_audit(
        db_path=Path(args.ledger_db),
        date_from=date_from,
        date_to=date_to,
        source_label=str(args.source_label),
    )

    if not args.no_write:
        json_path, md_path = write_audit(audit, Path(args.output_dir))
        print(f"Wrote JSON report: {json_path}")
        print(f"Wrote Markdown report: {md_path}")

    summary = audit["summary"]
    print(
        "Missed guardrail audit: "
        f"sessions={summary['sessions']} "
        f"raw_candidates={summary['raw_candidates']} "
        f"blocked={summary['guardrail_blocked_candidates']} "
        f"returned={summary['returned_picks']} "
        f"candidate_identity_recovery={summary['candidate_identity_recovery']}"
    )
    for conclusion in audit.get("conclusions") or []:
        print(f"- {conclusion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
