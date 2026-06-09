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
PROOF_EVIDENCE_CONTRACT_VERSION = int(PROOF_EVIDENCE_CONTRACT["version"])
PROOF_CLASSES = dict(PROOF_EVIDENCE_CONTRACT["proofClasses"])
FRONTEND_GROUPS_CONTRACT = dict(PROOF_EVIDENCE_CONTRACT["frontendGroups"])
RESEARCH_BACKFILL_CONTRACT = dict(PROOF_EVIDENCE_CONTRACT["researchBackfill"])
ENTRY_PROOF_CONTRACT = dict(PROOF_EVIDENCE_CONTRACT["entryProof"])
EXIT_BASIS_CONTRACT = dict(PROOF_EVIDENCE_CONTRACT["exitBasis"])
QUOTE_EVIDENCE_CONTRACT = dict(PROOF_EVIDENCE_CONTRACT.get("quoteEvidence") or {})
EVIDENCE_GROUPS = dict(FRONTEND_GROUPS_CONTRACT["groups"])
QUOTE_EVIDENCE_CLASSES = dict(QUOTE_EVIDENCE_CONTRACT.get("classes") or {})

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
QUOTE_TRUSTED_INTRADAY_TOKENS = tuple(QUOTE_EVIDENCE_CONTRACT.get("trustedIntradayTokens") or ())
QUOTE_DAILY_TOKENS = tuple(QUOTE_EVIDENCE_CONTRACT.get("dailyTokens") or ())
QUOTE_SYNTHETIC_TOKENS = tuple(QUOTE_EVIDENCE_CONTRACT.get("syntheticTokens") or ())
QUOTE_RESEARCH_TRUST_TOKENS = tuple(QUOTE_EVIDENCE_CONTRACT.get("researchTrustTokens") or ())
QUOTE_UNKNOWN_CLASS = str(QUOTE_EVIDENCE_CONTRACT.get("unknownClass") or "unknown")

LIVE_EXACT_EVIDENCE_GROUP = "live_exact"
MANUAL_EXACT_EVIDENCE_GROUP = "manual_exact"
HISTORICAL_PAPER_EVIDENCE_GROUP = "historical_paper"
RESEARCH_BACKFILL_EVIDENCE_GROUP = "research_backfill"
LIFECYCLE_ONLY_EVIDENCE_GROUP = "lifecycle_only"
PROOF_INELIGIBLE_EVIDENCE_GROUP = "proof_ineligible"
LEGACY_UNCLASSIFIED_EVIDENCE_GROUP = "legacy_unclassified"

TRUSTED_INTRADAY_OPRA_NBBO_QUOTE_CLASS = "trusted_intraday_opra_nbbo"
TRUSTED_DAILY_EOD_QUOTE_CLASS = "trusted_daily_eod"
RESEARCH_EOD_QUOTE_CLASS = "research_eod"
SYNTHETIC_RESEARCH_QUOTE_CLASS = "synthetic_research"


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


def _first_source_value(row: dict[str, Any], source: dict[str, Any], *fields: str) -> Any:
    for field in fields:
        value = source.get(field)
        if value not in (None, ""):
            return value
        value = row.get(field)
        if value not in (None, ""):
            return value
    return None


def _has_any_value(row: dict[str, Any], source: dict[str, Any], *fields: str) -> bool:
    return _first_value(row, source, *fields) not in (None, "")


