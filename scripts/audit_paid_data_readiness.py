from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import (  # noqa: E402
    DAILY_SNAPSHOT_KIND,
    HistoricalOptionsStore,
    TRUSTED_DATA_TRUST,
    load_import_batches,
)


DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "paid-data-readiness"
DEFAULT_REQUIRED_UNDERLYINGS = ("SPY", "QQQ", "DIA", "XLK", "GOOGL", "NVDA")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_symbols(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return list(DEFAULT_REQUIRED_UNDERLYINGS)
    if isinstance(value, str):
        pieces = value.replace(";", ",").split(",")
    else:
        pieces = list(value)
    symbols = sorted({str(item).strip().upper() for item in pieces if str(item).strip()})
    return symbols or list(DEFAULT_REQUIRED_UNDERLYINGS)


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator) * 100.0, 2) if denominator else 0.0


def _parse_source_labels(value: str | Sequence[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        pieces = value.replace(";", ",").split(",")
    else:
        pieces = list(value)
    return sorted({str(item).strip() for item in pieces if str(item).strip()})


def _readiness_scope_from_playbook(playbook_id: str | None) -> dict[str, Any]:
    raw = str(playbook_id or "").strip().lower()
    if not raw:
        return {}
    from wfo_optimizer import (  # noqa: WPS433 - lazy import keeps the CLI light unless requested.
        REPLAY_PLAYBOOKS,
        _get_replay_playbook,
        _imported_replay_underlyings_for_playbook,
    )

    if raw not in REPLAY_PLAYBOOKS:
        raise ValueError(f"Unknown replay playbook: {playbook_id}")
    playbook = _get_replay_playbook(raw)
    return {
        "id": playbook.get("id") or raw,
        "label": playbook.get("label") or raw,
        "required_underlyings": list(_imported_replay_underlyings_for_playbook(playbook)),
        "source_labels": _parse_source_labels(playbook.get("historical_source_labels") or []),
    }


def _sqlite_readonly(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _source_label_clause(source_labels: Sequence[str], alias: str = "b") -> tuple[str, list[Any]]:
    labels = _parse_source_labels(source_labels)
    if not labels:
        return "", []
    placeholders = ", ".join("?" for _ in labels)
    return f"AND {alias}.source_label IN ({placeholders})", list(labels)


def _underlying_clause(underlyings: Sequence[str] | str | None, alias: str = "q") -> tuple[str, list[Any]]:
    if underlyings is None:
        return "", []
    symbols = _parse_symbols(underlyings)
    if not symbols:
        return "", []
    placeholders = ", ".join("?" for _ in symbols)
    return f"AND {alias}.underlying IN ({placeholders})", list(symbols)


def _source_filtered_snapshot_summary(
    db_path: Path,
    *,
    snapshot_kind: str,
    trusted_only: bool = True,
    source_labels: Sequence[str] = (),
    underlyings: Sequence[str] | str | None = None,
) -> dict[str, Any]:
    if not db_path.exists():
        return {
            "db_path": str(db_path),
            "snapshot_kind": snapshot_kind,
            "quote_count": 0,
            "batch_count": 0,
            "earliest_quote_at_utc": None,
            "latest_quote_at_utc": None,
            "latest_imported_at_utc": None,
            "available_underlyings": [],
            "source_labels": _parse_source_labels(source_labels),
            "dataset_kinds": [],
            "trust_levels": [TRUSTED_DATA_TRUST] if trusted_only else [],
            "trusted_only": trusted_only,
        }
    with _sqlite_readonly(db_path) as conn:
        params: list[Any] = [snapshot_kind]
        trust_clause = ""
        if trusted_only:
            trust_clause = "AND b.data_trust = ?"
            params.append(TRUSTED_DATA_TRUST)
        source_clause, source_params = _source_label_clause(source_labels)
        params.extend(source_params)
        underlying_clause, underlying_params = _underlying_clause(underlyings)
        params.extend(underlying_params)
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS quote_count,
                COUNT(DISTINCT b.id) AS batch_count,
                MIN(q.as_of_utc) AS earliest_quote_at_utc,
                MAX(q.as_of_utc) AS latest_quote_at_utc,
                MAX(b.imported_at_utc) AS latest_imported_at_utc,
                GROUP_CONCAT(DISTINCT q.underlying) AS available_underlyings,
                GROUP_CONCAT(DISTINCT b.source_label) AS source_labels,
                GROUP_CONCAT(DISTINCT b.dataset_kind) AS dataset_kinds,
                GROUP_CONCAT(DISTINCT b.data_trust) AS trust_levels
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE q.snapshot_kind = ?
              {trust_clause}
              {source_clause}
              {underlying_clause}
            """,
            tuple(params),
        ).fetchone()

    available = sorted(
        str(item).upper()
        for item in str((row["available_underlyings"] if row else "") or "").split(",")
        if item
    )
    return {
        "db_path": str(db_path),
        "snapshot_kind": snapshot_kind,
        "quote_count": int((row["quote_count"] if row else 0) or 0),
        "batch_count": int((row["batch_count"] if row else 0) or 0),
        "earliest_quote_at_utc": str((row["earliest_quote_at_utc"] if row else None) or "") or None,
        "latest_quote_at_utc": str((row["latest_quote_at_utc"] if row else None) or "") or None,
        "latest_imported_at_utc": str((row["latest_imported_at_utc"] if row else None) or "") or None,
        "available_underlyings": available,
        "source_labels": [
            item for item in str((row["source_labels"] if row else "") or "").split(",") if item
        ],
        "dataset_kinds": [
            item for item in str((row["dataset_kinds"] if row else "") or "").split(",") if item
        ],
        "trust_levels": [
            item for item in str((row["trust_levels"] if row else "") or "").split(",") if item
        ],
        "trusted_only": trusted_only,
    }


def _query_underlying_health(
    db_path: Path,
    *,
    snapshot_kind: str,
    trusted_only: bool = True,
    source_labels: Sequence[str] = (),
    underlyings: Sequence[str] | str | None = None,
) -> dict[str, dict[str, Any]]:
    if not db_path.exists():
        return {}
    with _sqlite_readonly(db_path) as conn:
        params: list[Any] = [snapshot_kind]
        trust_clause = ""
        if trusted_only:
            trust_clause = "AND b.data_trust = ?"
            params.append(TRUSTED_DATA_TRUST)
        source_clause, source_params = _source_label_clause(source_labels)
        params.extend(source_params)
        underlying_clause, underlying_params = _underlying_clause(underlyings)
        params.extend(underlying_params)
        rows = conn.execute(
            f"""
            SELECT
                q.underlying,
                COUNT(*) AS quote_rows,
                COUNT(DISTINCT q.contract_symbol) AS contract_count,
                COUNT(DISTINCT q.quote_date_et) AS quote_date_count,
                MIN(q.quote_date_et) AS first_quote_date,
                MAX(q.quote_date_et) AS last_quote_date,
                SUM(CASE WHEN q.bid IS NOT NULL AND q.ask IS NOT NULL AND q.bid > 0 AND q.ask >= q.bid AND q.ask > 0 THEN 1 ELSE 0 END)
                    AS executable_quote_rows,
                SUM(CASE WHEN q.bid IS NOT NULL AND q.ask IS NOT NULL AND q.ask < q.bid THEN 1 ELSE 0 END)
                    AS crossed_quote_rows,
                SUM(CASE WHEN q.bid IS NULL OR q.ask IS NULL THEN 1 ELSE 0 END)
                    AS missing_bid_ask_rows,
                SUM(CASE WHEN q.underlying_price IS NOT NULL THEN 1 ELSE 0 END)
                    AS rows_with_underlying_price
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE q.snapshot_kind = ?
              {trust_clause}
              {source_clause}
              {underlying_clause}
            GROUP BY q.underlying
            ORDER BY q.underlying
            """,
            tuple(params),
        ).fetchall()

    health: dict[str, dict[str, Any]] = {}
    for row in rows:
        quote_rows = int(row["quote_rows"] or 0)
        executable_rows = int(row["executable_quote_rows"] or 0)
        underlying_price_rows = int(row["rows_with_underlying_price"] or 0)
        symbol = str(row["underlying"]).upper()
        health[symbol] = {
            "quote_rows": quote_rows,
            "contract_count": int(row["contract_count"] or 0),
            "quote_date_count": int(row["quote_date_count"] or 0),
            "first_quote_date": row["first_quote_date"],
            "last_quote_date": row["last_quote_date"],
            "executable_quote_rows": executable_rows,
            "executable_quote_pct": _pct(executable_rows, quote_rows),
            "crossed_quote_rows": int(row["crossed_quote_rows"] or 0),
            "missing_bid_ask_rows": int(row["missing_bid_ask_rows"] or 0),
            "rows_with_underlying_price": underlying_price_rows,
            "underlying_price_pct": _pct(underlying_price_rows, quote_rows),
        }
    return health


def _latest_trusted_batches(
    db_path: Path,
    *,
    limit: int = 8,
    source_labels: Sequence[str] = (),
    trusted_only: bool = True,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    labels = set(_parse_source_labels(source_labels))
    batches = [
        batch
        for batch in load_import_batches(db_path)
        if (not trusted_only or str(batch.get("data_trust") or "").lower() == TRUSTED_DATA_TRUST)
        and (not labels or str(batch.get("source_label") or "") in labels)
    ]
    output: list[dict[str, Any]] = []
    for batch in batches[:limit]:
        output.append(
            {
                "id": batch.get("id"),
                "source_label": batch.get("source_label"),
                "dataset_kind": batch.get("dataset_kind"),
                "imported_rows": batch.get("imported_rows"),
                "duplicate_rows": batch.get("duplicate_rows"),
                "rejected_rows": batch.get("rejected_rows"),
                "imported_at_utc": batch.get("imported_at_utc"),
                "date_from": batch.get("date_from"),
                "date_to": batch.get("date_to"),
                "warnings": list(batch.get("warnings") or [])[:3],
            }
        )
    return output


def _fingerprint_payload(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "paid_options_data_readiness",
        "db_path": audit.get("db_path"),
        "snapshot_kind": audit.get("snapshot_kind"),
        "source_labels_required": audit.get("source_labels_required"),
        "required_underlyings": audit.get("required_underlyings"),
        "minimums": audit.get("minimums"),
        "summary": audit.get("summary"),
        "required_underlying_health": audit.get("required_underlying_health"),
    }


def build_paid_data_readiness_fingerprint(audit: dict[str, Any]) -> str:
    encoded = json.dumps(_fingerprint_payload(audit), sort_keys=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def _build_next_actions(
    *,
    missing_required: list[str],
    thin_required: list[str],
    low_executable_required: list[str],
    shared_quote_date_count: int,
    min_shared_quote_dates: int,
    snapshot_kind: str,
    trusted_only: bool = True,
) -> list[str]:
    actions: list[str] = []
    data_scope = "trusted option history" if trusted_only else "option history"
    if missing_required:
        actions.append(
            f"Import {data_scope} for missing required symbols: " + ", ".join(missing_required) + "."
        )
    if thin_required:
        actions.append(
            "Add more quote dates for thin symbols before using them in profitability claims: "
            + ", ".join(thin_required)
            + "."
        )
    if low_executable_required:
        actions.append(
            "Check bid/ask columns for low-executable symbols; spread backtests need real bid and ask: "
            + ", ".join(low_executable_required)
            + "."
        )
    if shared_quote_date_count < min_shared_quote_dates:
        actions.append(
            f"Extend the overlapping {snapshot_kind} window across required symbols; current shared dates "
            f"{shared_quote_date_count} < target {min_shared_quote_dates}."
        )
    if not actions:
        actions.append("Run exact-contract replay/backtest on the requested playbook and canary proof/control yardstick.")
    return actions


def build_paid_data_readiness_audit(
    *,
    db_path: str | Path | None = None,
    required_underlyings: Sequence[str] | str | None = None,
    snapshot_kind: str = DAILY_SNAPSHOT_KIND,
    min_quote_dates: int = 252,
    min_shared_quote_dates: int = 120,
    min_executable_quote_pct: float = 90.0,
    source_labels: Sequence[str] | str | None = None,
    playbook: str | None = None,
    trusted_only: bool = True,
) -> dict[str, Any]:
    store = HistoricalOptionsStore(db_path)
    playbook_scope = _readiness_scope_from_playbook(playbook)
    required = _parse_symbols(
        required_underlyings
        if required_underlyings is not None
        else playbook_scope.get("required_underlyings")
    )
    required_source_labels = _parse_source_labels(
        source_labels if source_labels is not None else playbook_scope.get("source_labels")
    )
    db = store.db_path
    summary = (
        _source_filtered_snapshot_summary(
            db,
            snapshot_kind=snapshot_kind,
            trusted_only=trusted_only,
            source_labels=required_source_labels,
            underlyings=required,
        )
        if required_source_labels
        else store.snapshot_summary(snapshot_kind, trusted_only=trusted_only)
    )
    available = [str(item).upper() for item in summary.get("available_underlyings") or []]
    missing_required = [symbol for symbol in required if symbol not in available]
    health = _query_underlying_health(
        db,
        snapshot_kind=snapshot_kind,
        trusted_only=trusted_only,
        source_labels=required_source_labels,
        underlyings=required,
    )
    required_health = {symbol: health.get(symbol, {"missing": True}) for symbol in required}
    present_required = [symbol for symbol in required if symbol in health]
    shared_dates = (
        store.shared_quote_dates(
            present_required,
            snapshot_kind=snapshot_kind,
            trusted_only=trusted_only,
            source_labels=required_source_labels,
        )
        if present_required
        else []
    )

    thin_required = [
        symbol
        for symbol, item in required_health.items()
        if not item.get("missing") and int(item.get("quote_date_count") or 0) < int(min_quote_dates)
    ]
    low_executable_required = [
        symbol
        for symbol, item in required_health.items()
        if not item.get("missing") and float(item.get("executable_quote_pct") or 0.0) < float(min_executable_quote_pct)
    ]

    if not int(summary.get("quote_count") or 0):
        status = "not_ready"
        blocker = "no_trusted_quotes" if trusted_only else "no_quotes"
    elif missing_required:
        status = "not_ready"
        blocker = "missing_required_underlyings"
    elif low_executable_required:
        status = "not_ready"
        blocker = "low_executable_quote_coverage"
    elif thin_required or len(shared_dates) < int(min_shared_quote_dates):
        status = "partial"
        blocker = "thin_required_history"
    else:
        status = "ready_for_exact_replay"
        blocker = None

    audit = {
        "generated_at": _utc_now_iso(),
        "db_path": str(db),
        "snapshot_kind": snapshot_kind,
        "source_labels_required": required_source_labels,
        "playbook": (
            {
                "id": playbook_scope.get("id"),
                "label": playbook_scope.get("label"),
            }
            if playbook_scope
            else None
        ),
        "status": status,
        "blocker": blocker,
        "required_underlyings": required,
        "minimums": {
            "min_quote_dates_per_required_underlying": int(min_quote_dates),
            "min_shared_quote_dates": int(min_shared_quote_dates),
            "min_executable_quote_pct": float(min_executable_quote_pct),
            "trusted_only": bool(trusted_only),
        },
        "summary": summary,
        "available_underlyings": available,
        "missing_required_underlyings": missing_required,
        "thin_required_underlyings": thin_required,
        "low_executable_required_underlyings": low_executable_required,
        "shared_required_quote_dates": {
            "count": len(shared_dates),
            "first": shared_dates[0] if shared_dates else None,
            "last": shared_dates[-1] if shared_dates else None,
        },
        "required_underlying_health": required_health,
        "latest_trusted_import_batches": _latest_trusted_batches(
            db,
            source_labels=required_source_labels,
            trusted_only=True,
        ),
        "latest_import_batches": _latest_trusted_batches(
            db,
            source_labels=required_source_labels,
            trusted_only=trusted_only,
        ),
        "next_actions": _build_next_actions(
            missing_required=missing_required,
            thin_required=thin_required,
            low_executable_required=low_executable_required,
            shared_quote_date_count=len(shared_dates),
            min_shared_quote_dates=int(min_shared_quote_dates),
            snapshot_kind=snapshot_kind,
            trusted_only=trusted_only,
        ),
    }
    audit["readiness_fingerprint"] = build_paid_data_readiness_fingerprint(audit)
    return audit


def find_duplicate_paid_data_readiness(output_dir: Path, fingerprint: str) -> Path | None:
    for path in sorted(output_dir.glob("paid_data_readiness_*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("readiness_fingerprint") == fingerprint:
            return path
    return None


def write_paid_data_readiness_audit(
    audit: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    force: bool = False,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    duplicate = find_duplicate_paid_data_readiness(output_dir, str(audit.get("readiness_fingerprint") or ""))
    if duplicate is not None and not force:
        return {
            "status": "duplicate_skipped",
            "duplicate_of": str(duplicate),
            "latest": str(output_dir / "latest.json"),
            "audit": audit,
        }
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = output_dir / f"paid_data_readiness_{stamp}.json"
    latest_path = output_dir / "latest.json"
    serialized = json.dumps(audit, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    return {"status": "written", "output": str(output_path), "latest": str(latest_path), "audit": audit}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit whether paid historical options data is ready for exact replay.")
    parser.add_argument("--db-path", help="Optional SQLite path for the historical options store.")
    parser.add_argument("--snapshot-kind", default=DAILY_SNAPSHOT_KIND)
    parser.add_argument(
        "--required-underlyings",
        default=None,
        help="Comma-separated symbols that must be present before we trust the profitability lab.",
    )
    parser.add_argument("--playbook", help="Optional replay playbook whose imported-data scope should be audited.")
    parser.add_argument("--min-quote-dates", type=int, default=252)
    parser.add_argument("--min-shared-quote-dates", type=int, default=120)
    parser.add_argument("--min-executable-quote-pct", type=float, default=90.0)
    parser.add_argument("--source-labels", help="Optional comma-separated trusted import source labels to require.")
    parser.add_argument(
        "--include-research",
        action="store_true",
        help="Include research-grade imports in this audit. Does not make them proof-grade or trusted.",
    )
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    audit = build_paid_data_readiness_audit(
        db_path=args.db_path,
        required_underlyings=args.required_underlyings,
        snapshot_kind=args.snapshot_kind,
        min_quote_dates=args.min_quote_dates,
        min_shared_quote_dates=args.min_shared_quote_dates,
        min_executable_quote_pct=args.min_executable_quote_pct,
        source_labels=args.source_labels,
        playbook=args.playbook,
        trusted_only=not bool(args.include_research),
    )
    written = write_paid_data_readiness_audit(
        audit,
        output_dir=Path(args.output_dir),
        force=bool(args.force),
    )
    compact = {
        "write_status": written["status"],
        "output": written.get("output"),
        "latest": written.get("latest"),
        "status": audit["status"],
        "blocker": audit["blocker"],
        "snapshot_kind": audit["snapshot_kind"],
        "source_labels_required": audit["source_labels_required"],
        "playbook": audit["playbook"],
        "required_underlyings": audit["required_underlyings"],
        "missing_required_underlyings": audit["missing_required_underlyings"],
        "thin_required_underlyings": audit["thin_required_underlyings"],
        "low_executable_required_underlyings": audit["low_executable_required_underlyings"],
        "shared_required_quote_dates": audit["shared_required_quote_dates"],
        "next_actions": audit["next_actions"],
    }
    print(json.dumps(audit if args.json else compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
