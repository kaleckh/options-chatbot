"""Research-only VRP put-credit-spread replay for the 2018-2021 fresh window.

Implements data/contracts/regular-options-vrp-credit-spread-fresh-window-contract-v1.json:
defined-risk put credit spreads on SPY/QQQ/IWM/DIA, entries and daily exit
monitoring on the 15:55:00 ET trusted OPRA/NBBO surface, side-aware pricing,
fail-closed denominators, cluster-bootstrap metrics.

Frozen implementation choices (recorded here per the contract's
design-decision clause; none may change after first scoring):
- Underlying spot proxy at 15:55 comes from put-call parity on a synchronized
  quote minute at the chosen expiry: spot ~= strike + call_mid - put_mid at
  the strike minimizing |call_mid - put_mid| (no external 15:55 equity print
  exists in the research stores).
- Short-put selection uses the playbook's OTM fallback (no deltas in NBBO
  store): strikes within [0.93, 0.97] x spot, preferring the strike closest
  to 0.95 x spot.
- net_pnl_pct denominator is max_loss_usd (defined-risk capital at risk), and
  both USD and percentage metrics are net of the frozen round-trip fees.
- The contract's crash guard requires an explicit point-in-time boolean from
  a market-regime input row. VIX is not treated as a substitute; absent,
  ambiguous, reconstructed, or late crash inputs fail closed.
- One open position per underlying; entries blocked while open.

This script never touches scanner policy, proof bars, live validation,
auto-track, broker paths, protected holdout, or promotion.
"""

from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Sequence
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_historical_profitability_filter_iteration import (  # noqa: E402
    _metrics,
)
from us_equity_market_calendar import is_us_equity_market_day  # noqa: E402

REPORT_ID = "regular_options_vrp_credit_spread_replay"
CONTRACT = (
    ROOT
    / "data"
    / "contracts"
    / "regular-options-vrp-credit-spread-fresh-window-contract-v1.json"
)
WINDOW_CONTRACT = (
    ROOT
    / "data"
    / "contracts"
    / "regular-options-filter-family-fresh-window-contract-v1.json"
)
DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_IMPORT_MANIFEST = (
    ROOT / "data" / "options-validation" / "fresh_window_2018_2021_import_manifest.json"
)
FF = ROOT / "data" / "profitability-lab" / "regular-options-filter-family-fresh-window"
DEFAULT_CRASH_GUARD = FF / "point-in-time-market-regime-inputs" / "latest.json"
VIX_POLICY_CONTRACT = (
    ROOT / "data" / "contracts" / "regular-options-vix-bucket-policy.json"
)
UNIVERSE = ("SPY", "QQQ", "IWM", "DIA")
EXIT_MINUTE = 15 * 60 + 55
FEE_PER_LEG = 0.65
ROUND_TRIP_LEGS = 4
FROZEN_BOOTSTRAP_DRAWS = 10_000
TRUSTED_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
QUOTE_CORPUS_BINDING_VERSION = "fresh_window_quote_corpus_v1"
EASTERN = ZoneInfo("America/New_York")
CONSUMED_WINDOWS = (
    ("2022-01", "2024-05"),
    ("2024-06", "2026-01"),
    ("2026-02", "2026-05"),
)
MISSING_FORMAL_VALIDATION_PATH = "missing_formal_family_validation_evaluation_path"

