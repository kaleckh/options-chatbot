from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT_DIR / "data" / "contracts" / "proof-evidence-contract.json"


def _load_contract() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


PROOF_EVIDENCE_CONTRACT = _load_contract()
PROOF_CLASSES = dict(PROOF_EVIDENCE_CONTRACT["proofClasses"])
RESEARCH_BACKFILL_CONTRACT = dict(PROOF_EVIDENCE_CONTRACT["researchBackfill"])
ENTRY_PROOF_CONTRACT = dict(PROOF_EVIDENCE_CONTRACT["entryProof"])
EXIT_BASIS_CONTRACT = dict(PROOF_EVIDENCE_CONTRACT["exitBasis"])

LIVE_SCAN_EXACT_PROOF_CLASS = str(PROOF_CLASSES["liveScanExact"])
MANUAL_BROKER_EXACT_PROOF_CLASS = str(PROOF_CLASSES["manualBrokerExact"])
INELIGIBLE_PROOF_CLASS = str(PROOF_CLASSES["ineligible"])

RESEARCH_BACKFILL_IDENTITY_FIELDS = tuple(RESEARCH_BACKFILL_CONTRACT["identityFields"])
RESEARCH_BACKFILL_TOKENS = tuple(RESEARCH_BACKFILL_CONTRACT["tokens"])
SCAN_RESEARCH_BACKFILL_MARKER_FIELDS = tuple(RESEARCH_BACKFILL_CONTRACT["scanMarkerFields"])
ROW_RESEARCH_BACKFILL_MARKER_FIELDS = tuple(RESEARCH_BACKFILL_CONTRACT["rowMarkerFields"])

REQUIRED_LIVE_SELECTION_SOURCE = str(ENTRY_PROOF_CONTRACT["requiredSelectionSource"])
REQUIRED_SOURCE_SCAN_LINEAGE_FIELDS = tuple(ENTRY_PROOF_CONTRACT["requiredLineageFields"])
TRUSTED_OPTIONS_SOURCE_LABELS = tuple(ENTRY_PROOF_CONTRACT["trustedOptionsSourceLabels"])
TRUSTED_OPTIONS_SOURCE_REQUIRED_TOKENS = tuple(ENTRY_PROOF_CONTRACT["trustedOptionsSourceRequiredTokens"])
PROOF_SOURCE_FIELDS = tuple(ENTRY_PROOF_CONTRACT["sourceFields"])
TRUSTED_ENTRY_BASIS_TOKENS = tuple(ENTRY_PROOF_CONTRACT["trustedEntryBasisTokens"])
UNTRUSTED_ENTRY_BASIS_TOKENS = tuple(ENTRY_PROOF_CONTRACT["untrustedEntryBasisTokens"])
ENTRY_PRICE_FIELDS = tuple(ENTRY_PROOF_CONTRACT["entryPriceFields"])
QUOTE_TIME_FIELDS = tuple(ENTRY_PROOF_CONTRACT["quoteTimeFields"])
QUOTE_FRESHNESS_FIELDS = tuple(ENTRY_PROOF_CONTRACT["quoteFreshnessFields"])
QUOTE_FRESHNESS_REQUIRED = bool(ENTRY_PROOF_CONTRACT.get("quoteFreshnessRequired"))
UNTRUSTED_QUOTE_FRESHNESS_TOKENS = tuple(ENTRY_PROOF_CONTRACT["untrustedQuoteFreshnessTokens"])

TRUSTED_EXIT_BASIS_TOKENS = tuple(EXIT_BASIS_CONTRACT["trustedTokens"])
UNTRUSTED_EXIT_BASIS_TOKENS = tuple(EXIT_BASIS_CONTRACT["untrustedTokens"])


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _finite_float(value: Any) -> float | None:
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _source_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    return _mapping(_mapping(row).get("source_pick_snapshot"))


def _entry_quote_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    snapshot = _mapping(row_mapping.get("entry_quote_snapshot"))
    if snapshot:
        return snapshot
    return _mapping(source.get("entry_quote_snapshot"))


