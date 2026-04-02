from __future__ import annotations

import math
from typing import Any, Optional


CONTRACT_MULTIPLIER = 100
DEFAULT_COMMISSION_PER_CONTRACT_USD = 0.65
ELIGIBLE_STATUS = "eligible"
INELIGIBLE_STATUS = "ineligible"
PENDING_TRUTH_STATUS = "pending_truth"


def safe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
        if not math.isfinite(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    try:
        if value in (None, ""):
            return None
        parsed = int(value)
        return parsed
    except (TypeError, ValueError):
        return None


def normalize_quote_freshness_status(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if any(token in text for token in ("stale", "expired", "error", "missing", "unavailable")):
            return "stale"
        if text in {"fresh", "ready", "live", "current", "ok"}:
            return "fresh"
        if text in {"observed", "captured"}:
            return "observed"
        if text == "unknown":
            return "unknown"
    return "unknown"


def has_two_sided_quote(*, bid: Any, ask: Any) -> bool:
    bid_value = safe_float(bid)
    ask_value = safe_float(ask)
    return bool(
        bid_value is not None
        and ask_value is not None
        and bid_value > 0
        and ask_value > 0
        and ask_value >= bid_value
    )


def quote_midpoint(*, bid: Any, ask: Any) -> Optional[float]:
    bid_value = safe_float(bid)
    ask_value = safe_float(ask)
    if not has_two_sided_quote(bid=bid_value, ask=ask_value):
        return None
    return round((float(bid_value) + float(ask_value)) / 2.0, 4)


def display_quote_price(
    *,
    bid: Any = None,
    ask: Any = None,
    last: Any = None,
    model_price: Any = None,
    preferred: Any = None,
) -> tuple[Optional[float], Optional[str]]:
    preferred_value = safe_float(preferred)
    if preferred_value is not None and preferred_value > 0:
        return round(preferred_value, 4), "preferred"
    midpoint = quote_midpoint(bid=bid, ask=ask)
    if midpoint is not None and midpoint > 0:
        return midpoint, "mid"
    last_value = safe_float(last)
    if last_value is not None and last_value > 0:
        return round(last_value, 4), "last"
    model_value = safe_float(model_price)
    if model_value is not None and model_value > 0:
        return round(model_value, 4), "model"
    return None, None


def commission_total_usd(
    *,
    contracts: Any,
    sides: int = 1,
    commission_per_contract_usd: float = DEFAULT_COMMISSION_PER_CONTRACT_USD,
) -> float:
    contract_count = max(int(safe_int(contracts) or 0), 0)
    if contract_count <= 0 or int(sides) <= 0:
        return 0.0
    total = float(contract_count) * float(max(int(sides), 0)) * float(commission_per_contract_usd)
    return round(total, 4)


def resolve_execution_price(
    *,
    side: str,
    bid: Any = None,
    ask: Any = None,
    last: Any = None,
    model_price: Any = None,
    manual_price: Any = None,
    manual_basis: str | None = None,
    slippage_pct: float = 0.0,
    quote_freshness_status: Any = None,
    allow_research_fallback: bool = True,
) -> dict[str, Any]:
    normalized_side = str(side or "").strip().lower()
    if normalized_side not in {"entry", "exit"}:
        raise ValueError("side must be entry or exit")

    freshness = normalize_quote_freshness_status(quote_freshness_status)
    bid_value = safe_float(bid)
    ask_value = safe_float(ask)
    last_value = safe_float(last)
    model_value = safe_float(model_price)
    manual_value = safe_float(manual_price)
    two_sided = has_two_sided_quote(bid=bid_value, ask=ask_value)
    raw_execution_price: Optional[float] = None
    execution_basis: Optional[str] = None
    executable = False
    blockers: list[str] = []
    research_price: Optional[float] = None
    research_basis: Optional[str] = None

    if manual_value is not None and manual_value > 0:
        raw_execution_price = manual_value
        execution_basis = str(manual_basis or "manual").strip() or "manual"
        executable = True
        freshness = "observed"
    elif two_sided and freshness != "stale":
        raw_execution_price = ask_value if normalized_side == "entry" else bid_value
        execution_basis = "ask" if normalized_side == "entry" else "bid"
        executable = raw_execution_price is not None and raw_execution_price > 0
        if freshness == "unknown":
            freshness = "fresh"
    else:
        if freshness == "stale":
            blockers.append("stale_quote_freshness")
        elif freshness == "unknown":
            blockers.append("unknown_quote_freshness")
        if normalized_side == "entry":
            blockers.append("missing_executable_entry_quote")
        else:
            blockers.append("missing_executable_exit_quote")
        if allow_research_fallback:
            if last_value is not None and last_value > 0:
                research_price = round(last_value, 4)
                research_basis = "last"
            elif model_value is not None and model_value > 0:
                research_price = round(model_value, 4)
                research_basis = "model"
            if research_basis:
                blockers.append(f"research_only_quote_basis:{research_basis}")

    execution_price = None
    if raw_execution_price is not None and raw_execution_price > 0:
        slippage = float(slippage_pct or 0.0) / 100.0
        if normalized_side == "entry":
            adjusted = raw_execution_price * (1.0 + slippage)
        else:
            adjusted = raw_execution_price * max(0.0, 1.0 - slippage)
        execution_price = round(max(adjusted, 0.0001), 4)

    display_price, display_basis = display_quote_price(
        bid=bid_value,
        ask=ask_value,
        last=last_value,
        model_price=model_value,
        preferred=research_price,
    )
    if display_basis == "preferred":
        display_basis = research_basis

    return {
        "execution_price": execution_price,
        "execution_basis": execution_basis,
        "executable": executable,
        "quote_freshness_status": freshness,
        "blockers": blockers,
        "research_price": research_price,
        "research_basis": research_basis,
        "display_price": display_price,
        "display_basis": display_basis,
        "bid": bid_value,
        "ask": ask_value,
        "last": last_value,
        "model_price": model_value,
    }


def position_pnl_snapshot(
    *,
    entry_execution_price: Any,
    exit_execution_price: Any,
    contracts: Any = 1,
    entry_fee_total_usd: Any = 0.0,
    exit_fee_total_usd: Any = 0.0,
    contract_multiplier: int = CONTRACT_MULTIPLIER,
) -> dict[str, Optional[float]]:
    entry_price = safe_float(entry_execution_price)
    exit_price = safe_float(exit_execution_price)
    contract_count = max(int(safe_int(contracts) or 0), 0)
    if entry_price is None or entry_price <= 0 or exit_price is None or contract_count <= 0:
        fee_total = round(float(safe_float(entry_fee_total_usd) or 0.0) + float(safe_float(exit_fee_total_usd) or 0.0), 4)
        return {
            "gross_pnl_usd": None,
            "net_pnl_usd": None,
            "gross_pnl_pct": None,
            "net_pnl_pct": None,
            "fee_total_usd": fee_total,
        }

    gross_pnl_usd = (float(exit_price) - float(entry_price)) * int(contract_multiplier) * contract_count
    fee_total_usd = float(safe_float(entry_fee_total_usd) or 0.0) + float(safe_float(exit_fee_total_usd) or 0.0)
    net_pnl_usd = gross_pnl_usd - fee_total_usd
    capital_at_risk_usd = float(entry_price) * int(contract_multiplier) * contract_count
    gross_pnl_pct = (gross_pnl_usd / capital_at_risk_usd) * 100.0 if capital_at_risk_usd > 0 else None
    net_pnl_pct = (net_pnl_usd / capital_at_risk_usd) * 100.0 if capital_at_risk_usd > 0 else None
    return {
        "gross_pnl_usd": round(gross_pnl_usd, 4),
        "net_pnl_usd": round(net_pnl_usd, 4),
        "gross_pnl_pct": round(gross_pnl_pct, 4) if gross_pnl_pct is not None else None,
        "net_pnl_pct": round(net_pnl_pct, 4) if net_pnl_pct is not None else None,
        "fee_total_usd": round(fee_total_usd, 4),
    }


def scan_profitability_assessment(
    *,
    contract_symbol: Any,
    promotion_class: Any,
    selection_source: Any,
    entry_execution_price: Any,
    quote_freshness_status: Any,
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    promotion = str(promotion_class or "").strip().lower()
    selection = str(selection_source or "").strip().lower()
    freshness = normalize_quote_freshness_status(quote_freshness_status)

    if not str(contract_symbol or "").strip():
        blockers.append("missing_exact_contract")
    if promotion != "promotable_exact_contract":
        blockers.append(f"promotion_class:{promotion or 'unknown'}")
    if selection != "live_chain_exact_contract":
        blockers.append(f"selection_source:{selection or 'unknown'}")
    if safe_float(entry_execution_price) is None:
        blockers.append("missing_executable_entry_quote")
    if freshness == "stale":
        blockers.append("stale_quote_freshness")
    elif freshness == "unknown":
        blockers.append("unknown_quote_freshness")

    return (ELIGIBLE_STATUS if not blockers else INELIGIBLE_STATUS, blockers)


def executable_option_price(
    *,
    side: str,
    bid: Any = None,
    ask: Any = None,
    last: Any = None,
    model_price: Any = None,
    manual_price: Any = None,
    manual_basis: str | None = None,
    slippage_pct: float = 0.0,
    quote_freshness_status: Any = None,
    allow_research_fallback: bool = True,
) -> dict[str, Any]:
    result = resolve_execution_price(
        side=side,
        bid=bid,
        ask=ask,
        last=last,
        model_price=model_price,
        manual_price=manual_price,
        manual_basis=manual_basis,
        slippage_pct=slippage_pct,
        quote_freshness_status=quote_freshness_status,
        allow_research_fallback=allow_research_fallback,
    )
    result["profitability_blockers"] = list(result.get("blockers") or [])
    return result


def profitability_status_with_blockers(
    *,
    base_blockers: Any = None,
    contract_symbol: Any,
    quote_freshness_status: Any,
    promotion_class: Any = None,
    selection_source: Any = None,
    entry_execution_price: Any = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    for item in list(base_blockers or []):
        text = str(item or "").strip()
        if text and text not in blockers:
            blockers.append(text)
    if promotion_class is not None or selection_source is not None or entry_execution_price is not None:
        _eligibility, assessment_blockers = scan_profitability_assessment(
            contract_symbol=contract_symbol,
            promotion_class=promotion_class,
            selection_source=selection_source,
            entry_execution_price=entry_execution_price,
            quote_freshness_status=quote_freshness_status,
        )
        for item in assessment_blockers:
            if item not in blockers:
                blockers.append(item)
    else:
        freshness = normalize_quote_freshness_status(quote_freshness_status)
        if not str(contract_symbol or "").strip():
            blockers.append("missing_exact_contract")
        if freshness == "stale":
            blockers.append("stale_quote_freshness")
        elif freshness == "unknown":
            blockers.append("unknown_quote_freshness")
    return {
        "profitability_eligibility": ELIGIBLE_STATUS if not blockers else INELIGIBLE_STATUS,
        "profitability_blockers": blockers,
    }


def long_option_pnl(
    *,
    entry_execution_price: Any,
    exit_execution_price: Any,
    contracts: Any = 1,
    commission_per_contract_usd: float = DEFAULT_COMMISSION_PER_CONTRACT_USD,
    include_entry_fee: bool = True,
    include_exit_fee: bool = True,
) -> dict[str, Optional[float]]:
    return {
        **position_pnl_snapshot(
            entry_execution_price=entry_execution_price,
            exit_execution_price=exit_execution_price,
            contracts=contracts,
            entry_fee_total_usd=commission_total_usd(
                contracts=contracts,
                sides=1 if include_entry_fee else 0,
                commission_per_contract_usd=commission_per_contract_usd,
            ),
            exit_fee_total_usd=commission_total_usd(
                contracts=contracts,
                sides=1 if include_exit_fee else 0,
                commission_per_contract_usd=commission_per_contract_usd,
            ),
        ),
        "entry_fee_total_usd": commission_total_usd(
            contracts=contracts,
            sides=1 if include_entry_fee else 0,
            commission_per_contract_usd=commission_per_contract_usd,
        ),
        "exit_fee_total_usd": commission_total_usd(
            contracts=contracts,
            sides=1 if include_exit_fee else 0,
            commission_per_contract_usd=commission_per_contract_usd,
        ),
    }


def option_pnl_snapshot(
    *,
    entry_price: Any,
    exit_price: Any,
    contracts: Any = 1,
    entry_fee_total_usd: Any = 0.0,
    exit_fee_total_usd: Any = 0.0,
) -> dict[str, Optional[float]]:
    return position_pnl_snapshot(
        entry_execution_price=entry_price,
        exit_execution_price=exit_price,
        contracts=contracts,
        entry_fee_total_usd=entry_fee_total_usd,
        exit_fee_total_usd=exit_fee_total_usd,
    )


def option_pnl_snapshot(
    *,
    entry_execution_price: Any,
    exit_execution_price: Any,
    contracts: Any = 1,
    entry_fee_total_usd: Any = 0.0,
    exit_fee_total_usd: Any = 0.0,
    contract_multiplier: int = CONTRACT_MULTIPLIER,
) -> dict[str, Optional[float]]:
    return position_pnl_snapshot(
        entry_execution_price=entry_execution_price,
        exit_execution_price=exit_execution_price,
        contracts=contracts,
        entry_fee_total_usd=entry_fee_total_usd,
        exit_fee_total_usd=exit_fee_total_usd,
        contract_multiplier=contract_multiplier,
    )
