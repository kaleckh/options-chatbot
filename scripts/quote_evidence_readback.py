from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from proof_contract import (  # noqa: E402
    PROOF_EVIDENCE_CONTRACT_VERSION,
    classify_quote_evidence,
)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        pieces = value.replace(";", ",").split(",")
    elif isinstance(value, Sequence):
        pieces = list(value)
    else:
        pieces = [value]
    return [str(item).strip() for item in pieces if str(item or "").strip()]


def _first_or_join(values: list[str]) -> str | None:
    if not values:
        return None
    return values[0] if len(values) == 1 else ",".join(values)


def quote_evidence_readback(
    *,
    snapshot_kind: str | None = None,
    data_trust: str | None = None,
    dataset_kind: str | None = None,
    source_label: str | None = None,
    source_labels: Sequence[str] | str | None = None,
    trust_levels: Sequence[str] | str | None = None,
    dataset_kinds: Sequence[str] | str | None = None,
    truth_lane: str | None = None,
    trusted_only: bool | None = None,
) -> dict[str, Any]:
    labels = _as_list(source_labels)
    if source_label:
        labels = [str(source_label).strip(), *labels]
    labels = sorted(dict.fromkeys(item for item in labels if item))

    trusts = _as_list(trust_levels)
    if data_trust:
        trusts = [str(data_trust).strip(), *trusts]
    trusts = sorted({item.lower() for item in trusts if item})
    if not trusts and trusted_only is not None:
        trusts = ["trusted"] if trusted_only else []

    kinds = _as_list(dataset_kinds)
    if dataset_kind:
        kinds = [str(dataset_kind).strip(), *kinds]
    kinds = sorted(dict.fromkeys(item for item in kinds if item))

    if len(trusts) > 1:
        return {
            "proof_contract_version": PROOF_EVIDENCE_CONTRACT_VERSION,
            "quote_evidence_class": "unknown",
            "quote_evidence_label": "Unclassified source",
            "quote_evidence_tone": "muted",
            "quote_snapshot_kind": snapshot_kind,
            "quote_data_trust": ",".join(trusts),
            "quote_source_label": _first_or_join(labels) or truth_lane,
            "quote_dataset_kind": _first_or_join(kinds),
            "production_proof_source_eligible": False,
            "quote_evidence_reason": "mixed_trust_levels",
        }

    source = {
        "snapshot_kind": snapshot_kind,
        "data_trust": trusts[0] if trusts else None,
        "dataset_kind": _first_or_join(kinds),
        "source_label": _first_or_join(labels),
        "truth_lane": truth_lane,
    }
    readback = classify_quote_evidence({"source_pick_snapshot": source})
    readback["proof_contract_version"] = PROOF_EVIDENCE_CONTRACT_VERSION
    readback["quote_evidence_reason"] = "contract_classified"
    return readback


def non_production_research_policy(
    *,
    record_class: str,
    quote_evidence: dict[str, Any],
    evidence_group: str = "research_backfill",
) -> dict[str, Any]:
    return {
        "proof_contract_version": PROOF_EVIDENCE_CONTRACT_VERSION,
        "record_class": record_class,
        "evidence_group": evidence_group,
        "production_proof": False,
        "research_learning": True,
        "quote_evidence": quote_evidence,
    }