FALSE_FLAGS = {
    "read_only_research_harness": True,
    "research_only_not_forward_proof": True,
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "scanner_policy_changed": False,
    "proof_bars_changed": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "promotion_ready": False,
    "protected_holdout_consumed": False,
    "consumption_registry_appended": False,
}


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _load_row_file(
    path: Path, *, container_keys: Sequence[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "status": "missing",
        "row_count": 0,
    }
    if not path.exists():
        return [], meta
    try:
        if path.suffix.lower() == ".jsonl":
            rows = []
            for raw in path.read_text(encoding="utf8").splitlines():
                if not raw.strip():
                    continue
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError("row file contained a non-object line")
                rows.append(value)
        else:
            payload = json.loads(path.read_text(encoding="utf8"))
            if isinstance(payload, list):
                rows = [row for row in payload if isinstance(row, dict)]
                if len(rows) != len(payload):
                    raise ValueError("row file contained a non-object item")
            elif isinstance(payload, dict):
                rows = []
                for key in container_keys:
                    if isinstance(payload.get(key), list):
                        values = payload[key]
                        rows = [row for row in values if isinstance(row, dict)]
                        if len(rows) != len(values):
                            raise ValueError(f"{key} contained a non-object item")
                        break
            else:
                raise ValueError("row file did not contain an object or array")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        meta.update({"status": "invalid", "error": type(exc).__name__})
        return [], meta
    meta.update({"status": "loaded", "row_count": len(rows)})
    return rows, meta


def _index_rows(
    rows: Sequence[dict[str, Any]], *, date_field: str
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    indexed: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for row in rows:
        day = str(row.get(date_field) or "")
        try:
            date.fromisoformat(day)
        except ValueError:
            continue
        if day in indexed:
            duplicates.add(day)
        else:
            indexed[day] = row
    for day in duplicates:
        indexed.pop(day, None)
    return indexed, duplicates


def _month(day: str) -> str:
    return day[:7]


def _month_end(month: str) -> str:
    year, month_number = (int(part) for part in month.split("-"))
    return date(
        year, month_number, calendar.monthrange(year, month_number)[1]
    ).isoformat()


def _frozen_train_window() -> tuple[str, str]:
    train_rule = _load_json(WINDOW_CONTRACT)["split_rule"]["family_train"]
    return (
        f"{train_rule['start_month']}-01",
        _month_end(str(train_rule["end_month"])),
    )


def _expected_us_equity_market_dates(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    final = date.fromisoformat(end)
    dates: list[str] = []
    while current <= final:
        if is_us_equity_market_day(current):
            dates.append(current.isoformat())
        current += timedelta(days=1)
    return dates


def _overlaps_consumed(start_month: str, end_month: str) -> bool:
    return any(
        start_month <= c_end and end_month >= c_start
        for c_start, c_end in CONSUMED_WINDOWS
    )


def _parse_utc(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _event_timestamp_utc(day: str, minute_et: int = EXIT_MINUTE) -> datetime:
    parsed = date.fromisoformat(day)
    hour, minute = divmod(minute_et, 60)
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError(f"invalid ET minute-of-day: {minute_et}")
    return datetime(
        parsed.year, parsed.month, parsed.day, hour, minute, tzinfo=EASTERN
    ).astimezone(UTC)


def _entry_timestamp_utc(day: str) -> datetime:
    return _event_timestamp_utc(day)


def _point_in_time_vix(
    row: dict[str, Any] | None, day: str
) -> tuple[float | None, str]:
    if row is None:
        return None, "missing_point_in_time_vix_row"
    if row.get("point_in_time_valid") is not True:
        return None, "invalid_point_in_time_vix_row"
    if row.get("source_provenance_status") != "trusted_local_or_contract_declared":
        return None, "untrusted_point_in_time_vix_row"
    known_at = _parse_utc(row.get("known_at_utc"))
    if known_at is None or known_at > _entry_timestamp_utc(day):
        return None, "late_or_missing_point_in_time_vix_known_at"
    try:
        value = float(row["vix_value"])
    except (KeyError, TypeError, ValueError):
        return None, "invalid_point_in_time_vix_value"
    if not math.isfinite(value) or value < 0:
        return None, "invalid_point_in_time_vix_value"
    return value, "point_in_time_vix_ready"


def _point_in_time_crash_guard(
    row: dict[str, Any] | None, day: str
) -> tuple[bool | None, str]:
    if row is None:
        return None, "missing_point_in_time_crash_guard"
    if (
        row.get("point_in_time_valid") is not True
        or row.get("proof_eligible") is not True
    ):
        return None, "invalid_point_in_time_crash_guard"
    if row.get("historical_prior_bar_reconstruction") is True or row.get("blockers"):
        return None, "invalid_point_in_time_crash_guard"
    if not isinstance(row.get("crash_regime"), bool):
        return None, "missing_explicit_point_in_time_crash_flag"
    known_at = _parse_utc(row.get("known_at_utc"))
    if known_at is None or known_at > _entry_timestamp_utc(day):
        return None, "late_or_missing_point_in_time_crash_known_at"
    return bool(row["crash_regime"]), "point_in_time_crash_guard_ready"


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text.lower()
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_source_batch_ids(manifest: dict[str, Any]) -> tuple[int, ...]:
    batch_ids: set[int] = set()

    def visit(value: Any, key: str | None = None) -> None:
        if key == "batch_id" and not isinstance(value, bool):
            try:
                batch_id = int(value)
            except (TypeError, ValueError):
                return
            if batch_id > 0 and str(batch_id) == str(value):
                batch_ids.add(batch_id)
            return
        if key == "import_batch_ids" and isinstance(value, list):
            for item in value:
                visit(item, "batch_id")
            return
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, str(child_key))
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(manifest.get("chunks") or {})
    return tuple(sorted(batch_ids))


def _verified_quote_corpus_from_manifest(
    manifest_path: Path | None, db_path: Path
) -> tuple[tuple[int, ...], dict[str, Any], list[str]]:
    if manifest_path is None or not manifest_path.is_file():
        return (
            (),
            {"status": "missing", "path": str(manifest_path or "")},
            ["missing_manifest_bound_quote_corpus"],
        )
    try:
        manifest = _load_json(manifest_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return (
            (),
            {"status": "invalid", "path": str(manifest_path)},
            [f"invalid_quote_import_manifest:{type(exc).__name__}"],
        )

    from scripts import run_fresh_window_2018_2021_quote_imports as fresh_import

    chain_errors = fresh_import.chain_completeness_standard_errors(manifest)
    corpus = manifest.get("downstream_corpus_binding")
    corpus_errors: list[str] = []
    if not isinstance(corpus, dict):
        corpus_errors.append("downstream_corpus_binding_missing")
        corpus = {}
    elif (
        corpus.get("standard_version") != "fresh_window_manifest_database_corpus_v1"
        or corpus.get("status") != "exact"
        or corpus.get("exact_row_set") is not True
        or corpus.get("errors") != []
        or not _is_sha256(corpus.get("manifest_eligible_row_set_sha256"))
        or corpus.get("manifest_eligible_row_set_sha256")
        != corpus.get("database_eligible_row_set_sha256")
    ):
        corpus_errors.append("downstream_corpus_binding_not_exact")
    meta: dict[str, Any] = {
        "status": "blocked",
        "path": str(manifest_path),
        "manifest_sha256": _file_sha256(manifest_path),
        "chain_status": (manifest.get("chain_completeness") or {}).get("status")
        if isinstance(manifest.get("chain_completeness"), dict)
        else None,
        "chain_standard_errors": chain_errors,
        "persisted_corpus_binding": corpus,
    }
    if chain_errors or corpus_errors:
        blockers = list(corpus_errors)
        if chain_errors:
            blockers.append("provider_chain_completeness_not_established")
        return (), meta, sorted(set(blockers))

    try:
        plan = fresh_import.build_plan(db_path=db_path)
        revalidation_errors = fresh_import.revalidate_complete_manifest_database(
            manifest, plan, db_path=db_path
        )
        current_corpus = fresh_import.manifest_database_corpus_binding(
            manifest, plan, db_path=db_path
        )
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        meta["revalidation_error"] = type(exc).__name__
        return (), meta, ["quote_manifest_database_revalidation_failed"]
    meta["revalidation_errors"] = revalidation_errors
    meta["recomputed_corpus_binding"] = current_corpus
    if revalidation_errors or current_corpus != corpus:
        return (), meta, ["quote_manifest_database_revalidation_failed"]

    batch_ids = _manifest_source_batch_ids(manifest)
    normalized_binding = {
        "binding_version": QUOTE_CORPUS_BINDING_VERSION,
        "manifest_bound": True,
        "exact_set_validated": True,
        "chain_completeness_status": "established",
        "manifest_sha256": meta["manifest_sha256"],
        "corpus_sha256": corpus.get("manifest_eligible_row_set_sha256"),
        "source_batch_ids": list(batch_ids),
    }
    validated_ids, normalized_meta, normalized_blockers = _quote_corpus_binding_audit(
        normalized_binding
    )
    meta.update(normalized_meta)
    meta["path"] = str(manifest_path)
    if normalized_blockers:
        return (), meta, normalized_blockers
    meta["status"] = "validated"
    return validated_ids, meta, []


def _quote_corpus_binding_audit(
    binding: dict[str, Any] | None,
) -> tuple[tuple[int, ...], dict[str, Any], list[str]]:
    blockers: list[str] = []
    if not isinstance(binding, dict):
        return (), {"status": "missing"}, ["missing_manifest_bound_quote_corpus"]
    raw_ids = binding.get("source_batch_ids")
    batch_ids: list[int] = []
    if not isinstance(raw_ids, list) or not raw_ids:
        blockers.append("missing_manifest_bound_validated_quote_batch_ids")
    else:
        for raw_id in raw_ids:
            if isinstance(raw_id, bool):
                blockers.append("invalid_manifest_bound_quote_batch_ids")
                break
            try:
                batch_id = int(raw_id)
            except (TypeError, ValueError):
                blockers.append("invalid_manifest_bound_quote_batch_ids")
                break
            if batch_id <= 0 or str(batch_id) != str(raw_id):
                blockers.append("invalid_manifest_bound_quote_batch_ids")
                break
            batch_ids.append(batch_id)
    if len(set(batch_ids)) != len(batch_ids):
        blockers.append("duplicate_manifest_bound_quote_batch_ids")
    if binding.get("binding_version") != QUOTE_CORPUS_BINDING_VERSION:
        blockers.append("unsupported_quote_corpus_binding_version")
    if (
        binding.get("manifest_bound") is not True
        or binding.get("exact_set_validated") is not True
    ):
        blockers.append("quote_corpus_exact_manifest_binding_not_established")
    if binding.get("chain_completeness_status") != "established":
        blockers.append("provider_chain_completeness_not_established")
    if not _is_sha256(binding.get("manifest_sha256")):
        blockers.append("missing_or_invalid_quote_manifest_sha256")
    if not _is_sha256(binding.get("corpus_sha256")):
        blockers.append("missing_or_invalid_quote_corpus_sha256")
    normalized_ids = tuple(sorted(set(batch_ids))) if not blockers else ()
    return (
        normalized_ids,
        {
            "status": "validated" if not blockers else "blocked",
            "binding_version": binding.get("binding_version"),
            "manifest_bound": binding.get("manifest_bound") is True,
            "exact_set_validated": binding.get("exact_set_validated") is True,
            "chain_completeness_status": binding.get("chain_completeness_status"),
            "manifest_sha256": binding.get("manifest_sha256"),
            "corpus_sha256": binding.get("corpus_sha256"),
            "source_batch_ids": list(normalized_ids),
        },
        sorted(set(blockers)),
    )


def _quote_batch_lineage_audit(
    conn: sqlite3.Connection, batch_ids: Sequence[int]
) -> tuple[dict[str, Any], list[str]]:
    required_columns = {
        "id",
        "source_label",
        "dataset_kind",
        "data_trust",
        "input_path",
        "file_hash",
        "total_rows",
        "imported_rows",
        "duplicate_rows",
        "rejected_rows",
    }
    columns = {
        str(row[1])
        for row in conn.execute("PRAGMA table_info(import_batches)").fetchall()
    }
    if not required_columns.issubset(columns):
        return (
            {
                "status": "blocked",
                "missing_schema_columns": sorted(required_columns - columns),
            },
            ["quote_batch_lineage_schema_incomplete"],
        )
    placeholders = ",".join("?" for _ in batch_ids)
    rows = conn.execute(
        f"""
        SELECT id, source_label, dataset_kind, data_trust, input_path, file_hash,
               total_rows, imported_rows, duplicate_rows, rejected_rows
        FROM import_batches
        WHERE id IN ({placeholders})
        ORDER BY id
        """,
        tuple(batch_ids),
    ).fetchall()
    returned_ids = {int(row[0]) for row in rows}
    blockers: list[str] = []
    if returned_ids != set(batch_ids):
        blockers.append("manifest_bound_quote_batch_missing_from_database")
    invalid_ids: list[int] = []
    for row in rows:
        valid = bool(
            row[1] == TRUSTED_SOURCE_LABEL
            and row[2] == "intraday_csv"
            and row[3] == "trusted"
            and str(row[4] or "").strip()
            and _is_sha256(row[5])
            and int(row[9]) == 0
            and int(row[6]) == int(row[7]) + int(row[8])
        )
        if not valid:
            invalid_ids.append(int(row[0]))
    if invalid_ids:
        blockers.append("manifest_bound_quote_batch_failed_integrity_contract")
    return (
        {
            "status": "validated" if not blockers else "blocked",
            "requested_batch_ids": list(batch_ids),
            "validated_batch_ids": sorted(returned_ids - set(invalid_ids)),
            "invalid_batch_ids": sorted(invalid_ids),
        },
        blockers,
    )


def _quotes(
    conn: sqlite3.Connection,
    symbol: str,
    day: str,
    validated_batch_ids: Sequence[int],
) -> list[sqlite3.Row]:
    if not validated_batch_ids:
        return []
    placeholders = ",".join("?" for _ in validated_batch_ids)
    return conn.execute(
        f"""
        WITH ranked AS (
            SELECT
                q.id, q.contract_symbol, q.option_type, q.strike, q.expiry,
                q.bid, q.ask, q.quote_date_et, q.quote_minute_et, q.as_of_utc,
                q.source_batch_id,
                ROW_NUMBER() OVER (
                    PARTITION BY q.quote_date_et, q.quote_minute_et, q.expiry,
                                 LOWER(q.option_type), q.strike, q.contract_symbol
                    ORDER BY q.as_of_utc ASC, q.source_batch_id ASC,
                             q.contract_symbol ASC, q.id ASC
                ) AS quote_rank
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE b.data_trust = 'trusted' AND b.source_label = ?
              AND b.dataset_kind = 'intraday_csv' AND b.rejected_rows = 0
              AND b.total_rows = b.imported_rows + b.duplicate_rows
              AND q.source_batch_id IN ({placeholders})
              AND q.snapshot_kind = 'intraday' AND q.underlying = ? AND q.quote_date_et = ?
              AND q.quote_minute_et = ? AND q.bid IS NOT NULL AND q.ask IS NOT NULL
              AND q.bid >= 0 AND q.ask > 0 AND q.ask >= q.bid
        )
        SELECT contract_symbol, option_type, strike, expiry, bid, ask,
               quote_date_et, quote_minute_et, as_of_utc, source_batch_id
        FROM ranked
        WHERE quote_rank = 1
        ORDER BY expiry, LOWER(option_type), strike, contract_symbol
        """,
        (TRUSTED_SOURCE_LABEL, *validated_batch_ids, symbol, day, EXIT_MINUTE),
    ).fetchall()


def _value(row: sqlite3.Row | dict[str, Any], key: str) -> Any:
    return row[key]


def _same_minute_pair(
    first: sqlite3.Row | dict[str, Any],
    second: sqlite3.Row | dict[str, Any],
    *,
    event_day: str,
    expected_minute: int = EXIT_MINUTE,
) -> bool:
    try:
        first_minute = int(_value(first, "quote_minute_et"))
        second_minute = int(_value(second, "quote_minute_et"))
    except (KeyError, TypeError, ValueError):
        return False
    first_as_of = _parse_utc(_value(first, "as_of_utc"))
    second_as_of = _parse_utc(_value(second, "as_of_utc"))
    expected_as_of = _event_timestamp_utc(event_day, expected_minute)
    return bool(
        first_minute == expected_minute
        and second_minute == expected_minute
        and str(_value(first, "quote_date_et")) == event_day
        and str(_value(second, "quote_date_et")) == event_day
        and first_as_of is not None
        and second_as_of is not None
        and first_as_of == expected_as_of
        and second_as_of == expected_as_of
        and first_as_of == second_as_of
    )


def _mid(row: sqlite3.Row | dict[str, Any]) -> float:
    return (float(_value(row, "bid")) + float(_value(row, "ask"))) / 2.0


def _spot_proxy(
    quotes: Sequence[sqlite3.Row | dict[str, Any]], expiry: str, day: str
) -> float | None:
    grouped_calls: dict[float, list[sqlite3.Row | dict[str, Any]]] = defaultdict(list)
    grouped_puts: dict[float, list[sqlite3.Row | dict[str, Any]]] = defaultdict(list)
    for row in quotes:
        if _value(row, "expiry") != expiry:
            continue
        option_type = str(_value(row, "option_type")).lower()
        if option_type == "call":
            grouped_calls[float(_value(row, "strike"))].append(row)
        elif option_type == "put":
            grouped_puts[float(_value(row, "strike"))].append(row)
    calls = {
        strike: rows[0] for strike, rows in grouped_calls.items() if len(rows) == 1
    }
    puts = {strike: rows[0] for strike, rows in grouped_puts.items() if len(rows) == 1}
    shared = sorted(
        strike
        for strike in set(calls) & set(puts)
        if _same_minute_pair(calls[strike], puts[strike], event_day=day)
    )
    if not shared:
        return None
    best = min(
        shared,
        key=lambda strike: (abs(_mid(calls[strike]) - _mid(puts[strike])), strike),
    )
    return best + _mid(calls[best]) - _mid(puts[best])


def _select_entry(
    quotes: Sequence[sqlite3.Row | dict[str, Any]], day: str, geometry: dict[str, Any]
) -> tuple[dict[str, Any] | None, str]:
    dte_lo, dte_hi = geometry["dte_range"]
    day_d = date.fromisoformat(day)
    expiries = sorted(
        {
            str(_value(row, "expiry"))
            for row in quotes
            if dte_lo
            <= (date.fromisoformat(str(_value(row, "expiry"))) - day_d).days
            <= dte_hi
        }
    )
    if not expiries:
        return None, "no_candidate"
    target_dte = (dte_lo + dte_hi) / 2
    expiry = min(
        expiries,
        key=lambda item: (
            abs((date.fromisoformat(item) - day_d).days - target_dte),
            item,
        ),
    )
    spot = _spot_proxy(quotes, expiry, day)
    if spot is None or spot <= 0:
        return None, "missing_synchronized_entry_leg_pair"
    grouped_puts: dict[float, list[sqlite3.Row | dict[str, Any]]] = defaultdict(list)
    for row in quotes:
        if (
            str(_value(row, "option_type")).lower() == "put"
            and _value(row, "expiry") == expiry
        ):
            grouped_puts[float(_value(row, "strike"))].append(row)
    if any(len(rows) != 1 for rows in grouped_puts.values()):
        return None, "ambiguous_contract_series_at_strike"
    puts = {strike: rows[0] for strike, rows in grouped_puts.items()}
    band = [strike for strike in puts if 0.93 * spot <= strike <= 0.97 * spot]
    if not band:
        return None, "no_candidate"
    short_k = min(band, key=lambda strike: (abs(strike - 0.95 * spot), strike))
    short_row = puts[short_k]
    widths = sorted(
        (short_k - strike, strike) for strike in puts if 3.0 <= short_k - strike <= 10.0
    )
    if not widths:
        return None, "no_candidate"
    width, long_k = min(widths, key=lambda item: (abs(item[0] - 5.0), item[0], item[1]))
    long_row = puts[long_k]
    if not _same_minute_pair(short_row, long_row, event_day=day):
        return None, "missing_synchronized_entry_leg_pair"
    if float(_value(short_row, "bid")) <= 0 or float(_value(long_row, "bid")) < 0:
        return None, "zero_bid_or_untradable"
    for leg in (short_row, long_row):
        mid = _mid(leg)
        if (
            mid <= 0
            or (float(_value(leg, "ask")) - float(_value(leg, "bid"))) / mid
            > geometry["max_leg_bid_ask_width_pct_mid"]
        ):
            return None, "rejected_width_or_credit"
    credit = float(_value(short_row, "bid")) - float(_value(long_row, "ask"))
    if not math.isfinite(credit) or not 0 < credit < width:
        return None, "rejected_width_or_credit"
    if credit < geometry["min_entry_credit_pct_width"] * width:
        return None, "rejected_width_or_credit"
    return {
        "expiry": expiry,
        "short_strike": short_k,
        "long_strike": long_k,
        "width": width,
        "entry_credit": round(credit, 4),
        "spot_proxy": round(spot, 4),
        "entry_quote_minute_et": EXIT_MINUTE,
        "entry_short_contract_symbol": _value(short_row, "contract_symbol"),
        "entry_long_contract_symbol": _value(long_row, "contract_symbol"),
        "entry_short_quote_as_of_utc": _value(short_row, "as_of_utc"),
        "entry_long_quote_as_of_utc": _value(long_row, "as_of_utc"),
        "entry_short_source_batch_id": int(_value(short_row, "source_batch_id")),
        "entry_long_source_batch_id": int(_value(long_row, "source_batch_id")),
        "entry_quote_pair_synchronized": True,
    }, "exact_entry_captured"


def _exit_debit(
    conn: sqlite3.Connection,
    symbol: str,
    day: str,
    pos: dict[str, Any],
    validated_batch_ids: Sequence[int],
) -> tuple[float | None, str, dict[str, Any]]:
    if not validated_batch_ids:
        return (
            None,
            "missing_manifest_bound_validated_quote_batch_ids",
            {"exit_quote_minute_et": EXIT_MINUTE},
        )
    placeholders = ",".join("?" for _ in validated_batch_ids)
    rows = conn.execute(
        f"""
        WITH ranked AS (
            SELECT
                q.id, q.contract_symbol, q.strike, q.bid, q.ask,
                q.quote_date_et, q.quote_minute_et, q.as_of_utc, q.source_batch_id,
                ROW_NUMBER() OVER (
                    PARTITION BY q.quote_date_et, q.quote_minute_et, q.expiry,
                                 LOWER(q.option_type), q.strike, q.contract_symbol
                    ORDER BY q.as_of_utc ASC, q.source_batch_id ASC,
                             q.contract_symbol ASC, q.id ASC
                ) AS quote_rank
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE b.data_trust = 'trusted' AND b.source_label = ?
              AND b.dataset_kind = 'intraday_csv' AND b.rejected_rows = 0
              AND b.total_rows = b.imported_rows + b.duplicate_rows
              AND q.source_batch_id IN ({placeholders})
              AND q.snapshot_kind = 'intraday' AND q.underlying = ? AND q.quote_date_et = ?
              AND q.quote_minute_et = ? AND q.expiry = ? AND LOWER(q.option_type) = 'put'
              AND q.contract_symbol IN (?, ?) AND q.bid IS NOT NULL AND q.ask IS NOT NULL
              AND q.bid >= 0 AND q.ask > 0 AND q.ask >= q.bid
        )
        SELECT contract_symbol, strike, bid, ask, quote_date_et, quote_minute_et,
               as_of_utc, source_batch_id
        FROM ranked
        WHERE quote_rank = 1
        ORDER BY strike, contract_symbol
        """,
        (
            TRUSTED_SOURCE_LABEL,
            *validated_batch_ids,
            symbol,
            day,
            EXIT_MINUTE,
            pos["expiry"],
            pos["entry_short_contract_symbol"],
            pos["entry_long_contract_symbol"],
        ),
    ).fetchall()
    short = next(
        (
            row
            for row in rows
            if row["contract_symbol"] == pos["entry_short_contract_symbol"]
        ),
        None,
    )
    long_ = next(
        (
            row
            for row in rows
            if row["contract_symbol"] == pos["entry_long_contract_symbol"]
        ),
        None,
    )
    if short is None or long_ is None:
        return (
            None,
            "missing_exact_entry_contract_exit_quote",
            {"exit_quote_minute_et": EXIT_MINUTE},
        )
    if float(short["strike"]) != float(pos["short_strike"]) or float(
        long_["strike"]
    ) != float(pos["long_strike"]):
        return (
            None,
            "exit_contract_geometry_mismatch",
            {"exit_quote_minute_et": EXIT_MINUTE},
        )
    if not _same_minute_pair(short, long_, event_day=day):
        return (
            None,
            "missing_synchronized_exit_leg_pair",
            {"exit_quote_minute_et": EXIT_MINUTE},
        )
    debit = float(short["ask"]) - float(long_["bid"])
    if not math.isfinite(debit) or debit < 0 or debit > float(pos["width"]):
        return None, "invalid_exit_debit", {"exit_quote_minute_et": EXIT_MINUTE}
    return (
        round(debit, 4),
        "exact_exit_quote_pair",
        {
            "exit_quote_minute_et": EXIT_MINUTE,
            "exit_short_contract_symbol": short["contract_symbol"],
            "exit_long_contract_symbol": long_["contract_symbol"],
            "exit_short_quote_as_of_utc": short["as_of_utc"],
            "exit_long_quote_as_of_utc": long_["as_of_utc"],
            "exit_short_source_batch_id": int(short["source_batch_id"]),
            "exit_long_source_batch_id": int(long_["source_batch_id"]),
            "exit_quote_pair_synchronized": True,
        },
    )


def _max_drawdown(values: Sequence[float]) -> float:
    equity = 0.0
    peak = 0.0
    maximum = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        maximum = max(maximum, peak - equity)
    return maximum


def _population_shape(values: Sequence[float]) -> tuple[float | None, float | None]:
    count = len(values)
    if count < 2:
        return None, None
    mean = sum(values) / count
    centered = [value - mean for value in values]
    variance = sum(value * value for value in centered) / count
    if variance <= 0:
        return None, None
    skewness = None
    excess_kurtosis = None
    if count >= 3:
        skewness = sum(value**3 for value in centered) / count / variance**1.5
    if count >= 4:
        excess_kurtosis = (
            sum(value**4 for value in centered) / count / variance**2 - 3.0
        )
    return skewness, excess_kurtosis


def _tail_statistics(
    rows: Sequence[dict[str, Any]], *, eligible_for_evaluation: bool
) -> dict[str, Any]:
    ordered = sorted(
        rows,
        key=lambda row: (
            str(row.get("exit_date") or ""),
            str(row.get("ticker") or ""),
            str(row.get("entry_date") or ""),
            str(row.get("expiry") or ""),
        ),
    )
    usd_values = [float(row["net_pnl_usd"]) for row in ordered]
    pct_values = [float(row["net_pnl_pct"]) for row in ordered]
    by_month: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        by_month[_month(str(row["exit_date"]))].append(row)
    worst_month: dict[str, Any] | None = None
    if by_month:
        month, month_rows = min(
            by_month.items(),
            key=lambda item: (
                sum(float(row["net_pnl_usd"]) for row in item[1]),
                item[0],
            ),
        )
        worst_month = {
            "month": month,
            "net_pnl_usd": round(
                sum(float(row["net_pnl_usd"]) for row in month_rows), 2
            ),
            "net_pnl_pct_points": round(
                sum(float(row["net_pnl_pct"]) for row in month_rows), 4
            ),
            "trade_count": len(month_rows),
        }
    skewness, excess_kurtosis = _population_shape(usd_values)
    return {
        "eligible_for_evaluation": eligible_for_evaluation,
        "pnl_basis": "net_after_frozen_round_trip_fees",
        "ordering": "exit_date_then_ticker_then_entry_date_then_expiry",
        "max_drawdown_usd": round(_max_drawdown(usd_values), 2) if usd_values else None,
        "max_drawdown_net_pnl_pct_points": round(_max_drawdown(pct_values), 4)
        if pct_values
        else None,
        "worst_month": worst_month,
        "trade_net_pnl_usd_skewness_population": round(skewness, 6)
        if skewness is not None
        else None,
        "trade_net_pnl_usd_excess_kurtosis_population": (
            round(excess_kurtosis, 6) if excess_kurtosis is not None else None
        ),
        "moment_method": "population standardized moments; kurtosis is excess kurtosis",
        "worst_trade_usd": min(usd_values, default=None),
        "best_trade_usd": max(usd_values, default=None),
    }


def _fee_aware_metrics(
    rows: Sequence[dict[str, Any]], *, branch_id: str, bootstrap_draws: int
) -> dict[str, Any]:
    if any(
        row.get("fee_aware") is not True
        or row.get("round_trip_fees_usd") is None
        or row.get("net_pnl_usd") is None
        or row.get("net_pnl_pct") is None
        for row in rows
    ):
        raise ValueError(
            "refusing to compute metrics from a non-fee-aware completed row"
        )
    metrics = _metrics(rows, branch_id=branch_id, bootstrap_draws=bootstrap_draws)
    metrics.update(
        {
            "pnl_basis": "net_after_frozen_round_trip_fees",
            "fee_model": {
                "per_leg_usd": FEE_PER_LEG,
                "round_trip_legs": ROUND_TRIP_LEGS,
            },
            "total_round_trip_fees_usd": round(
                sum(float(row["round_trip_fees_usd"]) for row in rows), 2
            ),
            "all_completed_rows_fee_aware": True,
        }
    )
    return metrics


def _validation_control() -> dict[str, Any]:
    return {
        "status": "blocked_missing_formal_evaluation_path",
        "blockers": [MISSING_FORMAL_VALIDATION_PATH],
        "formal_evaluation_path": None,
        "one_shot_registry_consuming": True,
        "operator_review_required": True,
        "disclosure": "No formal registry-consuming family_validation runner is implemented in this repository.",
    }


def _market_calendar_audit(
    market_dates: Sequence[str], *, expected_dates: Sequence[str]
) -> dict[str, Any]:
    supplied_counts = Counter(str(day) for day in market_dates)
    supplied = set(supplied_counts)
    expected = set(expected_dates)
    missing = sorted(expected - supplied)
    unexpected = sorted(supplied - expected)
    duplicates = sorted(day for day, count in supplied_counts.items() if count != 1)
    return {
        "calendar": "us_equity_market_days",
        "authoritative_source": "us_equity_market_calendar.is_us_equity_market_day",
        "expected_market_day_count": len(expected_dates),
        "supplied_market_date_count": len(market_dates),
        "supplied_distinct_market_date_count": len(supplied),
        "missing_market_day_count": len(missing),
        "missing_market_days": missing,
        "unexpected_market_date_count": len(unexpected),
        "unexpected_market_dates": unexpected,
        "duplicate_market_date_count": len(duplicates),
        "duplicate_market_dates": duplicates,
        "exact_match": not missing and not unexpected and not duplicates,
    }


def _date_identity_audit(
    rows: Sequence[dict[str, Any]],
    *,
    date_field: str,
    expected_dates: Sequence[str],
) -> dict[str, Any]:
    valid_counts: Counter[str] = Counter()
    invalid_dates: list[str] = []
    for row in rows:
        raw_day = str(row.get(date_field) or "")
        try:
            parsed = date.fromisoformat(raw_day)
        except ValueError:
            invalid_dates.append(raw_day)
        else:
            valid_counts[parsed.isoformat()] += 1
    valid_dates = set(valid_counts)
    expected = set(expected_dates)
    missing = sorted(expected - valid_dates)
    unexpected = sorted(valid_dates - expected)
    duplicates = sorted(day for day, count in valid_counts.items() if count != 1)
    invalid_dates.sort()
    return {
        "date_field": date_field,
        "expected_date_count": len(expected_dates),
        "supplied_row_count": len(rows),
        "valid_distinct_date_count": len(valid_dates),
        "missing_date_count": len(missing),
        "missing_dates": missing,
        "unexpected_date_count": len(unexpected),
        "unexpected_dates": unexpected,
        "invalid_date_count": len(invalid_dates),
        "invalid_dates": invalid_dates,
        "duplicate_date_count": len(duplicates),
        "duplicate_dates": duplicates,
        "exact_date_identity": (
            not missing and not unexpected and not invalid_dates and not duplicates
        ),
    }


def _blocked_run_result(
    *,
    status: str,
    split_name: str,
    split_start: str,
    split_end: str,
    blockers: Sequence[str],
    vix_meta: dict[str, Any] | None = None,
    crash_meta: dict[str, Any] | None = None,
    quote_meta: dict[str, Any] | None = None,
    market_calendar_audit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    unique_blockers = sorted(set(blockers))
    fees = ROUND_TRIP_LEGS * FEE_PER_LEG
    return {
        "status": status,
        "evaluation_ready": False,
        "evaluation_blockers": unique_blockers,
        "split": {"name": split_name, "start": split_start, "end": split_end},
        "denominator_statuses": {blocker: 1 for blocker in unique_blockers},
        "denominator_row_count": 0,
        "completed_trades": 0,
        "blocked_unresolved_trade_rows": 0,
        "exit_reasons": {},
        "metrics": {},
        "fee_model": {
            "per_leg_usd": FEE_PER_LEG,
            "round_trip_legs": ROUND_TRIP_LEGS,
            "round_trip_fees_usd": round(fees, 2),
            "metrics_basis": "net_after_frozen_round_trip_fees",
        },
        "tail_report": _tail_statistics([], eligible_for_evaluation=False),
        "market_calendar_audit": market_calendar_audit
        or {"status": "not_built_preflight_blocked"},
        "input_sources": {
            "vix_rows": vix_meta or {"status": "not_loaded_preflight_blocked"},
            "crash_guard": crash_meta or {"status": "not_loaded_preflight_blocked"},
            "quote_corpus": quote_meta or {"status": "not_loaded_preflight_blocked"},
        },
        "rows": [],
    }


def _split_preflight_blockers(
    *, split_name: str, split_start: str, split_end: str
) -> list[str]:
    if split_name == "family_validation":
        return [MISSING_FORMAL_VALIDATION_PATH]
    if split_name != "family_train":
        return ["unsupported_split_name"]
    try:
        start = date.fromisoformat(split_start)
        end = date.fromisoformat(split_end)
    except ValueError:
        return ["invalid_split_window"]
    if start > end:
        return ["invalid_split_window"]
    allowed_start, allowed_end = _frozen_train_window()
    if start.isoformat() != allowed_start or end.isoformat() != allowed_end:
        return ["split_window_does_not_match_exact_frozen_family_train"]
    return []


def _scoring_knob_blockers(
    *, vix_policy: dict[str, Any], geometry: dict[str, Any], bootstrap_draws: int
) -> tuple[float | None, float | None, list[str]]:
    blockers: list[str] = []
    try:
        low_max = float(vix_policy["low_max"])
        mid_max = float(vix_policy["mid_max"])
    except (KeyError, TypeError, ValueError):
        return None, None, ["invalid_scoring_vix_thresholds"]
    if not 0 < low_max < mid_max:
        blockers.append("invalid_scoring_vix_thresholds")
    frozen = _load_json(VIX_POLICY_CONTRACT)
    if low_max != float(frozen["low_max"]) or mid_max != float(frozen["mid_max"]):
        blockers.append("vix_thresholds_do_not_match_frozen_policy")
    if bootstrap_draws != FROZEN_BOOTSTRAP_DRAWS:
        blockers.append("bootstrap_draws_do_not_match_frozen_10000")
    frozen_geometry = _load_json(CONTRACT)["playbook_binding"]["geometry"]
    try:
        geometry_matches = json.dumps(
            geometry, sort_keys=True, separators=(",", ":")
        ) == json.dumps(frozen_geometry, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        geometry_matches = False
    if not geometry_matches:
        blockers.append("geometry_does_not_match_frozen_playbook_binding")
    return low_max, mid_max, blockers


def _unresolved_exit_blocker(dte_left: int, exit_status: str) -> str:
    return "unresolved_expiration_or_assignment" if dte_left <= 0 else exit_status


def run_split(
    *,
    split_name: str,
    split_start: str,
    split_end: str,
    vix_rows_path: Path,
    crash_guard_path: Path,
    vix_policy: dict[str, Any],
    market_dates: list[str],
    db_path: Path,
    geometry: dict[str, Any],
    bootstrap_draws: int,
    quote_manifest_path: Path | None = None,
) -> dict[str, Any]:
    split_blockers = _split_preflight_blockers(
        split_name=split_name, split_start=split_start, split_end=split_end
    )
    if split_blockers:
        return _blocked_run_result(
            status="blocked_split_not_authorized",
            split_name=split_name,
            split_start=split_start,
            split_end=split_end,
            blockers=split_blockers,
        )

    low_max, mid_max, knob_blockers = _scoring_knob_blockers(
        vix_policy=vix_policy, geometry=geometry, bootstrap_draws=bootstrap_draws
    )
    vix_rows, vix_meta = _load_row_file(
        vix_rows_path, container_keys=("source_rows", "bucket_rows", "vix_rows", "rows")
    )
    vix_by_date, duplicate_vix_dates = _index_rows(
        vix_rows, date_field="bucket_date_et"
    )
    crash_rows, crash_meta = _load_row_file(
        crash_guard_path, container_keys=("input_rows", "crash_guard_rows", "rows")
    )
    crash_by_date, duplicate_crash_dates = _index_rows(
        crash_rows, date_field="input_date_et"
    )

    expected_market_dates = _expected_us_equity_market_dates(split_start, split_end)
    market_calendar = _market_calendar_audit(
        market_dates, expected_dates=expected_market_dates
    )
    vix_date_identity = _date_identity_audit(
        vix_rows,
        date_field="bucket_date_et",
        expected_dates=expected_market_dates,
    )
    crash_date_identity = _date_identity_audit(
        crash_rows,
        date_field="input_date_et",
        expected_dates=expected_market_dates,
    )
    days = list(expected_market_dates)
    input_blockers = list(knob_blockers)
    validated_batch_ids, quote_binding_meta, quote_binding_blockers = (
        _verified_quote_corpus_from_manifest(quote_manifest_path, db_path)
    )
    input_blockers.extend(quote_binding_blockers)
    if not market_dates:
        input_blockers.append("missing_required_market_dates")
    if market_calendar["exact_match"] is not True:
        input_blockers.append(
            "market_dates_do_not_match_authoritative_us_equity_calendar"
        )
    if vix_meta.get("status") != "loaded" or not vix_rows:
        input_blockers.append("missing_required_point_in_time_vix_inputs")
    if crash_meta.get("status") != "loaded" or not crash_rows:
        input_blockers.append("missing_required_point_in_time_crash_regime_inputs")
    vix_meta = {
        **vix_meta,
        **vix_date_identity,
    }
    crash_meta = {
        **crash_meta,
        **crash_date_identity,
    }
    if vix_date_identity["exact_date_identity"] is not True:
        input_blockers.append("point_in_time_vix_date_identity_mismatch")
    if crash_date_identity["exact_date_identity"] is not True:
        input_blockers.append("point_in_time_crash_regime_date_identity_mismatch")
    if input_blockers:
        return _blocked_run_result(
            status="blocked_missing_or_invalid_replay_inputs",
            split_name=split_name,
            split_start=split_start,
            split_end=split_end,
            blockers=input_blockers,
            vix_meta=vix_meta,
            crash_meta=crash_meta,
            quote_meta=quote_binding_meta,
            market_calendar_audit=market_calendar,
        )
    assert low_max is not None and mid_max is not None
    fees = ROUND_TRIP_LEGS * FEE_PER_LEG
    statuses: Counter[str] = Counter()
    completed: list[dict[str, Any]] = []
    blocked_rows: list[dict[str, Any]] = []
    evaluation_blockers: set[str] = set()
    open_pos: dict[str, dict[str, Any]] = {}
    conn = sqlite3.connect(
        f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True, timeout=120
    )
    conn.row_factory = sqlite3.Row
    quote_batch_meta, quote_batch_blockers = _quote_batch_lineage_audit(
        conn, validated_batch_ids
    )
    if quote_batch_blockers:
        conn.close()
        return _blocked_run_result(
            status="blocked_missing_or_invalid_replay_inputs",
            split_name=split_name,
            split_start=split_start,
            split_end=split_end,
            blockers=quote_batch_blockers,
            vix_meta=vix_meta,
            crash_meta=crash_meta,
            quote_meta={**quote_binding_meta, "batch_lineage": quote_batch_meta},
            market_calendar_audit=market_calendar,
        )

    def block_position(symbol: str, pos: dict[str, Any], day: str, reason: str) -> None:
        statuses[reason] += 1
        evaluation_blockers.add(reason)
        row = {
            "ticker": symbol,
            "lane_id": "vrp_put_credit_spread_v1",
            "row_status": "blocked_unresolved",
            "blocking_status": reason,
            "entry_date": pos["entry_date"],
            "blocking_observation_date": day,
            "net_pnl_usd": None,
            "net_pnl_pct": None,
            "exact_priced": False,
            "proof_grade": "blocked_incomplete_denominator",
            "fee_aware": False,
        }
        for key in (
            "expiry",
            "short_strike",
            "long_strike",
            "width",
            "entry_credit",
            "entry_quote_minute_et",
            "entry_short_contract_symbol",
            "entry_long_contract_symbol",
            "entry_short_quote_as_of_utc",
            "entry_long_quote_as_of_utc",
            "entry_short_source_batch_id",
            "entry_long_source_batch_id",
            "entry_quote_pair_synchronized",
        ):
            if key in pos:
                row[key] = pos[key]
        blocked_rows.append(row)
        open_pos.pop(symbol, None)

    def close(
        symbol: str,
        pos: dict[str, Any],
        day: str,
        debit: float,
        reason: str,
        exit_quote: dict[str, Any],
    ) -> None:
        gross_pnl = (pos["entry_credit"] - debit) * 100.0
        pnl = gross_pnl - fees
        max_loss = (pos["width"] - pos["entry_credit"]) * 100.0 + fees
        completed.append(
            {
                "ticker": symbol,
                "lane_id": "vrp_put_credit_spread_v1",
                "row_status": "completed",
                "entry_date": pos["entry_date"],
                "exit_date": day,
                "exit_reason": reason,
                "exit_debit": round(debit, 4),
                "gross_pnl_usd_before_fees": round(gross_pnl, 2),
                "round_trip_fees_usd": round(fees, 2),
                "net_pnl_usd": round(pnl, 2),
                "gross_pnl_pct_before_fees": round(gross_pnl / max_loss * 100.0, 4)
                if max_loss > 0
                else None,
                "net_pnl_pct": round(pnl / max_loss * 100.0, 4)
                if max_loss > 0
                else None,
                "max_loss_usd": round(max_loss, 2),
                "fee_aware": True,
                "exact_priced": True,
                "proof_grade": "trusted_intraday_opra_nbbo",
                "fill_basis": "side_aware_bid_ask_cross",
                **{
                    key: pos[key]
                    for key in (
                        "expiry",
                        "short_strike",
                        "long_strike",
                        "width",
                        "entry_credit",
                        "entry_quote_minute_et",
                        "entry_short_contract_symbol",
                        "entry_long_contract_symbol",
                        "entry_short_quote_as_of_utc",
                        "entry_long_quote_as_of_utc",
                        "entry_short_source_batch_id",
                        "entry_long_source_batch_id",
                        "entry_quote_pair_synchronized",
                    )
                },
                **exit_quote,
            }
        )
        statuses["exact_exit_captured"] += 1
        open_pos.pop(symbol, None)

    for day in days:
        day_d = date.fromisoformat(day)
        for symbol in UNIVERSE:
            pos = open_pos.get(symbol)
            if pos:
                dte_left = (date.fromisoformat(pos["expiry"]) - day_d).days
                debit, exit_status, exit_quote = _exit_debit(
                    conn, symbol, day, pos, validated_batch_ids
                )
                if debit is None:
                    block_position(
                        symbol,
                        pos,
                        day,
                        _unresolved_exit_blocker(dte_left, exit_status),
                    )
                    continue
                if (
                    debit
                    <= geometry["profit_take_credit_fraction"] * pos["entry_credit"]
                ):
                    close(symbol, pos, day, debit, "profit_take", exit_quote)
                elif (
                    debit >= geometry["loss_cut_credit_multiple"] * pos["entry_credit"]
                ):
                    close(symbol, pos, day, debit, "loss_cut", exit_quote)
                elif dte_left <= geometry["time_exit_dte"]:
                    close(symbol, pos, day, debit, "time_exit", exit_quote)
                continue

            if day in duplicate_crash_dates:
                crash, crash_status = None, "duplicate_point_in_time_crash_guard_rows"
            else:
                crash, crash_status = _point_in_time_crash_guard(
                    crash_by_date.get(day), day
                )
            if crash is None:
                statuses[crash_status] += 1
                evaluation_blockers.add(crash_status)
                continue
            if crash:
                statuses["regime_excluded_crash"] += 1
                continue

            if day in duplicate_vix_dates:
                vix, vix_status = None, "duplicate_point_in_time_vix_rows"
            else:
                vix, vix_status = _point_in_time_vix(vix_by_date.get(day), day)
            if vix is None:
                statuses[vix_status] += 1
                evaluation_blockers.add(vix_status)
                continue
            if vix > mid_max:
                statuses["regime_excluded_high_vix"] += 1
                continue

            quotes = _quotes(conn, symbol, day, validated_batch_ids)
            if not quotes:
                statuses["missing_entry_quote_surface"] += 1
                evaluation_blockers.add("missing_entry_quote_surface")
                continue
            entry, status = _select_entry(quotes, day, geometry)
            statuses[status] += 1
            if status in {
                "missing_leg_quote",
                "missing_synchronized_entry_leg_pair",
                "ambiguous_contract_series_at_strike",
            }:
                evaluation_blockers.add(status)
            if entry:
                entry["entry_date"] = day
                entry["entry_vix"] = vix
                entry["vix_bucket"] = "low" if vix <= low_max else "mid"
                entry["crash_regime"] = False
                open_pos[symbol] = entry

    for symbol, pos in sorted(list(open_pos.items())):
        block_position(symbol, pos, split_end, "open_at_split_end_unresolved")
    conn.close()

    if not completed:
        evaluation_blockers.add("zero_completed_trades")
    evaluation_ready = not evaluation_blockers
    metrics = (
        _fee_aware_metrics(
            completed,
            branch_id=f"{REPORT_ID}:{split_start[:7]}",
            bootstrap_draws=bootstrap_draws,
        )
        if evaluation_ready and completed
        else {}
    )
    exit_reasons = Counter(row["exit_reason"] for row in completed)
    rows = sorted(
        [*completed, *blocked_rows],
        key=lambda row: (
            str(row.get("entry_date") or ""),
            str(row.get("ticker") or ""),
            str(row.get("exit_date") or row.get("blocking_observation_date") or ""),
            str(row.get("row_status") or ""),
        ),
    )
    return {
        "status": "ready_fee_aware_research_evaluation"
        if evaluation_ready
        else "blocked_incomplete_replay_denominator",
        "evaluation_ready": evaluation_ready,
        "evaluation_blockers": sorted(evaluation_blockers),
        "split": {"name": split_name, "start": split_start, "end": split_end},
        "denominator_statuses": dict(sorted(statuses.items())),
        "denominator_row_count": len(rows),
        "completed_trades": len(completed),
        "blocked_unresolved_trade_rows": len(blocked_rows),
        "exit_reasons": dict(sorted(exit_reasons.items())),
        "metrics": metrics,
        "fee_model": {
            "per_leg_usd": FEE_PER_LEG,
            "round_trip_legs": ROUND_TRIP_LEGS,
            "round_trip_fees_usd": round(fees, 2),
            "metrics_basis": "net_after_frozen_round_trip_fees",
        },
        "tail_report": _tail_statistics(
            completed, eligible_for_evaluation=evaluation_ready
        ),
        "market_calendar_audit": market_calendar,
        "input_sources": {
            "vix_rows": vix_meta,
            "crash_guard": crash_meta,
            "quote_corpus": {
                **quote_binding_meta,
                "batch_lineage": quote_batch_meta,
            },
        },
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Research-only VRP put-credit-spread replay (fresh window)."
    )
    parser.add_argument(
        "--split", choices=["family_train", "family_validation"], default="family_train"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--import-manifest", type=Path, default=DEFAULT_IMPORT_MANIFEST)
    parser.add_argument(
        "--feature-store", type=Path, default=FF / "feature-store" / "latest.json"
    )
    parser.add_argument(
        "--vix-source-rows",
        type=Path,
        default=FF / "point-in-time-vix-bucket" / "source_rows.jsonl",
    )
    parser.add_argument("--crash-guard", type=Path, default=DEFAULT_CRASH_GUARD)
    parser.add_argument(
        "--vix-low-max",
        type=float,
        default=None,
        help="override low-bucket max (else frozen policy)",
    )
    parser.add_argument(
        "--vix-mid-max",
        type=float,
        default=None,
        help="override mid-bucket max (else frozen policy)",
    )
    parser.add_argument(
        "--vix-policy",
        type=Path,
        default=FF / "point-in-time-vix-bucket" / "latest.json",
    )
    parser.add_argument("--bootstrap-draws", type=int, default=10000)
    parser.add_argument(
        "--output-dir", type=Path, default=FF / "vrp-credit-spread-replay"
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.split == "family_validation":
        raise SystemExit(
            f"family_validation blocked: {MISSING_FORMAL_VALIDATION_PATH}; no formal registry-consuming "
            "evaluation path is implemented, so this research harness cannot score or consume that split"
        )

    contract = _load_json(CONTRACT)
    window_contract = _load_json(WINDOW_CONTRACT)
    split = window_contract["split_rule"][args.split]
    if _overlaps_consumed(split["start_month"], split["end_month"]):
        raise SystemExit("refusing: split overlaps consumed window")

    bucket = _load_json(args.vix_policy)
    thresholds = bucket.get("threshold_policy") or bucket.get("frozen_thresholds") or {}
    low_max = (
        args.vix_low_max
        if args.vix_low_max is not None
        else thresholds.get("low_max") or thresholds.get("low_bucket_max")
    )
    mid_max = (
        args.vix_mid_max
        if args.vix_mid_max is not None
        else thresholds.get("mid_max") or thresholds.get("mid_bucket_max")
    )
    if low_max is None or mid_max is None:
        raise SystemExit(
            f"cannot resolve frozen VIX bucket thresholds from {args.vix_policy}; pass "
            "--vix-low-max/--vix-mid-max from the frozen policy contract"
        )

    feature_store = _load_json(args.feature_store)
    market_dates = sorted(
        str(day) for day in feature_store.get("shared_quote_dates") or []
    )
    split_start = f"{split['start_month']}-01"
    split_end = _month_end(str(split["end_month"]))

    result = run_split(
        split_name=args.split,
        split_start=split_start,
        split_end=split_end,
        vix_rows_path=args.vix_source_rows,
        crash_guard_path=args.crash_guard,
        vix_policy={"low_max": low_max, "mid_max": mid_max},
        market_dates=market_dates,
        db_path=args.db,
        geometry=contract["playbook_binding"]["geometry"],
        bootstrap_draws=args.bootstrap_draws,
        quote_manifest_path=args.import_manifest,
    )
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": datetime.now(UTC)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "contract": str(CONTRACT.relative_to(ROOT)).replace("\\", "/"),
        "split_name": args.split,
        "vix_thresholds": {"low_max": low_max, "mid_max": mid_max},
        "crash_guard_contract": {
            "source": str(args.crash_guard),
            "explicit_boolean_required": True,
            "vix_is_not_a_crash_guard_substitute": True,
        },
        "family_validation_control": _validation_control(),
        **{key: value for key, value in result.items() if key != "rows"},
        **FALSE_FLAGS,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / f"{args.split}_latest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8"
    )
    (args.output_dir / f"{args.split}_rows.jsonl").write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in result["rows"])
        + ("\n" if result["rows"] else ""),
        encoding="utf8",
    )
    print(
        json.dumps(
            {
                key: value
                for key, value in report.items()
                if key != "denominator_statuses"
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