def _first_value(row: dict[str, Any], source: dict[str, Any], *fields: str) -> Any:
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            return value
        value = source.get(field)
        if value not in (None, ""):
            return value
    return None


def _has_any_value(row: dict[str, Any], source: dict[str, Any], *fields: str) -> bool:
    return _first_value(row, source, *fields) not in (None, "")


def _row_is_closed(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    return _normalized(row_mapping.get("status")) == "closed" or bool(row_mapping.get("closed_at"))


def _has_research_identity_marker(record: dict[str, Any]) -> bool:
    if bool(record.get("research_only")):
        return True
    return any(record.get(field) for field in RESEARCH_BACKFILL_IDENTITY_FIELDS)


def _values_have_research_token(values: list[Any]) -> bool:
    return any(
        any(token in _normalized(value) for token in RESEARCH_BACKFILL_TOKENS)
        for value in values
    )


def mapping_has_research_backfill_marker(
    record: dict[str, Any],
    *,
    marker_fields: tuple[str, ...] = SCAN_RESEARCH_BACKFILL_MARKER_FIELDS,
) -> bool:
    if _has_research_identity_marker(record):
        return True
    return _values_have_research_token([record.get(field) for field in marker_fields])


def scan_pick_has_research_backfill_marker(scan_pick: dict[str, Any]) -> bool:
    return mapping_has_research_backfill_marker(_mapping(scan_pick))


def row_has_research_backfill_marker(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    if _has_research_identity_marker(row_mapping):
        return True
    if _has_research_identity_marker(source):
        return True
    row_values = [row_mapping.get(field) for field in ROW_RESEARCH_BACKFILL_MARKER_FIELDS]
    source_values = [source.get(field) for field in SCAN_RESEARCH_BACKFILL_MARKER_FIELDS]
    return _values_have_research_token(row_values + source_values)


def row_has_trusted_opra_source(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    values = [
        _normalized(row_mapping.get(field))
        for field in PROOF_SOURCE_FIELDS
    ] + [
        _normalized(source.get(field))
        for field in PROOF_SOURCE_FIELDS
    ]
    for value in values:
        if not value:
            continue
        if value in TRUSTED_OPTIONS_SOURCE_LABELS:
            return True
        if all(token in value for token in TRUSTED_OPTIONS_SOURCE_REQUIRED_TOKENS):
            return True
    return False


def row_has_verified_live_scan_lineage(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    if not all(_has_any_value(row_mapping, source, field) for field in REQUIRED_SOURCE_SCAN_LINEAGE_FIELDS):
        return False
    return bool(row_mapping.get("source_scan_lineage_verified") or source.get("source_scan_lineage_verified"))


def row_has_live_exact_selection_source(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    selection_source = _normalized(
        _first_value(row_mapping, source, "selection_source", "contract_selection_source")
    )
    return selection_source == REQUIRED_LIVE_SELECTION_SOURCE


def row_has_executable_entry(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    snapshot = _entry_quote_snapshot(row_mapping)
    entry_price = None
    for field in ENTRY_PRICE_FIELDS:
        entry_price = _finite_float(row_mapping.get(field))
        if entry_price is not None:
            break
        entry_price = _finite_float(source.get(field))
        if entry_price is not None:
            break
        entry_price = _finite_float(snapshot.get(field))
        if entry_price is not None:
            break
    if entry_price is None or entry_price <= 0:
        return False

    basis = _normalized(
        row_mapping.get("entry_execution_basis")
        or source.get("entry_execution_basis")
        or snapshot.get("entry_execution_basis")
    )
    if not basis:
        return False
    if any(token in basis for token in UNTRUSTED_ENTRY_BASIS_TOKENS):
        return False
    if not any(token in basis for token in TRUSTED_ENTRY_BASIS_TOKENS):
        return False

    quote_values = [row_mapping.get(field) for field in QUOTE_TIME_FIELDS]
    quote_values += [source.get(field) for field in QUOTE_TIME_FIELDS]
    quote_values += [
        snapshot.get("quote_time_et"),
        snapshot.get("quote_time_utc"),
        snapshot.get("captured_at_utc"),
    ]
    if not any(str(value or "").strip() for value in quote_values):
        return False

    freshness_values = [row_mapping.get(field) for field in QUOTE_FRESHNESS_FIELDS]
    freshness_values += [source.get(field) for field in QUOTE_FRESHNESS_FIELDS]
    freshness_values += [snapshot.get(field) for field in QUOTE_FRESHNESS_FIELDS]
    if QUOTE_FRESHNESS_REQUIRED and not any(str(value or "").strip() for value in freshness_values):
        return False
    return not any(
        any(token in _normalized(value) for token in UNTRUSTED_QUOTE_FRESHNESS_TOKENS)
        for value in freshness_values
    )


def row_has_trusted_executable_exit(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    review = _mapping(row_mapping.get("latest_review"))
    exit_price = (
        _finite_float(row_mapping.get("exit_execution_price"))
        if _finite_float(row_mapping.get("exit_execution_price")) is not None
        else _finite_float(row_mapping.get("exit_option_price"))
    )
    if exit_price is None:
        exit_price = _finite_float(review.get("exit_execution_price"))
    if exit_price is None:
        exit_price = _finite_float(review.get("current_option_price"))
    if exit_price is None:
        return False

    basis = _normalized(
        row_mapping.get("exit_execution_basis")
        or review.get("exit_execution_basis")
        or review.get("pricing_source")
        or row_mapping.get("exit_reason")
    )
    if not basis:
        return False
    if any(token in basis for token in UNTRUSTED_EXIT_BASIS_TOKENS):
        return False
    return any(token in basis for token in TRUSTED_EXIT_BASIS_TOKENS)


def row_has_calculable_realized_pnl(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    review = _mapping(row_mapping.get("latest_review"))
    for field in ("net_pnl_pct", "gross_pnl_pct"):
        if _finite_float(row_mapping.get(field)) is not None:
            return True
        if _finite_float(review.get(field)) is not None:
            return True
    entry_price = _finite_float(
        row_mapping.get("entry_execution_price")
        or row_mapping.get("entry_option_price")
        or _source_snapshot(row_mapping).get("entry_execution_price")
    )
    exit_price = _finite_float(row_mapping.get("exit_execution_price") or row_mapping.get("exit_option_price"))
    if exit_price is None:
        exit_price = _finite_float(review.get("exit_execution_price") or review.get("current_option_price"))
    return entry_price is not None and entry_price > 0 and exit_price is not None


def row_counts_as_production_proof(row: dict[str, Any]) -> bool:
    if row_has_research_backfill_marker(row):
        return False
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    proof_class = _normalized(row_mapping.get("proof_class") or source.get("proof_class"))
    if proof_class != LIVE_SCAN_EXACT_PROOF_CLASS or row_mapping.get("proof_eligible") is not True:
        return False
    if not row_has_raw_exact_contract(row_mapping):
        return False
    if not row_has_live_exact_selection_source(row_mapping):
        return False
    if not row_has_verified_live_scan_lineage(row_mapping):
        return False
    if not row_has_trusted_opra_source(row_mapping):
        return False
    if not row_has_executable_entry(row_mapping):
        return False
    if _row_is_closed(row_mapping):
        return row_has_trusted_executable_exit(row_mapping) and row_has_calculable_realized_pnl(row_mapping)
    return True


def row_has_raw_exact_contract(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    return bool(str(row_mapping.get("contract_symbol") or source.get("contract_symbol") or "").strip())


def row_counts_as_proof_grade_exact_closed(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    return (
        _row_is_closed(row_mapping)
        and row_has_raw_exact_contract(row_mapping)
        and row_counts_as_production_proof(row_mapping)
        and row_has_trusted_executable_exit(row_mapping)
        and row_has_calculable_realized_pnl(row_mapping)
    )