def _row_is_closed(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    return _normalized(row_mapping.get("status")) == "closed" or bool(row_mapping.get("closed_at"))


def _group_contract(group_id: str) -> dict[str, Any]:
    return _mapping(EVIDENCE_GROUPS.get(group_id))


def _quote_class_contract(class_id: str) -> dict[str, Any]:
    return _mapping(QUOTE_EVIDENCE_CLASSES.get(class_id)) or _mapping(QUOTE_EVIDENCE_CLASSES.get(QUOTE_UNKNOWN_CLASS))


def _has_lifecycle_only_exit(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    review = _mapping(row_mapping.get("latest_review"))
    return (
        _row_is_closed(row_mapping)
        and _finite_float(row_mapping.get("exit_execution_price")) is None
        and _finite_float(row_mapping.get("exit_option_price")) is None
        and _finite_float(review.get("exit_execution_price")) is None
    )


def _has_historical_paper_marker(row: dict[str, Any]) -> bool:
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    return any(
        value not in (None, "")
        for value in (
            row_mapping.get("position_migration_id"),
            row_mapping.get("position_migrated_at_utc"),
            source.get("position_migration_id"),
            source.get("position_migrated_at_utc"),
        )
    )


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


def _row_evidence_group(row: dict[str, Any]) -> str:
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    proof_class = _normalized(row_mapping.get("proof_class") or source.get("proof_class"))

    if _has_lifecycle_only_exit(row_mapping):
        return LIFECYCLE_ONLY_EVIDENCE_GROUP
    if _has_historical_paper_marker(row_mapping):
        return HISTORICAL_PAPER_EVIDENCE_GROUP
    if row_has_research_backfill_marker(row_mapping):
        return RESEARCH_BACKFILL_EVIDENCE_GROUP
    if source.get("comparable_contract") or row_mapping.get("comparable_contract") or source.get("approximation_only"):
        return PROOF_INELIGIBLE_EVIDENCE_GROUP
    if proof_class == MANUAL_BROKER_EXACT_PROOF_CLASS:
        return MANUAL_EXACT_EVIDENCE_GROUP
    if proof_class == INELIGIBLE_PROOF_CLASS or row_mapping.get("proof_eligible") is False:
        return PROOF_INELIGIBLE_EVIDENCE_GROUP
    if proof_class == LIVE_SCAN_EXACT_PROOF_CLASS:
        return (
            LIVE_EXACT_EVIDENCE_GROUP
            if row_counts_as_production_proof(row_mapping)
            else PROOF_INELIGIBLE_EVIDENCE_GROUP
        )
    return LEGACY_UNCLASSIFIED_EVIDENCE_GROUP


def classify_row_evidence(row: dict[str, Any], *, record_class: str = "tracked_position") -> dict[str, Any]:
    row_mapping = _mapping(row)
    group_id = _row_evidence_group(row_mapping)
    group = _group_contract(group_id)
    tracked_position = record_class == "tracked_position"
    production_proof = bool(tracked_position and row_counts_as_production_proof(row_mapping))
    truth_grade_closed = bool(tracked_position and row_counts_as_proof_grade_exact_closed(row_mapping))
    realized_pnl_closed = bool(
        tracked_position
        and _row_is_closed(row_mapping)
        and row_has_trusted_executable_exit(row_mapping)
        and row_has_calculable_realized_pnl(row_mapping)
    )
    return {
        "proof_contract_version": PROOF_EVIDENCE_CONTRACT_VERSION,
        "record_class": record_class,
        "evidence_group": group_id,
        "evidence_label": str(group.get("label") or group_id),
        "evidence_tone": str(group.get("tone") or "muted"),
        "production_proof": production_proof,
        "truth_grade_closed": truth_grade_closed,
        "realized_pnl_closed": realized_pnl_closed,
        "raw_exact_contract": row_has_raw_exact_contract(row_mapping),
        "research_learning": bool(group.get("researchLearning")),
    }


def _quote_evidence_values(row: dict[str, Any], source: dict[str, Any]) -> list[str]:
    fields = (
        "snapshot_kind",
        "quote_snapshot_kind",
        "dataset_kind",
        "quote_dataset_kind",
        "data_trust",
        "quote_data_trust",
        "source_label",
        "truth_source",
        "truth_lane",
        "pricing_evidence_class",
        "profitability_evidence_class",
        "market_data_source",
        "options_market_data_source",
        "options_data_source",
        "quote_source",
        "data_source",
    )
    values = [
        _normalized(row.get(field))
        for field in fields
    ] + [
        _normalized(source.get(field))
        for field in fields
    ]
    return [value for value in values if value]


def _values_have_any_token(values: list[str], tokens: tuple[str, ...]) -> bool:
    return any(any(token in value for token in tokens) for value in values)


def classify_quote_evidence(row: dict[str, Any]) -> dict[str, Any]:
    row_mapping = _mapping(row)
    source = _source_snapshot(row_mapping)
    snapshot_kind = _normalized(
        _first_source_value(row_mapping, source, "snapshot_kind", "quote_snapshot_kind")
    )
    data_trust = _normalized(_first_source_value(row_mapping, source, "data_trust", "quote_data_trust"))
    dataset_kind = _normalized(
        _first_source_value(row_mapping, source, "dataset_kind", "quote_dataset_kind")
    )
    source_label = str(
        _first_source_value(
            row_mapping,
            source,
            "source_label",
            "proof_source_label",
            "options_data_source",
            "options_market_data_source",
            "market_data_source",
            "quote_source",
            "data_source",
            "truth_source",
            "truth_lane",
        )
        or ""
    ).strip()
    values = _quote_evidence_values(row_mapping, source)
    daily = snapshot_kind in {"daily", "daily_eod", "eod"} or _values_have_any_token(values, QUOTE_DAILY_TOKENS)
    synthetic = data_trust == "synthetic" or _values_have_any_token(values, QUOTE_SYNTHETIC_TOKENS)
    research = data_trust == "research" or _values_have_any_token(values, QUOTE_RESEARCH_TRUST_TOKENS)
    trusted = data_trust == "trusted" or not data_trust
    trusted_intraday = (
        not daily
        and trusted
        and _values_have_any_token(values, QUOTE_TRUSTED_INTRADAY_TOKENS)
    )

    if synthetic:
        class_id = SYNTHETIC_RESEARCH_QUOTE_CLASS
    elif daily and research:
        class_id = RESEARCH_EOD_QUOTE_CLASS
    elif daily and trusted:
        class_id = TRUSTED_DAILY_EOD_QUOTE_CLASS
    elif trusted_intraday:
        class_id = TRUSTED_INTRADAY_OPRA_NBBO_QUOTE_CLASS
    else:
        class_id = QUOTE_UNKNOWN_CLASS

    quote_class = _quote_class_contract(class_id)
    inferred_snapshot_kind = snapshot_kind or quote_class.get("snapshotKind")
    inferred_data_trust = data_trust or quote_class.get("dataTrust")
    return {
        "quote_evidence_class": class_id,
        "quote_evidence_label": str(quote_class.get("label") or class_id),
        "quote_evidence_tone": str(quote_class.get("tone") or "muted"),
        "quote_snapshot_kind": inferred_snapshot_kind,
        "quote_data_trust": inferred_data_trust,
        "quote_source_label": source_label or None,
        "quote_dataset_kind": dataset_kind or None,
        "production_proof_source_eligible": bool(quote_class.get("productionProofSourceEligible")),
    }
