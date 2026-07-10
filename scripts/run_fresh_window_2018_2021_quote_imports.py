"""Resumable monthly ThetaData OPRA imports for the 2018-2021 fresh window.

The database is authoritative. An atomic manifest checkpoints attempts, but a
chunk is skipped only after its trusted bid/ask coverage is revalidated from
the quote store. Provider/request failures stop before the child importer can
write, and no completion state is emitted until every planned chunk verifies.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing, contextmanager
from datetime import UTC, date, datetime, time as datetime_time, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from us_equity_market_calendar import (  # noqa: E402
    is_us_equity_market_day,
    us_equity_market_close_time_et,
)


CONTRACT_ID = "regular_options_filter_family_fresh_window_v1"
CONTRACT_PATH = (
    ROOT
    / "data"
    / "contracts"
    / "regular-options-filter-family-fresh-window-contract-v1.json"
)
FROZEN_CONTRACT_CANONICAL_SHA256 = (
    "f54be365893aec81f61a8943c3835c098a8332b4bae46c629b9c5b9560a20657"
)
DEFAULT_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_MANIFEST = (
    ROOT / "data" / "options-validation" / "fresh_window_2018_2021_import_manifest.json"
)
DEFAULT_LOCK = (
    ROOT / "data" / "options-validation" / "fresh_window_2018_2021_import.lock"
)
DEFAULT_LOG = ROOT / "data" / "options-validation" / "fresh_window_2018_2021_import.log"
IMPORT_SCRIPT = ROOT / "scripts" / "import_thetadata_options_nbbo.py"
CSV_OUTPUT_DIR = ROOT / "data" / "options-validation" / "thetadata-nbbo"
SOURCE_LABEL = "thetadata_opra_nbbo_1m"
MANIFEST_SCHEMA_VERSION = 3
CHAIN_COMPLETENESS_STANDARD_VERSION = "regular_options_provider_chain_completeness_v1"
CHAIN_COMPLETENESS_SCOPE = (
    "every_provider_listed_contract_in_each_requested_symbol_date_time_dte_right_scope"
)
MIN_FREE_GB = 20.0
WINDOW_START = date(2018, 1, 1)
WINDOW_END = date(2021, 12, 31)
SYMBOLS = (
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
PASSES: tuple[dict[str, Any], ...] = (
    {
        "label": "entry_1010",
        "start_time": "10:10:00",
        "end_time": "10:10:00",
        "min_dte": 5,
        "max_dte": 35,
    },
    {
        "label": "exit_1555",
        "start_time": "15:55:00",
        "end_time": "15:55:00",
        "min_dte": 5,
        "max_dte": 60,
    },
)
EASTERN_TZ = ZoneInfo("America/New_York")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path.resolve()).replace("\\", "/")


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _unproved_chain_completeness() -> dict[str, Any]:
    return {
        "standard_version": CHAIN_COMPLETENESS_STANDARD_VERSION,
        "required_scope": CHAIN_COMPLETENESS_SCOPE,
        "status": "not_established",
        "standard_satisfied": False,
        "selection_or_evaluation_authorized": False,
        "limitation": (
            "per-symbol/date call/put coverage and exact CSV/database row binding do not prove an exhaustive "
            "provider chain across every listed strike and expiration"
        ),
        "required_chunk_proofs": [
            "provider_response_exhaustive",
            "provider_contract_identity_set_sha256",
            "trusted_database_contract_identity_set_sha256",
            "provider_eligible_quote_row_set_sha256",
            "trusted_database_eligible_quote_row_set_sha256",
            "eligible_row_set_exact",
        ],
    }


def _is_sha256(value: Any) -> bool:
    token = str(value or "")
    return len(token) == 64 and all(
        character in "0123456789abcdef" for character in token
    )


def chain_completeness_standard_errors(manifest: dict[str, Any]) -> list[str]:
    """Validate the versioned proof required before selection or evaluation.

    This validates only the manifest proof structure. A downstream consumer must
    also run ``revalidate_complete_manifest_database`` against its selected DB.
    """
    errors: list[str] = []
    completeness = manifest.get("chain_completeness")
    if not isinstance(completeness, dict):
        return ["chain_completeness_proof_missing"]
    if completeness.get("standard_version") != CHAIN_COMPLETENESS_STANDARD_VERSION:
        errors.append("chain_completeness_standard_version_mismatch")
    if completeness.get("required_scope") != CHAIN_COMPLETENESS_SCOPE:
        errors.append("chain_completeness_scope_mismatch")
    if (
        completeness.get("status") != "satisfied"
        or completeness.get("standard_satisfied") is not True
    ):
        errors.append("chain_completeness_standard_not_satisfied")
    if completeness.get("selection_or_evaluation_authorized") is not True:
        errors.append("chain_completeness_selection_or_evaluation_not_authorized")
    if completeness.get("proof_spec_hash") != manifest.get("spec_hash"):
        errors.append("chain_completeness_proof_spec_hash_mismatch")

    states = manifest.get("chunks")
    proofs = completeness.get("chunk_proofs")
    if (
        not isinstance(states, dict)
        or not isinstance(proofs, dict)
        or set(proofs) != set(states)
    ):
        errors.append("chain_completeness_chunk_proof_identity_set_mismatch")
        return sorted(set(errors))
    for chunk_id, state in states.items():
        proof = proofs.get(chunk_id)
        if not isinstance(state, dict) or not isinstance(proof, dict):
            errors.append(f"chain_completeness_chunk_proof_invalid:{chunk_id}")
            continue
        if proof.get("chunk_spec_hash") != state.get("chunk_spec_hash"):
            errors.append(f"chain_completeness_chunk_spec_hash_mismatch:{chunk_id}")
        if proof.get("provider_response_exhaustive") is not True:
            errors.append(
                f"chain_completeness_provider_exhaustiveness_unproved:{chunk_id}"
            )
        provider_contract_hash = proof.get("provider_contract_identity_set_sha256")
        database_contract_hash = proof.get(
            "trusted_database_contract_identity_set_sha256"
        )
        if (
            not _is_sha256(provider_contract_hash)
            or database_contract_hash != provider_contract_hash
        ):
            errors.append(f"chain_completeness_contract_set_mismatch:{chunk_id}")
        provider_row_hash = proof.get("provider_eligible_quote_row_set_sha256")
        database_row_hash = proof.get("trusted_database_eligible_quote_row_set_sha256")
        if not _is_sha256(provider_row_hash) or database_row_hash != provider_row_hash:
            errors.append(f"chain_completeness_eligible_row_set_mismatch:{chunk_id}")
        if proof.get("eligible_row_set_exact") is not True:
            errors.append(f"chain_completeness_exact_row_set_unproved:{chunk_id}")
    return sorted(set(errors))


def _parse_provider_lineage_timestamp(
    value: Any,
    *,
    expected_date: str,
    start_time: str,
    end_time: str,
) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    local = parsed.astimezone(EASTERN_TZ)
    requested_start = datetime_time.fromisoformat(start_time)
    requested_end = datetime_time.fromisoformat(end_time)
    local_time = local.time().replace(tzinfo=None)
    if (
        local.date().isoformat() != expected_date
        or not requested_start <= local_time <= requested_end
    ):
        return None
    return parsed


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_and_validate_frozen_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"fresh-window contract missing: {path}")
    payload = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(payload, dict):
        raise ValueError("fresh-window contract did not contain a JSON object")
    errors: list[str] = []
    if _canonical_hash(payload) != FROZEN_CONTRACT_CANONICAL_SHA256:
        errors.append("contract_canonical_sha256_mismatch")
    if payload.get("contract_id") != CONTRACT_ID:
        errors.append("contract_id_mismatch")
    window = payload.get("window") if isinstance(payload.get("window"), dict) else {}
    if (window.get("requested_start_date"), window.get("requested_end_date")) != (
        WINDOW_START.isoformat(),
        WINDOW_END.isoformat(),
    ):
        errors.append("contract_window_mismatch")
    split_rule = (
        payload.get("split_rule") if isinstance(payload.get("split_rule"), dict) else {}
    )
    if split_rule.get("family_train") != {
        "start_month": "2018-01",
        "end_month": "2020-06",
    }:
        errors.append("contract_family_train_split_mismatch")
    if split_rule.get("family_validation") != {
        "start_month": "2020-07",
        "end_month": "2021-12",
    }:
        errors.append("contract_family_validation_split_mismatch")
    if split_rule.get("split_fixed_before_import") is not True:
        errors.append("contract_split_not_fixed_before_import")
    proof_set = (
        payload.get("proof_set") if isinstance(payload.get("proof_set"), dict) else {}
    )
    if proof_set.get("symbols") != list(SYMBOLS) or proof_set.get(
        "symbol_count"
    ) != len(SYMBOLS):
        errors.append("contract_proof_set_mismatch")
    quote_plan = (
        payload.get("quote_import_plan")
        if isinstance(payload.get("quote_import_plan"), dict)
        else {}
    )
    if (
        quote_plan.get("entry_minute")
        != "10:10:00 ET single minute, DTE 5-35, both rights"
    ):
        errors.append("contract_entry_quote_plan_mismatch")
    if (
        quote_plan.get("exit_minute")
        != "15:55:00 ET single minute, DTE 5-60, both rights"
    ):
        errors.append("contract_exit_quote_plan_mismatch")
    if errors:
        raise ValueError(
            f"fresh-window frozen contract validation failed: {sorted(errors)}"
        )
    return payload


def _minute_of_day(value: str) -> int:
    hour, minute, *_seconds = (int(item) for item in value.split(":"))
    return hour * 60 + minute


def _resolved_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _storage_volume_probe(path: Path) -> tuple[tuple[str, int | str], Path]:
    probe = path.resolve()
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        return ("device", int(probe.stat().st_dev)), probe
    except OSError:
        return ("anchor", str(probe.anchor).lower()), probe


def _database_identity(db_path: Path) -> dict[str, Any]:
    resolved = db_path.resolve()
    base: dict[str, Any] = {
        "resolved_path": _resolved_path(db_path),
        "exists": resolved.exists(),
    }
    if not resolved.exists():
        body = {
            **base,
            "status": "missing",
            "schema_sha256": None,
            "required_tables_present": False,
        }
        return {**body, "identity_sha256": _canonical_hash(body)}
    stat = resolved.stat()
    uri = f"{resolved.as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True, timeout=120.0)) as connection:
            connection.execute("PRAGMA query_only=ON")
            schema_rows = connection.execute(
                "SELECT type, name, COALESCE(sql, '') FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            ).fetchall()
            schema_payload = [list(row) for row in schema_rows]
            table_names = {str(row[1]) for row in schema_rows if str(row[0]) == "table"}
            required_columns = {
                "import_batches": {
                    "id",
                    "source_label",
                    "dataset_kind",
                    "data_trust",
                    "input_path",
                    "file_hash",
                    "imported_at_utc",
                    "total_rows",
                    "imported_rows",
                    "duplicate_rows",
                    "rejected_rows",
                    "warnings_json",
                },
                "option_quote_snapshots": {
                    "id",
                    "as_of_utc",
                    "source_batch_id",
                    "quote_date_et",
                    "quote_minute_et",
                    "underlying",
                    "contract_symbol",
                    "option_type",
                    "strike",
                    "bid",
                    "ask",
                    "last",
                    "iv",
                    "underlying_price",
                    "volume",
                    "open_interest",
                    "expiry",
                    "snapshot_kind",
                },
            }
            observed_columns = {
                table: {
                    str(row[1])
                    for row in connection.execute(f"PRAGMA table_info('{table}')")
                }
                for table in required_columns
                if table in table_names
            }
            required_indexes = {
                "idx_option_quotes_underlying_date",
                "idx_option_quotes_contract_date",
                "idx_option_quotes_tuple_date",
                "idx_option_quotes_snapshot_underlying",
                "idx_option_quotes_snapshot_asof",
                "idx_option_quotes_snapshot_quote_date",
                "idx_option_quotes_source_batch_snapshot_date",
                "idx_import_batches_source_trust_kind",
            }
            observed_indexes = {
                str(row[1]) for row in schema_rows if str(row[0]) == "index"
            }
            expected_unique_columns = ["as_of_utc", "contract_symbol", "snapshot_kind"]
            unique_snapshot_key_present = any(
                int(index_row[2]) == 1
                and [
                    str(column_row[2])
                    for column_row in connection.execute(
                        f"PRAGMA index_info('{index_row[1]}')"
                    )
                ]
                == expected_unique_columns
                for index_row in connection.execute(
                    "PRAGMA index_list('option_quote_snapshots')"
                )
            )
            application_id = int(
                connection.execute("PRAGMA application_id").fetchone()[0]
            )
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            schema_version = int(
                connection.execute("PRAGMA schema_version").fetchone()[0]
            )
    except sqlite3.Error as exc:
        body = {
            **base,
            "status": "unreadable",
            "error": f"{type(exc).__name__}: {exc}",
            "schema_sha256": None,
            "required_tables_present": False,
        }
        return {**body, "identity_sha256": _canonical_hash(body)}
    required_tables = {"import_batches", "option_quote_snapshots"}
    required_columns_present = all(
        required.issubset(observed_columns.get(table, set()))
        for table, required in required_columns.items()
    )
    required_indexes_present = required_indexes.issubset(observed_indexes)
    body = {
        **base,
        "status": (
            "ready"
            if (
                required_tables.issubset(table_names)
                and required_columns_present
                and required_indexes_present
                and unique_snapshot_key_present
            )
            else "schema_incomplete"
        ),
        "file_device": int(stat.st_dev),
        "file_inode": int(stat.st_ino),
        "application_id": application_id,
        "user_version": user_version,
        "schema_version": schema_version,
        "schema_sha256": _canonical_hash(schema_payload),
        "required_tables": sorted(required_tables),
        "required_tables_present": required_tables.issubset(table_names),
        "required_columns": {
            table: sorted(columns)
            for table, columns in sorted(required_columns.items())
        },
        "observed_required_table_columns": {
            table: sorted(columns)
            for table, columns in sorted(observed_columns.items())
        },
        "required_columns_present": required_columns_present,
        "required_indexes": sorted(required_indexes),
        "required_indexes_present": required_indexes_present,
        "unique_snapshot_key_columns": expected_unique_columns,
        "unique_snapshot_key_present": unique_snapshot_key_present,
    }
    return {**body, "identity_sha256": _canonical_hash(body)}


def _database_identity_errors(
    actual: dict[str, Any], expected: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if actual.get("status") != "ready":
        errors.append(
            f"database_identity_not_ready:{actual.get('status') or 'missing'}"
        )
    if actual.get("resolved_path") != expected.get("resolved_path"):
        errors.append("database_resolved_path_mismatch")
    if actual.get("identity_sha256") != expected.get("identity_sha256"):
        errors.append("database_identity_sha256_mismatch")
    return errors


def _unsupported_sessions(
    market_dates: Sequence[str],
    *,
    start_time: str,
    end_time: str,
) -> list[dict[str, Any]]:
    requested_start = datetime_time.fromisoformat(start_time)
    requested_end = datetime_time.fromisoformat(end_time)
    unsupported: list[dict[str, Any]] = []
    for raw_date in market_dates:
        session_date = date.fromisoformat(raw_date)
        close_time = us_equity_market_close_time_et(session_date)
        if close_time is None:
            unsupported.append(
                {
                    "date": raw_date,
                    "reason": "market_close_time_metadata_missing",
                    "market_close_time_et": None,
                    "requested_start_time_et": requested_start.isoformat(),
                    "requested_end_time_et": requested_end.isoformat(),
                }
            )
            continue
        if requested_start > close_time or requested_end > close_time:
            unsupported.append(
                {
                    "date": raw_date,
                    "reason": "requested_time_after_market_close",
                    "market_close_time_et": close_time.isoformat(),
                    "requested_start_time_et": requested_start.isoformat(),
                    "requested_end_time_et": requested_end.isoformat(),
                }
            )
    return unsupported


def month_chunks(
    start: date = WINDOW_START, end: date = WINDOW_END
) -> list[tuple[date, date]]:
    chunks: list[tuple[date, date]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        following = date(cursor.year + (cursor.month == 12), (cursor.month % 12) + 1, 1)
        chunks.append((max(cursor, start), min(following - timedelta(days=1), end)))
        cursor = following
    return chunks


def _market_dates(start: date, end: date) -> list[str]:
    values: list[str] = []
    cursor = start
    while cursor <= end:
        if is_us_equity_market_day(cursor):
            values.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return values


def _build_plan_from_spec(
    *,
    window_start: date = WINDOW_START,
    window_end: date = WINDOW_END,
    symbols: Sequence[str] = SYMBOLS,
    passes: Sequence[dict[str, Any]] = PASSES,
    contract_path: Path = CONTRACT_PATH,
    db_path: Path = DEFAULT_DB,
) -> dict[str, Any]:
    if not contract_path.exists():
        raise FileNotFoundError(f"fresh-window contract missing: {contract_path}")
    contract_payload = json.loads(contract_path.read_text(encoding="utf8"))
    if not isinstance(contract_payload, dict):
        raise ValueError("fresh-window contract did not contain a JSON object")
    normalized_symbols = tuple(
        str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()
    )
    chunks: list[dict[str, Any]] = []
    for pass_spec in passes:
        for chunk_start, chunk_end in month_chunks(window_start, window_end):
            market_dates = _market_dates(chunk_start, chunk_end)
            chunk = {
                "chunk_id": f"{pass_spec['label']}:{chunk_start:%Y-%m}",
                "label": str(pass_spec["label"]),
                "month": f"{chunk_start:%Y-%m}",
                "date_from": chunk_start.isoformat(),
                "date_to": chunk_end.isoformat(),
                "market_dates": market_dates,
                "expected_request_count": len(market_dates) * len(normalized_symbols),
                "start_time": str(pass_spec["start_time"]),
                "end_time": str(pass_spec["end_time"]),
                "quote_minute_et": _minute_of_day(str(pass_spec["start_time"])),
                "min_dte": int(pass_spec["min_dte"]),
                "max_dte": int(pass_spec["max_dte"]),
                "right": "both",
                "snapshot_kind": "intraday",
                "interval": "1m",
                "source_label": SOURCE_LABEL,
            }
            chunk["unsupported_market_sessions"] = _unsupported_sessions(
                market_dates,
                start_time=chunk["start_time"],
                end_time=chunk["end_time"],
            )
            chunk["spec_hash"] = _canonical_hash(chunk)
            chunks.append(chunk)
    unsupported_sessions = [
        {"chunk_id": chunk["chunk_id"], **item}
        for chunk in chunks
        for item in chunk["unsupported_market_sessions"]
    ]
    preflight_blockers: list[str] = []
    if unsupported_sessions:
        reasons = {str(item.get("reason") or "") for item in unsupported_sessions}
        if "market_close_time_metadata_missing" in reasons:
            preflight_blockers.append(
                "market_close_time_metadata_missing_for_planned_session"
            )
        if "requested_time_after_market_close" in reasons:
            preflight_blockers.append(
                "frozen_quote_time_unavailable_on_early_close_sessions"
            )
    if preflight_blockers:
        database_identity_body = {
            "resolved_path": _resolved_path(db_path),
            "exists": None,
            "status": "not_checked_preflight_blocked",
            "reason": "unsupported_market_session_preflight",
            "schema_sha256": None,
            "required_tables_present": False,
        }
        database_identity = {
            **database_identity_body,
            "identity_sha256": _canonical_hash(database_identity_body),
        }
    else:
        database_identity = _database_identity(db_path)
        if database_identity.get("status") != "ready":
            preflight_blockers.append(
                f"database_identity_not_ready:{database_identity.get('status') or 'missing'}"
            )
    plan_body = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "contract_path": _rel(contract_path),
        "contract_sha256": _file_hash(contract_path),
        "contract_canonical_sha256": _canonical_hash(contract_payload),
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "symbols": list(normalized_symbols),
        "source_label": SOURCE_LABEL,
        "database_identity": database_identity,
        "preflight": {
            "status": "blocked" if preflight_blockers else "ready",
            "blockers": preflight_blockers,
            "unsupported_market_sessions": unsupported_sessions,
            "contract_time_reinterpreted": False,
        },
        "chain_completeness": _unproved_chain_completeness(),
        "chunks": chunks,
    }
    return {**plan_body, "spec_hash": _canonical_hash(plan_body)}


def build_plan(*, db_path: Path = DEFAULT_DB) -> dict[str, Any]:
    _load_and_validate_frozen_contract(CONTRACT_PATH)
    return _build_plan_from_spec(db_path=db_path, contract_path=CONTRACT_PATH)


def _new_manifest(plan: dict[str, Any]) -> dict[str, Any]:
    now = _utc_now_iso()
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "spec_hash": plan["spec_hash"],
        "database_identity": plan["database_identity"],
        "exact_plan": plan,
        "exact_plan_sha256": _canonical_hash(plan),
        "preflight": plan["preflight"],
        "chain_completeness": plan["chain_completeness"],
        "status": "in_progress",
        "created_at_utc": now,
        "updated_at_utc": now,
        "completed_at_utc": None,
        "chunk_count": len(plan["chunks"]),
        "chunks": {
            chunk["chunk_id"]: {
                "chunk_spec_hash": chunk["spec_hash"],
                "status": "pending",
                "attempt_count": 0,
            }
            for chunk in plan["chunks"]
        },
    }


def manifest_validation_errors(
    manifest: dict[str, Any], plan: dict[str, Any], *, require_complete: bool
) -> list[str]:
    errors: list[str] = []
    if manifest.get("manifest_schema_version") != MANIFEST_SCHEMA_VERSION:
        errors.append("manifest_schema_version_mismatch")
    if manifest.get("contract_id") != CONTRACT_ID:
        errors.append("contract_id_mismatch")
    if manifest.get("spec_hash") != plan.get("spec_hash"):
        errors.append("spec_hash_mismatch")
    plan_body = {key: value for key, value in plan.items() if key != "spec_hash"}
    if plan.get("spec_hash") != _canonical_hash(plan_body):
        errors.append("recomputed_plan_spec_hash_mismatch")
    if manifest.get("exact_plan") != plan or manifest.get(
        "exact_plan_sha256"
    ) != _canonical_hash(plan):
        errors.append("manifest_exact_plan_mismatch")
    if manifest.get("database_identity") != plan.get("database_identity"):
        errors.append("manifest_database_identity_mismatch")
    if manifest.get("chain_completeness") != plan.get("chain_completeness"):
        errors.append("manifest_chain_completeness_mismatch")
    states = manifest.get("chunks")
    if not isinstance(states, dict):
        return [*errors, "chunks_missing_or_invalid"]
    expected_ids = {chunk["chunk_id"] for chunk in plan["chunks"]}
    if set(states) != expected_ids:
        errors.append("chunk_identity_set_mismatch")
    for chunk in plan["chunks"]:
        chunk_body = {key: value for key, value in chunk.items() if key != "spec_hash"}
        if chunk.get("spec_hash") != _canonical_hash(chunk_body):
            errors.append(f"recomputed_chunk_spec_hash_mismatch:{chunk['chunk_id']}")
        state = states.get(chunk["chunk_id"])
        if not isinstance(state, dict):
            errors.append(f"chunk_state_missing:{chunk['chunk_id']}")
            continue
        if state.get("chunk_spec_hash") != chunk["spec_hash"]:
            errors.append(f"chunk_spec_hash_mismatch:{chunk['chunk_id']}")
        if require_complete and state.get("status") != "complete_verified":
            errors.append(f"chunk_not_complete:{chunk['chunk_id']}")
        if require_complete:
            lineage = state.get("provider_request_lineage")
            if (
                not isinstance(lineage, dict)
                or lineage.get("status") != "complete_verified"
            ):
                errors.append(
                    f"chunk_provider_lineage_not_complete:{chunk['chunk_id']}"
                )
            child_result = state.get("child_result")
            if not isinstance(child_result, dict) or not isinstance(
                child_result.get("request_results"), list
            ):
                errors.append(
                    f"chunk_provider_request_results_missing:{chunk['chunk_id']}"
                )
            elif not isinstance(lineage, dict) or lineage.get(
                "request_results_sha256"
            ) != _canonical_hash(child_result["request_results"]):
                errors.append(
                    f"chunk_provider_lineage_hash_mismatch:{chunk['chunk_id']}"
                )
            coverage = state.get("last_coverage")
            if not isinstance(coverage, dict) or coverage.get("complete") is not True:
                errors.append(
                    f"chunk_database_coverage_not_complete:{chunk['chunk_id']}"
                )
            elif coverage.get("database_identity_sha256") != plan[
                "database_identity"
            ].get("identity_sha256"):
                errors.append(f"chunk_database_identity_mismatch:{chunk['chunk_id']}")
    if require_complete:
        corpus_binding = manifest.get("downstream_corpus_binding")
        if (
            not isinstance(corpus_binding, dict)
            or corpus_binding.get("status") != "exact"
        ):
            errors.append("downstream_corpus_binding_not_exact")
        elif (
            corpus_binding.get("exact_row_set") is not True
            or corpus_binding.get("manifest_eligible_row_set_sha256")
            != corpus_binding.get("database_eligible_row_set_sha256")
            or corpus_binding.get("errors") != []
        ):
            errors.append("downstream_corpus_binding_evidence_mismatch")
    if require_complete and manifest.get("status") != "complete_verified":
        errors.append("manifest_not_complete_verified")
    return errors


def _load_or_create_manifest(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return _new_manifest(plan)
    payload = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(payload, dict):
        raise ValueError("import manifest did not contain a JSON object")
    errors = manifest_validation_errors(payload, plan, require_complete=False)
    if errors:
        raise ValueError(
            f"import manifest is incompatible with the current exact plan: {errors}"
        )
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _persist_manifest(path: Path, manifest: dict[str, Any]) -> None:
    manifest["updated_at_utc"] = _utc_now_iso()
    _atomic_write_json(path, manifest)


def _append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8") as handle:
        handle.write(f"{_utc_now_iso()} {message}\n")


def _pid_is_live(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@contextmanager
def _exclusive_lock(
    path: Path,
    *,
    spec_hash: str,
    recover_stale: bool = False,
    pid_is_live: Callable[[int], bool] = _pid_is_live,
) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not recover_stale:
            raise RuntimeError(f"fresh-window import lock already exists: {path}")
        try:
            existing = json.loads(path.read_text(encoding="utf8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"stale-lock recovery refused: unreadable lock {path}"
            ) from exc
        if not isinstance(existing, dict):
            raise RuntimeError(
                f"stale-lock recovery refused: invalid lock payload {path}"
            )
        if existing.get("spec_hash") != spec_hash:
            raise RuntimeError(
                "stale-lock recovery refused: lock spec does not match the current exact plan"
            )
        try:
            existing_pid = int(existing.get("pid") or 0)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                "stale-lock recovery refused: lock pid is invalid"
            ) from exc
        if pid_is_live(existing_pid):
            raise RuntimeError(
                f"stale-lock recovery refused: pid {existing_pid} is still live"
            )
        path.unlink()
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"fresh-window import lock already exists: {path}") from exc
    created_lock_stat = os.fstat(descriptor)
    try:
        lock_payload = {
            "pid": os.getpid(),
            "started_at_utc": _utc_now_iso(),
            "spec_hash": spec_hash,
            "owner_token": secrets.token_hex(32),
        }
        os.write(
            descriptor, (json.dumps(lock_payload, sort_keys=True) + "\n").encode("utf8")
        )
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            current_lock_stat = path.stat()
        except FileNotFoundError:
            current_lock_stat = None
        try:
            current_lock_payload = (
                json.loads(path.read_text(encoding="utf8"))
                if current_lock_stat is not None
                else None
            )
        except (OSError, json.JSONDecodeError):
            current_lock_payload = None
        if (
            current_lock_stat is not None
            and current_lock_stat.st_dev == created_lock_stat.st_dev
            and current_lock_stat.st_ino == created_lock_stat.st_ino
            and isinstance(current_lock_payload, dict)
            and current_lock_payload.get("owner_token") == lock_payload["owner_token"]
            and current_lock_payload.get("spec_hash") == spec_hash
            and current_lock_payload.get("pid") == os.getpid()
        ):
            path.unlink(missing_ok=True)


def _coverage_for_chunk(
    db_path: Path,
    chunk: dict[str, Any],
    symbols: Sequence[str],
    *,
    expected_database_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected_pairs = {
        (day, symbol) for day in chunk["market_dates"] for symbol in symbols
    }
    covered_pairs: set[tuple[str, str]] = set()
    pair_coverage: dict[tuple[str, str], dict[str, Any]] = {}
    import_batch_coverage: list[dict[str, Any]] = []
    observed_batch_ids: set[int] = set()
    actual_database_identity = _database_identity(db_path)
    identity_errors = (
        _database_identity_errors(actual_database_identity, expected_database_identity)
        if expected_database_identity is not None
        else []
    )
    if not identity_errors and db_path.exists() and expected_pairs:
        placeholders = ",".join("?" for _ in symbols)
        query = f"""
            SELECT q.quote_date_et, q.underlying,
                   SUM(CASE WHEN LOWER(q.option_type) = 'call' THEN 1 ELSE 0 END) AS call_rows,
                   SUM(CASE WHEN LOWER(q.option_type) = 'put' THEN 1 ELSE 0 END) AS put_rows,
                   COUNT(*) AS total_rows,
                   MIN(CAST(julianday(q.expiry) - julianday(q.quote_date_et) AS INTEGER)) AS min_dte,
                   MAX(CAST(julianday(q.expiry) - julianday(q.quote_date_et) AS INTEGER)) AS max_dte,
                   GROUP_CONCAT(DISTINCT b.id) AS import_batch_ids
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE b.source_label = ? AND b.data_trust = 'trusted'
              AND b.dataset_kind = 'intraday_csv'
              AND b.rejected_rows = 0
              AND b.total_rows = b.imported_rows + b.duplicate_rows
              AND q.snapshot_kind = 'intraday'
              AND q.quote_date_et BETWEEN ? AND ?
              AND q.quote_minute_et = ?
              AND q.underlying IN ({placeholders})
              AND q.bid IS NOT NULL AND q.ask IS NOT NULL AND q.ask >= q.bid
              AND (julianday(q.expiry) - julianday(q.quote_date_et)) BETWEEN ? AND ?
            GROUP BY q.quote_date_et, q.underlying
        """
        params: list[Any] = [
            SOURCE_LABEL,
            chunk["date_from"],
            chunk["date_to"],
            int(chunk["quote_minute_et"]),
            *symbols,
            int(chunk["min_dte"]),
            int(chunk["max_dte"]),
        ]
        uri = f"{db_path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=120.0)) as connection:
            connection.execute("PRAGMA query_only=ON")
            for (
                day,
                symbol,
                call_rows,
                put_rows,
                total_rows,
                min_dte,
                max_dte,
                batch_ids,
            ) in connection.execute(query, params):
                key = (str(day), str(symbol).upper())
                pair_coverage[key] = {
                    "date": key[0],
                    "symbol": key[1],
                    "call_row_count": int(call_rows or 0),
                    "put_row_count": int(put_rows or 0),
                    "total_row_count": int(total_rows or 0),
                    "observed_min_dte": int(min_dte) if min_dte is not None else None,
                    "observed_max_dte": int(max_dte) if max_dte is not None else None,
                    "import_batch_ids": sorted(
                        int(value)
                        for value in str(batch_ids or "").split(",")
                        if value.strip().isdigit()
                    ),
                }
                observed_batch_ids.update(pair_coverage[key]["import_batch_ids"])
                if int(call_rows or 0) > 0 and int(put_rows or 0) > 0:
                    covered_pairs.add(key)
            if observed_batch_ids:
                batch_placeholders = ",".join("?" for _ in observed_batch_ids)
                batch_query = f"""
                    SELECT id, source_label, dataset_kind, data_trust, input_path, file_hash,
                           total_rows, imported_rows, duplicate_rows, rejected_rows
                    FROM import_batches
                    WHERE id IN ({batch_placeholders})
                    ORDER BY id
                """
                for row in connection.execute(batch_query, sorted(observed_batch_ids)):
                    import_batch_coverage.append(
                        {
                            "batch_id": int(row[0]),
                            "source_label": str(row[1]),
                            "dataset_kind": str(row[2]),
                            "data_trust": str(row[3]),
                            "input_path": str(row[4]),
                            "file_hash": str(row[5]),
                            "total_rows": int(row[6]),
                            "imported_rows": int(row[7]),
                            "duplicate_rows": int(row[8]),
                            "rejected_rows": int(row[9]),
                        }
                    )
    missing = sorted(expected_pairs - covered_pairs)
    return {
        "expected_pair_count": len(expected_pairs),
        "covered_pair_count": len(expected_pairs & covered_pairs),
        "missing_pair_count": len(missing),
        "missing_pairs": [f"{day}:{symbol}" for day, symbol in missing],
        "pair_coverage": [pair_coverage[key] for key in sorted(pair_coverage)],
        "import_batches": import_batch_coverage,
        "database_identity": actual_database_identity,
        "database_identity_sha256": actual_database_identity.get("identity_sha256"),
        "database_identity_errors": identity_errors,
        "chain_completeness": {
            "status": "not_established",
            "limitation": "at-least-one executable call and put does not prove exhaustive chain completeness",
        },
        "complete": bool(expected_pairs and not missing and not identity_errors),
    }


def _child_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": payload.get("status"),
        "expected_request_count": payload.get("expected_request_count"),
        "successful_request_count": payload.get("successful_request_count"),
        "failed_request_count": payload.get("failed_request_count"),
        "empty_request_count": payload.get("empty_request_count"),
        "request_surface_complete": payload.get("request_surface_complete"),
        "generated_rows": payload.get("generated_rows"),
        "csv_path": payload.get("csv_path"),
        "csv_artifact": payload.get("csv_artifact"),
        "import_result": payload.get("import_result"),
        "database_import_complete": payload.get("database_import_complete"),
        "request_results": list(payload.get("request_results") or []),
        "chain_completeness": payload.get("chain_completeness"),
        "request_errors": list(payload.get("request_errors") or [])[:20],
        "empty_requests": list(payload.get("empty_requests") or [])[:20],
    }


def _csv_request_lineage_errors(
    csv_path: Path,
    *,
    chunk: dict[str, Any],
    expected_pairs: set[tuple[str, str]],
    indexed_requests: dict[tuple[str, str], dict[str, Any]],
    expected_row_count: int,
) -> list[str]:
    errors: list[str] = []
    pair_right_counts: dict[tuple[str, str, str], int] = {}
    pair_dtes: dict[tuple[str, str], list[int]] = {}
    pair_timestamps: dict[tuple[str, str], list[datetime]] = {}
    observed_row_count = 0
    required_fields = {
        "as_of_utc",
        "underlying",
        "contract_symbol",
        "expiry",
        "option_type",
        "strike",
        "bid",
        "ask",
    }
    try:
        with csv_path.open("r", encoding="utf8", newline="") as handle:
            reader = csv.DictReader(handle)
            if not required_fields.issubset(set(reader.fieldnames or [])):
                return ["csv_artifact_required_fields_missing"]
            for row_number, row in enumerate(reader, start=2):
                observed_row_count += 1
                underlying = str(row.get("underlying") or "").strip().upper()
                option_type = str(row.get("option_type") or "").strip().lower()
                try:
                    parsed_timestamp = datetime.fromisoformat(
                        str(row.get("as_of_utc") or "").replace("Z", "+00:00")
                    )
                    if parsed_timestamp.tzinfo is None:
                        raise ValueError("timestamp is naive")
                    local_date = (
                        parsed_timestamp.astimezone(EASTERN_TZ).date().isoformat()
                    )
                    if (
                        _parse_provider_lineage_timestamp(
                            row.get("as_of_utc"),
                            expected_date=local_date,
                            start_time=chunk["start_time"],
                            end_time=chunk["end_time"],
                        )
                        is None
                    ):
                        raise ValueError("timestamp outside requested window")
                    expiry = date.fromisoformat(str(row.get("expiry") or ""))
                    dte = (expiry - date.fromisoformat(local_date)).days
                    strike = float(str(row.get("strike") or ""))
                    bid = float(str(row.get("bid") or ""))
                    ask = float(str(row.get("ask") or ""))
                except (TypeError, ValueError):
                    errors.append(f"csv_row_lineage_invalid:{row_number}")
                    continue
                pair = (local_date, underlying)
                if pair not in expected_pairs:
                    errors.append(
                        f"csv_unexpected_request_pair:{row_number}:{local_date}:{underlying}"
                    )
                    continue
                if option_type not in {"call", "put"}:
                    errors.append(f"csv_invalid_option_right:{row_number}")
                    continue
                if (
                    not math.isfinite(strike)
                    or strike <= 0
                    or not math.isfinite(bid)
                    or not math.isfinite(ask)
                ):
                    errors.append(f"csv_non_finite_contract_or_quote:{row_number}")
                    continue
                if not int(chunk["min_dte"]) <= dte <= int(chunk["max_dte"]):
                    errors.append(f"csv_dte_outside_requested_window:{row_number}")
                    continue
                if bid < 0 or ask <= 0 or ask < bid:
                    errors.append(f"csv_non_executable_quote:{row_number}")
                    continue
                expected_contract_symbol = (
                    f"{underlying}{expiry.strftime('%y%m%d')}{'C' if option_type == 'call' else 'P'}"
                    f"{int(round(strike * 1000)):08d}"
                )
                if (
                    str(row.get("contract_symbol") or "").strip().upper()
                    != expected_contract_symbol
                ):
                    errors.append(f"csv_occ_contract_symbol_mismatch:{row_number}")
                    continue
                key = (local_date, underlying, option_type)
                pair_right_counts[key] = pair_right_counts.get(key, 0) + 1
                pair_dtes.setdefault(pair, []).append(dte)
                pair_timestamps.setdefault(pair, []).append(parsed_timestamp)
    except OSError as exc:
        return [f"csv_artifact_read_failed:{type(exc).__name__}"]
    if observed_row_count != expected_row_count:
        errors.append("csv_artifact_physical_row_count_mismatch")
    for day, symbol in sorted(expected_pairs):
        request = indexed_requests.get((day, symbol)) or {}
        if pair_right_counts.get((day, symbol, "call"), 0) != _safe_int(
            request.get("call_row_count")
        ):
            errors.append(f"csv_call_count_mismatch:{day}:{symbol}")
        if pair_right_counts.get((day, symbol, "put"), 0) != _safe_int(
            request.get("put_row_count")
        ):
            errors.append(f"csv_put_count_mismatch:{day}:{symbol}")
        dtes = pair_dtes.get((day, symbol)) or []
        if (
            not dtes
            or min(dtes) != request.get("observed_min_dte")
            or max(dtes) != request.get("observed_max_dte")
        ):
            errors.append(f"csv_observed_dte_mismatch:{day}:{symbol}")
        timestamps = pair_timestamps.get((day, symbol)) or []
        request_first = _parse_provider_lineage_timestamp(
            request.get("first_provider_timestamp_utc"),
            expected_date=day,
            start_time=chunk["start_time"],
            end_time=chunk["end_time"],
        )
        request_last = _parse_provider_lineage_timestamp(
            request.get("last_provider_timestamp_utc"),
            expected_date=day,
            start_time=chunk["start_time"],
            end_time=chunk["end_time"],
        )
        if (
            not timestamps
            or request_first is None
            or request_last is None
            or min(timestamps) != request_first
            or max(timestamps) != request_last
        ):
            errors.append(f"csv_provider_timestamp_extrema_mismatch:{day}:{symbol}")
    return sorted(set(errors))


def _persisted_import_batch_for_lineage(
    database_coverage: dict[str, Any],
    batch_id: Any,
) -> dict[str, Any] | None:
    resolved_path = str(
        (database_coverage.get("database_identity") or {}).get("resolved_path") or ""
    )
    normalized_batch_id = _safe_int(batch_id, default=-1)
    if not resolved_path or normalized_batch_id < 0:
        return None
    db_path = Path(resolved_path)
    try:
        uri = f"{db_path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=120.0)) as connection:
            connection.execute("PRAGMA query_only=ON")
            row = connection.execute(
                """
                SELECT id, source_label, dataset_kind, data_trust, input_path, file_hash,
                       total_rows, imported_rows, duplicate_rows, rejected_rows
                FROM import_batches
                WHERE id = ?
                """,
                (normalized_batch_id,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return {
        "batch_id": int(row[0]),
        "source_label": str(row[1]),
        "dataset_kind": str(row[2]),
        "data_trust": str(row[3]),
        "input_path": str(row[4]),
        "file_hash": str(row[5]),
        "total_rows": int(row[6]),
        "imported_rows": int(row[7]),
        "duplicate_rows": int(row[8]),
        "rejected_rows": int(row[9]),
    }


def _quote_row_binding_key(
    timestamp: Any,
    underlying: Any,
    contract_symbol: Any,
    expiry: Any,
    option_type: Any,
    strike: Any,
    bid: Any,
    ask: Any,
) -> tuple[Any, ...]:
    parsed = datetime.fromisoformat(str(timestamp or "").replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp is naive")
    return (
        parsed.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        str(underlying or "").strip().upper(),
        str(contract_symbol or "").strip().upper(),
        date.fromisoformat(str(expiry or "")).isoformat(),
        str(option_type or "").strip().lower(),
        round(float(strike), 8),
        round(float(bid), 8),
        round(float(ask), 8),
    )


def _csv_database_row_binding_errors(
    csv_path: Path,
    *,
    chunk: dict[str, Any],
    database_coverage: dict[str, Any],
    symbols: Sequence[str],
) -> list[str]:
    resolved_path = str(
        (database_coverage.get("database_identity") or {}).get("resolved_path") or ""
    )
    if not resolved_path:
        return ["database_path_missing_for_csv_row_binding"]
    normalized_symbols = tuple(
        sorted(
            {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
        )
    )
    symbol_placeholders = ",".join("?" for _ in normalized_symbols)
    query = f"""
        SELECT q.as_of_utc, q.underlying, q.contract_symbol, q.expiry, q.option_type,
               q.strike, q.bid, q.ask
        FROM option_quote_snapshots q
        JOIN import_batches b ON b.id = q.source_batch_id
        WHERE b.source_label = ?
          AND b.data_trust = 'trusted'
          AND b.dataset_kind = 'intraday_csv'
          AND b.rejected_rows = 0
          AND b.total_rows = b.imported_rows + b.duplicate_rows
          AND q.snapshot_kind = 'intraday'
          AND q.quote_date_et BETWEEN ? AND ?
          AND q.quote_minute_et = ?
          AND q.underlying IN ({symbol_placeholders})
          AND q.strike > 0 AND ABS(q.strike) < 1000000000
          AND q.bid IS NOT NULL AND q.ask IS NOT NULL
          AND q.bid >= 0 AND q.ask > 0 AND q.ask >= q.bid
          AND ABS(q.bid) < 1000000000 AND ABS(q.ask) < 1000000000
          AND (julianday(q.expiry) - julianday(q.quote_date_et)) BETWEEN ? AND ?
    """

    try:
        uri = f"{Path(resolved_path).resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=120.0)) as connection:
            connection.execute("PRAGMA query_only=ON")
            database_keys = {
                _quote_row_binding_key(*row)
                for row in connection.execute(
                    query,
                    (
                        SOURCE_LABEL,
                        chunk["date_from"],
                        chunk["date_to"],
                        int(chunk["quote_minute_et"]),
                        *normalized_symbols,
                        int(chunk["min_dte"]),
                        int(chunk["max_dte"]),
                    ),
                )
            }
        errors: list[str] = []
        csv_keys: set[tuple[Any, ...]] = set()
        with csv_path.open("r", encoding="utf8", newline="") as handle:
            for row_number, row in enumerate(csv.DictReader(handle), start=2):
                try:
                    csv_key = _quote_row_binding_key(
                        row.get("as_of_utc"),
                        row.get("underlying"),
                        row.get("contract_symbol"),
                        row.get("expiry"),
                        row.get("option_type"),
                        row.get("strike"),
                        row.get("bid"),
                        row.get("ask"),
                    )
                except (TypeError, ValueError):
                    errors.append(f"csv_database_row_key_invalid:{row_number}")
                    continue
                csv_keys.add(csv_key)
                if csv_key not in database_keys:
                    errors.append(
                        f"csv_row_missing_exact_trusted_database_match:{row_number}"
                    )
        extra_database_keys = database_keys - csv_keys
        missing_database_keys = csv_keys - database_keys
        if extra_database_keys:
            errors.append(
                f"trusted_database_rows_absent_from_csv_exact_set:{len(extra_database_keys)}"
            )
        if missing_database_keys:
            errors.append(
                f"csv_rows_absent_from_trusted_database_exact_set:{len(missing_database_keys)}"
            )
        if database_keys != csv_keys:
            errors.append("csv_database_eligible_row_set_not_exact")
        return sorted(set(errors))
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        return [f"csv_database_row_binding_failed:{type(exc).__name__}"]


def manifest_database_corpus_binding(
    manifest: dict[str, Any],
    plan: dict[str, Any],
    *,
    db_path: Path,
) -> dict[str, Any]:
    """Bind the full downstream-readable fresh-window DB corpus to manifest CSV rows."""
    errors: list[str] = []
    manifest_keys: set[tuple[Any, ...]] = set()
    states = manifest.get("chunks") if isinstance(manifest.get("chunks"), dict) else {}
    for chunk in plan.get("chunks") or []:
        chunk_id = str(chunk.get("chunk_id") or "")
        state = states.get(chunk_id) if isinstance(states, dict) else None
        child_result = state.get("child_result") if isinstance(state, dict) else None
        csv_artifact = (
            child_result.get("csv_artifact") if isinstance(child_result, dict) else None
        )
        csv_path_value = str((csv_artifact or {}).get("path") or "")
        csv_path = Path(csv_path_value)
        if not csv_path_value or not csv_path.is_file():
            errors.append(f"manifest_corpus_csv_missing:{chunk_id}")
            continue
        try:
            with csv_path.open("r", encoding="utf8", newline="") as handle:
                for row_number, row in enumerate(csv.DictReader(handle), start=2):
                    try:
                        manifest_keys.add(
                            _quote_row_binding_key(
                                row.get("as_of_utc"),
                                row.get("underlying"),
                                row.get("contract_symbol"),
                                row.get("expiry"),
                                row.get("option_type"),
                                row.get("strike"),
                                row.get("bid"),
                                row.get("ask"),
                            )
                        )
                    except (TypeError, ValueError):
                        errors.append(
                            f"manifest_corpus_csv_row_key_invalid:{chunk_id}:{row_number}"
                        )
        except OSError as exc:
            errors.append(
                f"manifest_corpus_csv_read_failed:{chunk_id}:{type(exc).__name__}"
            )

    normalized_symbols = tuple(
        sorted(
            {
                str(symbol).strip().upper()
                for symbol in (plan.get("symbols") or [])
                if str(symbol).strip()
            }
        )
    )
    database_keys: set[tuple[Any, ...]] = set()
    try:
        if not normalized_symbols:
            raise ValueError("empty symbol corpus")
        placeholders = ",".join("?" for _ in normalized_symbols)
        query = f"""
            SELECT q.as_of_utc, q.underlying, q.contract_symbol, q.expiry, q.option_type,
                   q.strike, q.bid, q.ask
            FROM option_quote_snapshots q
            JOIN import_batches b ON b.id = q.source_batch_id
            WHERE b.source_label = ?
              AND b.data_trust = 'trusted'
              AND q.snapshot_kind = 'intraday'
              AND q.quote_date_et BETWEEN ? AND ?
              AND q.underlying IN ({placeholders})
              AND q.strike > 0 AND ABS(q.strike) < 1000000000
              AND q.bid IS NOT NULL AND q.ask IS NOT NULL
              AND q.bid >= 0 AND q.ask > 0 AND q.ask >= q.bid
              AND ABS(q.bid) < 1000000000 AND ABS(q.ask) < 1000000000
        """
        uri = f"{db_path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True, timeout=120.0)) as connection:
            connection.execute("PRAGMA query_only=ON")
            database_keys = {
                _quote_row_binding_key(*row)
                for row in connection.execute(
                    query,
                    (
                        SOURCE_LABEL,
                        str((plan.get("window") or {}).get("start") or ""),
                        str((plan.get("window") or {}).get("end") or ""),
                        *normalized_symbols,
                    ),
                )
            }
    except (sqlite3.Error, TypeError, ValueError) as exc:
        errors.append(f"manifest_corpus_database_read_failed:{type(exc).__name__}")

    extra_database_keys = database_keys - manifest_keys
    missing_database_keys = manifest_keys - database_keys
    if extra_database_keys:
        errors.append(
            f"trusted_database_rows_outside_manifest_corpus:{len(extra_database_keys)}"
        )
    if missing_database_keys:
        errors.append(
            f"manifest_corpus_rows_missing_from_trusted_database:{len(missing_database_keys)}"
        )
    if database_keys != manifest_keys:
        errors.append("manifest_database_corpus_row_set_not_exact")
    manifest_hash = _canonical_hash(sorted(manifest_keys))
    database_hash = _canonical_hash(sorted(database_keys))
    return {
        "standard_version": "fresh_window_manifest_database_corpus_v1",
        "scope": "all_executable_trusted_intraday_rows_for_plan_window_symbols",
        "status": "exact"
        if not errors and manifest_keys == database_keys
        else "blocked",
        "manifest_eligible_row_count": len(manifest_keys),
        "database_eligible_row_count": len(database_keys),
        "manifest_eligible_row_set_sha256": manifest_hash,
        "database_eligible_row_set_sha256": database_hash,
        "exact_row_set": not errors and manifest_keys == database_keys,
        "errors": sorted(set(errors)),
    }


def _provider_lineage_errors(
    payload: dict[str, Any],
    *,
    chunk: dict[str, Any],
    symbols: Sequence[str],
    expected_database_identity: dict[str, Any],
    database_coverage: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    expected_pairs = {
        (day, symbol) for day in chunk["market_dates"] for symbol in symbols
    }
    results = payload.get("request_results")
    if not isinstance(results, list):
        return ["request_results_missing_or_invalid"]
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    for item in results:
        if not isinstance(item, dict):
            errors.append("request_result_not_object")
            continue
        key = (str(item.get("date") or ""), str(item.get("symbol") or "").upper())
        if key in indexed:
            errors.append(f"duplicate_request_result:{key[0]}:{key[1]}")
        indexed[key] = item
    if set(indexed) != expected_pairs:
        errors.append("request_result_identity_set_mismatch")
    normalized_row_total = 0
    for day, symbol in sorted(expected_pairs):
        item = indexed.get((day, symbol))
        if item is None:
            continue
        if item.get("request_id") != f"{symbol}:{day}":
            errors.append(f"request_id_mismatch:{day}:{symbol}")
        if (
            item.get("provider_request_succeeded") is not True
            or item.get("status") != "request_complete"
        ):
            errors.append(f"provider_request_not_complete:{day}:{symbol}")
        if item.get("requested_right") != chunk["right"]:
            errors.append(f"requested_right_mismatch:{day}:{symbol}")
        if (
            item.get("min_dte") != chunk["min_dte"]
            or item.get("max_dte") != chunk["max_dte"]
        ):
            errors.append(f"requested_dte_mismatch:{day}:{symbol}")
        if (
            item.get("start_time") != chunk["start_time"]
            or item.get("end_time") != chunk["end_time"]
        ):
            errors.append(f"requested_time_mismatch:{day}:{symbol}")
        call_row_count = _safe_int(item.get("call_row_count"))
        put_row_count = _safe_int(item.get("put_row_count"))
        if call_row_count <= 0 or put_row_count <= 0:
            errors.append(f"requested_right_coverage_missing:{day}:{symbol}")
        normalized_row_count = _safe_int(item.get("normalized_row_count"))
        normalized_row_total += normalized_row_count
        if (
            normalized_row_count <= 0
            or normalized_row_count != call_row_count + put_row_count
        ):
            errors.append(f"normalized_right_count_mismatch:{day}:{symbol}")
        if (
            _safe_int(item.get("provider_response_row_count"), default=-1)
            < normalized_row_count
        ):
            errors.append(f"provider_response_row_count_invalid:{day}:{symbol}")
        observed_min_dte = item.get("observed_min_dte")
        observed_max_dte = item.get("observed_max_dte")
        if (
            not isinstance(observed_min_dte, int)
            or not isinstance(observed_max_dte, int)
            or observed_min_dte < int(chunk["min_dte"])
            or observed_max_dte > int(chunk["max_dte"])
            or observed_min_dte > observed_max_dte
        ):
            errors.append(f"observed_dte_lineage_invalid:{day}:{symbol}")
        first_timestamp = _parse_provider_lineage_timestamp(
            item.get("first_provider_timestamp_utc"),
            expected_date=day,
            start_time=chunk["start_time"],
            end_time=chunk["end_time"],
        )
        last_timestamp = _parse_provider_lineage_timestamp(
            item.get("last_provider_timestamp_utc"),
            expected_date=day,
            start_time=chunk["start_time"],
            end_time=chunk["end_time"],
        )
        if (
            first_timestamp is None
            or last_timestamp is None
            or first_timestamp > last_timestamp
        ):
            errors.append(f"provider_timestamp_lineage_missing:{day}:{symbol}")
        if _safe_int(item.get("lineage_rejection_count"), default=-1) != 0:
            errors.append(f"provider_lineage_rejections_present:{day}:{symbol}")
    if payload.get("request_surface_complete") is not True:
        errors.append("request_surface_not_complete")
    if payload.get("expected_request_count") != len(expected_pairs):
        errors.append("expected_request_count_mismatch")
    if payload.get("successful_request_count") != len(expected_pairs):
        errors.append("successful_request_count_mismatch")
    if (
        payload.get("failed_request_count") != 0
        or payload.get("empty_request_count") != 0
    ):
        errors.append("failed_or_incomplete_requests_present")
    if _safe_int(payload.get("generated_rows"), default=-1) != normalized_row_total:
        errors.append("generated_rows_request_total_mismatch")
    if payload.get("database_import_complete") is not True:
        errors.append("database_import_not_complete")
    csv_artifact = payload.get("csv_artifact")
    import_result = payload.get("import_result")
    if not isinstance(csv_artifact, dict):
        errors.append("csv_artifact_lineage_missing")
    if not isinstance(import_result, dict):
        errors.append("import_batch_lineage_missing")
    if isinstance(csv_artifact, dict) and isinstance(import_result, dict):
        csv_path_value = str(csv_artifact.get("path") or "")
        csv_path = Path(csv_path_value)
        if not csv_path_value or not csv_path.is_file():
            errors.append("csv_artifact_missing_on_disk")
        elif _file_hash(csv_path) != csv_artifact.get("sha256"):
            errors.append("csv_artifact_on_disk_hash_mismatch")
        if not csv_artifact.get("sha256") or import_result.get(
            "file_hash"
        ) != csv_artifact.get("sha256"):
            errors.append("csv_import_file_hash_mismatch")
        if import_result.get("batch_id") is None:
            errors.append("import_batch_id_missing")
        if (
            import_result.get("source_label") != SOURCE_LABEL
            or import_result.get("data_trust") != "trusted"
        ):
            errors.append("import_batch_source_or_trust_mismatch")
        if import_result.get("dataset_kind") != "intraday_csv":
            errors.append("import_batch_dataset_kind_mismatch")
        imported_db_path = Path(str(import_result.get("db_path") or ""))
        if not str(import_result.get("db_path") or "") or _resolved_path(
            imported_db_path
        ) != expected_database_identity.get("resolved_path"):
            errors.append("import_result_database_path_mismatch")
        csv_row_count = _safe_int(csv_artifact.get("row_count"), default=-1)
        if csv_path.is_file():
            errors.extend(
                _csv_request_lineage_errors(
                    csv_path,
                    chunk=chunk,
                    expected_pairs=expected_pairs,
                    indexed_requests=indexed,
                    expected_row_count=csv_row_count,
                )
            )
        if (
            csv_row_count <= 0
            or csv_row_count != normalized_row_total
            or csv_row_count != _safe_int(payload.get("generated_rows"), default=-1)
            or _safe_int(import_result.get("total_rows"), default=-1) != csv_row_count
            or _safe_int(import_result.get("rejected_rows"), default=-1) != 0
            or _safe_int(import_result.get("imported_rows"), default=-1)
            + _safe_int(import_result.get("duplicate_rows"), default=-1)
            != csv_row_count
        ):
            errors.append("import_batch_row_accounting_mismatch")
        if not import_result.get("input_path") or _resolved_path(
            Path(str(import_result.get("input_path")))
        ) != _resolved_path(csv_path):
            errors.append("import_result_input_path_mismatch")
        for day, symbol in sorted(expected_pairs):
            item = indexed.get((day, symbol))
            if item is None:
                continue
            lineage = item.get("artifact_lineage")
            if not isinstance(lineage, dict):
                errors.append(f"request_artifact_lineage_missing:{day}:{symbol}")
                continue
            if (
                lineage.get("csv_path") != csv_artifact.get("path")
                or lineage.get("csv_sha256") != csv_artifact.get("sha256")
                or lineage.get("csv_row_count") != csv_artifact.get("row_count")
            ):
                errors.append(f"request_csv_lineage_mismatch:{day}:{symbol}")
            if (
                lineage.get("import_batch_id") != import_result.get("batch_id")
                or lineage.get("import_file_hash") != import_result.get("file_hash")
                or lineage.get("import_source_label")
                != import_result.get("source_label")
                or lineage.get("import_data_trust") != import_result.get("data_trust")
                or lineage.get("database_import_complete") is not True
            ):
                errors.append(f"request_import_batch_lineage_mismatch:{day}:{symbol}")
            lineage_db_path = Path(str(lineage.get("import_db_path") or ""))
            if not str(lineage.get("import_db_path") or "") or _resolved_path(
                lineage_db_path
            ) != expected_database_identity.get("resolved_path"):
                errors.append(f"request_database_path_lineage_mismatch:{day}:{symbol}")
        if database_coverage is not None:
            if csv_path.is_file():
                errors.extend(
                    _csv_database_row_binding_errors(
                        csv_path,
                        chunk=chunk,
                        database_coverage=database_coverage,
                        symbols=symbols,
                    )
                )
            persisted_batch = _persisted_import_batch_for_lineage(
                database_coverage,
                import_result.get("batch_id"),
            )
            if not isinstance(persisted_batch, dict):
                errors.append("persisted_import_batch_missing")
            elif (
                persisted_batch.get("file_hash") != import_result.get("file_hash")
                or persisted_batch.get("source_label") != SOURCE_LABEL
                or persisted_batch.get("data_trust") != "trusted"
                or persisted_batch.get("dataset_kind") != "intraday_csv"
                or _safe_int(persisted_batch.get("total_rows"), default=-1)
                != _safe_int(import_result.get("total_rows"), default=-2)
                or _safe_int(persisted_batch.get("imported_rows"), default=-1)
                != _safe_int(import_result.get("imported_rows"), default=-2)
                or _safe_int(persisted_batch.get("duplicate_rows"), default=-1)
                != _safe_int(import_result.get("duplicate_rows"), default=-2)
                or _safe_int(persisted_batch.get("rejected_rows"), default=-1)
                != _safe_int(import_result.get("rejected_rows"), default=-2)
            ):
                errors.append("persisted_import_batch_lineage_mismatch")
            elif _resolved_path(
                Path(str(persisted_batch.get("input_path") or ""))
            ) != _resolved_path(Path(str(csv_artifact.get("path") or ""))):
                errors.append("persisted_import_batch_input_path_mismatch")
    completeness = payload.get("chain_completeness")
    if (
        not isinstance(completeness, dict)
        or completeness.get("standard_version") != CHAIN_COMPLETENESS_STANDARD_VERSION
        or completeness.get("required_scope") != CHAIN_COMPLETENESS_SCOPE
        or completeness.get("status") != "not_established"
        or completeness.get("standard_satisfied") is not False
        or completeness.get("selection_or_evaluation_authorized") is not False
    ):
        errors.append("chain_completeness_limitation_missing")
    return sorted(set(errors))


def revalidate_complete_manifest_database(
    manifest: dict[str, Any],
    plan: dict[str, Any],
    *,
    db_path: Path,
) -> list[str]:
    errors = manifest_validation_errors(manifest, plan, require_complete=True)
    actual_identity = _database_identity(db_path)
    errors.extend(_database_identity_errors(actual_identity, plan["database_identity"]))
    states = manifest.get("chunks") if isinstance(manifest.get("chunks"), dict) else {}
    symbols = tuple(str(symbol) for symbol in plan["symbols"])
    for chunk in plan["chunks"]:
        coverage = _coverage_for_chunk(
            db_path,
            chunk,
            symbols,
            expected_database_identity=plan["database_identity"],
        )
        if coverage.get("complete") is not True:
            errors.append(f"database_coverage_revalidation_failed:{chunk['chunk_id']}")
        state = states.get(chunk["chunk_id"]) if isinstance(states, dict) else None
        child_result = state.get("child_result") if isinstance(state, dict) else None
        if not isinstance(child_result, dict):
            errors.append(f"provider_request_lineage_missing:{chunk['chunk_id']}")
        else:
            errors.extend(
                f"{chunk['chunk_id']}:{item}"
                for item in _provider_lineage_errors(
                    child_result,
                    chunk=chunk,
                    symbols=symbols,
                    expected_database_identity=plan["database_identity"],
                    database_coverage=coverage,
                )
            )
    current_corpus_binding = manifest_database_corpus_binding(
        manifest, plan, db_path=db_path
    )
    errors.extend(
        f"manifest_corpus:{item}" for item in current_corpus_binding["errors"]
    )
    if manifest.get("downstream_corpus_binding") != current_corpus_binding:
        errors.append("persisted_downstream_corpus_binding_mismatch")
    return sorted(set(errors))


def _block(
    *,
    manifest: dict[str, Any],
    manifest_path: Path,
    state: dict[str, Any],
    state_status: str,
    manifest_status: str,
    message: str,
    log_path: Path,
) -> int:
    state["status"] = state_status
    state["last_error"] = message
    state["failed_at_utc"] = _utc_now_iso()
    manifest["status"] = manifest_status
    manifest["last_error"] = message
    _persist_manifest(manifest_path, manifest)
    _append_log(log_path, message)
    return 1


def run_imports(
    *,
    plan: dict[str, Any],
    manifest_path: Path,
    db_path: Path,
    lock_path: Path,
    log_path: Path,
    min_free_gb: float = MIN_FREE_GB,
    child_timeout_seconds: float = 6 * 3600,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    disk_usage: Callable[[Path], Any] = shutil.disk_usage,
    recover_stale_lock: bool = False,
    pid_is_live: Callable[[int], bool] = _pid_is_live,
) -> int:
    symbols = tuple(str(symbol) for symbol in plan["symbols"])
    preflight_blockers = list((plan.get("preflight") or {}).get("blockers") or [])
    if preflight_blockers:
        _append_log(
            log_path,
            "fresh-window preflight blocked before lock/manifest/provider/database mutation: "
            + json.dumps(plan["preflight"], sort_keys=True),
        )
        return 1
    with _exclusive_lock(
        lock_path,
        spec_hash=str(plan["spec_hash"]),
        recover_stale=recover_stale_lock,
        pid_is_live=pid_is_live,
    ):
        manifest = _load_or_create_manifest(manifest_path, plan)
        manifest["status"] = "in_progress"
        manifest.pop("last_error", None)
        _persist_manifest(manifest_path, manifest)
        _append_log(
            log_path, f"fresh-window resume start spec_hash={plan['spec_hash']}"
        )

        for chunk in plan["chunks"]:
            state = manifest["chunks"][chunk["chunk_id"]]
            try:
                before = _coverage_for_chunk(
                    db_path,
                    chunk,
                    symbols,
                    expected_database_identity=plan["database_identity"],
                )
            except sqlite3.Error as exc:
                return _block(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    state=state,
                    state_status="blocked_database_revalidation",
                    manifest_status="blocked_database_revalidation",
                    message=f"{chunk['chunk_id']} database revalidation failed: {type(exc).__name__}: {exc}",
                    log_path=log_path,
                )
            state["last_coverage"] = before
            state["last_verified_at_utc"] = _utc_now_iso()
            prior_child_result = (
                state.get("child_result")
                if isinstance(state.get("child_result"), dict)
                else None
            )
            prior_lineage_errors = (
                _provider_lineage_errors(
                    prior_child_result,
                    chunk=chunk,
                    symbols=symbols,
                    expected_database_identity=plan["database_identity"],
                    database_coverage=before,
                )
                if prior_child_result is not None
                else ["provider_request_lineage_missing"]
            )
            if before["complete"] and not prior_lineage_errors:
                state["status"] = "complete_verified"
                state["completion_source"] = "database_revalidation"
                state["provider_request_lineage"] = {
                    "status": "complete_verified",
                    "request_results_sha256": _canonical_hash(
                        prior_child_result.get("request_results") or []
                    ),
                }
                state.pop("last_error", None)
                _persist_manifest(manifest_path, manifest)
                _append_log(
                    log_path,
                    f"{chunk['chunk_id']} complete_verified from database; skipped",
                )
                continue

            volume_probes = dict(
                [
                    _storage_volume_probe(CSV_OUTPUT_DIR),
                    _storage_volume_probe(db_path.parent),
                ]
            )
            free_by_volume = {
                str(probe): float(disk_usage(probe).free) / 2**30
                for probe in volume_probes.values()
            }
            low_volumes = {
                probe: free_gb
                for probe, free_gb in free_by_volume.items()
                if free_gb < min_free_gb
            }
            if low_volumes:
                return _block(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    state=state,
                    state_status="blocked_low_disk",
                    manifest_status="blocked_low_disk",
                    message=(
                        f"{chunk['chunk_id']} blocked before import: storage reserve below {min_free_gb:.1f} GiB "
                        f"on {low_volumes}"
                    ),
                    log_path=log_path,
                )

            requested_symbols = list(symbols)
            state["status"] = "running"
            state["attempt_count"] = int(state.get("attempt_count") or 0) + 1
            state["attempt_started_at_utc"] = _utc_now_iso()
            state["requested_symbols"] = requested_symbols
            state["coverage_before_attempt"] = before
            state.pop("last_error", None)
            _persist_manifest(manifest_path, manifest)
            _append_log(
                log_path,
                f"{chunk['chunk_id']} attempt={state['attempt_count']} missing_pairs={before['missing_pair_count']} symbols={','.join(requested_symbols)}",
            )

            command = [
                sys.executable,
                str(IMPORT_SCRIPT),
                "--date-from",
                chunk["date_from"],
                "--date-to",
                chunk["date_to"],
                "--symbols",
                ",".join(requested_symbols),
                "--interval",
                chunk["interval"],
                "--start-time",
                chunk["start_time"],
                "--end-time",
                chunk["end_time"],
                "--min-dte",
                str(chunk["min_dte"]),
                "--max-dte",
                str(chunk["max_dte"]),
                "--right",
                chunk["right"],
                "--snapshot-kind",
                chunk["snapshot_kind"],
                "--source",
                SOURCE_LABEL,
                "--db-path",
                str(db_path),
                "--output-dir",
                str(CSV_OUTPUT_DIR),
                "--timeout",
                "60",
                "--require-complete",
                "--json",
            ]
            try:
                result = runner(
                    command,
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=child_timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                return _block(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    state=state,
                    state_status="blocked_child_timeout",
                    manifest_status="blocked_child_timeout",
                    message=f"{chunk['chunk_id']} child timed out after {exc.timeout} seconds",
                    log_path=log_path,
                )

            try:
                child_payload = (
                    json.loads(result.stdout) if result.stdout.strip() else {}
                )
            except json.JSONDecodeError:
                child_payload = {}
            state["child_result"] = _child_summary(child_payload)
            expected_child_request_count = len(requested_symbols) * len(
                chunk["market_dates"]
            )
            provider_lineage_errors = _provider_lineage_errors(
                state["child_result"],
                chunk=chunk,
                symbols=requested_symbols,
                expected_database_identity=plan["database_identity"],
            )
            if (
                result.returncode != 0
                or child_payload.get("status") != "request_surface_complete"
                or child_payload.get("request_surface_complete") is not True
                or child_payload.get("expected_request_count")
                != expected_child_request_count
                or child_payload.get("successful_request_count")
                != expected_child_request_count
                or child_payload.get("failed_request_count") != 0
                or child_payload.get("empty_request_count") != 0
                or provider_lineage_errors
            ):
                tail = (
                    (result.stderr or result.stdout or "no child output")
                    .strip()
                    .splitlines()
                )
                return _block(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    state=state,
                    state_status="blocked_import_incomplete",
                    manifest_status="blocked_import_incomplete",
                    message=(
                        f"{chunk['chunk_id']} importer failed closed: exit={result.returncode} "
                        f"lineage_errors={provider_lineage_errors} tail={tail[-1][:240] if tail else 'none'}"
                    ),
                    log_path=log_path,
                )

            try:
                after = _coverage_for_chunk(
                    db_path,
                    chunk,
                    symbols,
                    expected_database_identity=plan["database_identity"],
                )
            except sqlite3.Error as exc:
                return _block(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    state=state,
                    state_status="blocked_database_revalidation",
                    manifest_status="blocked_database_revalidation",
                    message=f"{chunk['chunk_id']} post-import revalidation failed: {type(exc).__name__}: {exc}",
                    log_path=log_path,
                )
            state["coverage_after_attempt"] = after
            state["last_coverage"] = after
            state["last_verified_at_utc"] = _utc_now_iso()
            if not after["complete"]:
                return _block(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    state=state,
                    state_status="blocked_coverage_incomplete",
                    manifest_status="blocked_coverage_incomplete",
                    message=f"{chunk['chunk_id']} request completed but database coverage still misses {after['missing_pair_count']} pairs",
                    log_path=log_path,
                )
            persisted_lineage_errors = _provider_lineage_errors(
                state["child_result"],
                chunk=chunk,
                symbols=symbols,
                expected_database_identity=plan["database_identity"],
                database_coverage=after,
            )
            if persisted_lineage_errors:
                return _block(
                    manifest=manifest,
                    manifest_path=manifest_path,
                    state=state,
                    state_status="blocked_database_lineage_mismatch",
                    manifest_status="blocked_database_lineage_mismatch",
                    message=f"{chunk['chunk_id']} database lineage mismatch: {persisted_lineage_errors}",
                    log_path=log_path,
                )
            state["status"] = "complete_verified"
            state["completion_source"] = "post_import_database_revalidation"
            state["provider_request_lineage"] = {
                "status": "complete_verified",
                "request_results_sha256": _canonical_hash(
                    state["child_result"].get("request_results") or []
                ),
            }
            state["completed_at_utc"] = _utc_now_iso()
            state.pop("last_error", None)
            _persist_manifest(manifest_path, manifest)
            _append_log(log_path, f"{chunk['chunk_id']} complete_verified after import")

        manifest["downstream_corpus_binding"] = manifest_database_corpus_binding(
            manifest,
            plan,
            db_path=db_path,
        )
        manifest["status"] = "complete_verified"
        manifest["completed_at_utc"] = _utc_now_iso()
        errors = manifest_validation_errors(manifest, plan, require_complete=True)
        errors.extend(
            revalidate_complete_manifest_database(manifest, plan, db_path=db_path)
        )
        if errors:
            manifest["status"] = "blocked_final_manifest_validation"
            manifest["completed_at_utc"] = None
            manifest["last_error"] = str(errors)
            _persist_manifest(manifest_path, manifest)
            _append_log(log_path, f"final manifest validation failed: {errors}")
            return 1
        _persist_manifest(manifest_path, manifest)
        _append_log(
            log_path,
            f"FRESH_WINDOW_IMPORTS_COMPLETE_VERIFIED spec_hash={plan['spec_hash']}",
        )
        return 0


def _record_crashed_manifest(
    manifest_path: Path, plan: dict[str, Any] | None, exc: Exception
) -> None:
    try:
        if manifest_path.exists():
            payload = json.loads(manifest_path.read_text(encoding="utf8"))
            if not isinstance(payload, dict):
                return
        elif plan is not None:
            payload = _new_manifest(plan)
        else:
            return
        if plan is not None and manifest_validation_errors(
            payload, plan, require_complete=False
        ):
            return
        payload["status"] = "crashed"
        payload["crashed_at_utc"] = _utc_now_iso()
        payload["last_error"] = f"{type(exc).__name__}: {exc}"
        for state in (payload.get("chunks") or {}).values():
            if isinstance(state, dict) and state.get("status") == "running":
                state["status"] = "crashed"
                state["last_error"] = payload["last_error"]
                state["failed_at_utc"] = payload["crashed_at_utc"]
        _persist_manifest(manifest_path, payload)
    except (OSError, ValueError, json.JSONDecodeError):
        return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resume the exact 2018-2021 fresh-window quote plan with database revalidation."
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Required acknowledgement that existing verified chunks may be reused.",
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--log-path", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--min-free-gb", type=float, default=MIN_FREE_GB)
    parser.add_argument("--child-timeout-seconds", type=float, default=6 * 3600)
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--recover-stale-lock",
        action="store_true",
        help="Explicitly recover a same-plan lock only after its recorded PID is confirmed not live.",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])
    if not args.resume:
        parser.error(
            "--resume is required; the manifest/database revalidation path is the only supported mode"
        )
    plan: dict[str, Any] | None = None
    json_fallback: dict[str, Any] | None = None
    try:
        plan = build_plan(db_path=args.db_path)
        return_code = run_imports(
            plan=plan,
            manifest_path=args.manifest,
            db_path=args.db_path,
            lock_path=args.lock_path,
            log_path=args.log_path,
            min_free_gb=float(args.min_free_gb),
            child_timeout_seconds=float(args.child_timeout_seconds),
            recover_stale_lock=bool(args.recover_stale_lock),
        )
        if return_code and plan.get("preflight", {}).get("blockers"):
            json_fallback = {
                "status": "blocked_preflight",
                "spec_hash": str(plan.get("spec_hash") or ""),
                "preflight": plan["preflight"],
            }
    except Exception as exc:  # pragma: no cover - operational boundary
        _record_crashed_manifest(args.manifest, plan, exc)
        _append_log(args.log_path, f"CRASHED {type(exc).__name__}: {exc}")
        json_fallback = {"status": "crashed", "error": f"{type(exc).__name__}: {exc}"}
        return 1
    finally:
        if args.json_output:
            if (
                json_fallback is not None
                and json_fallback.get("status") == "blocked_preflight"
            ):
                print(json.dumps(json_fallback, indent=2))
            elif args.manifest.exists():
                print(args.manifest.read_text(encoding="utf8"), end="")
            elif json_fallback is not None:
                print(json.dumps(json_fallback, indent=2))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
