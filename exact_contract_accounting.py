from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


EXACT_CONTRACT_RESOLUTIONS = frozenset(
    {
        "exact_target_contract",
        "exact_archived_contract",
        "exact_contract",
    }
)
NEAREST_CONTRACT_RESOLUTION = "nearest_listed_contract"
UNKNOWN_CONTRACT_RESOLUTION = "unknown"


def normalize_contract_resolution(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return normalized or UNKNOWN_CONTRACT_RESOLUTION


def trade_contract_resolution(trade: dict[str, Any]) -> str:
    return normalize_contract_resolution(
        trade.get("entry_contract_resolution")
        or trade.get("contract_resolution")
    )


def is_exact_contract_resolution(value: Any) -> bool:
    return normalize_contract_resolution(value) in EXACT_CONTRACT_RESOLUTIONS


def is_exact_contract_trade(trade: dict[str, Any]) -> bool:
    return is_exact_contract_resolution(trade_contract_resolution(trade))


def priced_trades(trades: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(trade) for trade in trades if dict(trade).get("priced", True)]


def contract_resolution_counts(trades: Iterable[dict[str, Any]]) -> Counter[str]:
    return Counter(trade_contract_resolution(dict(trade)) for trade in trades)


def contract_resolution_accounting(
    trades: Iterable[dict[str, Any]],
    *,
    priced_trade_count: int | None = None,
    candidate_trade_count: int | None = None,
) -> dict[str, Any]:
    rows = [dict(trade) for trade in trades]
    counts = contract_resolution_counts(rows)
    priced_count = int(priced_trade_count if priced_trade_count is not None else len(rows))
    candidate_count = int(candidate_trade_count if candidate_trade_count is not None else priced_count)
    exact_count = sum(int(counts.get(resolution, 0) or 0) for resolution in EXACT_CONTRACT_RESOLUTIONS)
    nearest_count = int(counts.get(NEAREST_CONTRACT_RESOLUTION, 0) or 0)
    unresolved_count = max(candidate_count - exact_count - nearest_count, 0)
    normalized_counts = dict(sorted(counts.items()))
    normalized_counts.setdefault("exact_target_contract", 0)
    normalized_counts.setdefault("exact_archived_contract", 0)
    normalized_counts.setdefault("exact_contract", 0)
    normalized_counts.setdefault(NEAREST_CONTRACT_RESOLUTION, 0)
    normalized_counts["unresolved_candidates"] = unresolved_count
    return {
        "contract_resolution_counts": normalized_counts,
        "exact_contract_match_count": exact_count,
        "nearest_contract_match_count": nearest_count,
        "unresolved_contract_count": unresolved_count,
        "exact_contract_match_pct": round(exact_count / max(priced_count, 1) * 100.0, 1) if priced_count else 0.0,
        "nearest_contract_match_pct": round(nearest_count / max(priced_count, 1) * 100.0, 1) if priced_count else 0.0,
        "priced_trade_count": priced_count,
        "candidate_trade_count": candidate_count,
    }


def split_exact_and_research_trades(
    trades: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    exact: list[dict[str, Any]] = []
    research: list[dict[str, Any]] = []
    for trade in trades:
        row = dict(trade)
        if is_exact_contract_trade(row):
            exact.append(row)
        else:
            research.append(row)
    return exact, research
