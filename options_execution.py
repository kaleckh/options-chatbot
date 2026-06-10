from __future__ import annotations

import math
from typing import Any, Optional


CONTRACT_MULTIPLIER = 100
DEFAULT_COMMISSION_PER_CONTRACT_USD = 0.65
DEFAULT_SLIPPAGE_PCT = 1.0
ELIGIBLE_STATUS = "eligible"
INELIGIBLE_STATUS = "ineligible"
PENDING_TRUTH_STATUS = "pending_truth"


def safe_float(value: Any) -> Optional[float]:
    try:
        if isinstance(value, bool) or value in (None, ""):
            return None
        parsed = float(value)
        if not math.isfinite(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> Optional[int]:
    try:
        if isinstance(value, bool) or value in (None, ""):
            return None
        parsed = int(value)
        return parsed
    except (TypeError, ValueError):
        return None


def normalize_quote_freshness_status(*values: Any) -> str:
    has_fresh = False
    has_observed = False
    has_unknown = False
    for value in values:
        text = str(value or "").strip().lower()
        if not text:
            continue
        if any(token in text for token in ("stale", "expired", "error", "missing", "unavailable")):
            return "stale"
        if text in {"fresh", "ready", "live", "current", "ok"}:
            has_fresh = True
        elif text in {"observed", "captured"}:
            has_observed = True
        else:
            has_unknown = True
    if has_unknown:
        return "unknown"
    if has_fresh:
        return "fresh"
    if has_observed:
        return "observed"
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


def _net_return_pct(
    *,
    gross_pnl_usd: float,
    fee_total_usd: float,
    capital_at_risk_usd: float,
) -> Optional[float]:
    if capital_at_risk_usd <= 0:
        return None
    total_cost_basis = capital_at_risk_usd + max(float(fee_total_usd), 0.0)
    if total_cost_basis <= 0:
        return None
    net_pnl_pct = ((float(gross_pnl_usd) - float(fee_total_usd)) / total_cost_basis) * 100.0
    return max(net_pnl_pct, -100.0)


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
    elif two_sided and freshness in {"fresh", "observed"}:
        raw_execution_price = ask_value if normalized_side == "entry" else bid_value
        execution_basis = "ask" if normalized_side == "entry" else "bid"
        executable = raw_execution_price is not None and raw_execution_price > 0
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
    net_pnl_pct = _net_return_pct(
        gross_pnl_usd=gross_pnl_usd,
        fee_total_usd=fee_total_usd,
        capital_at_risk_usd=capital_at_risk_usd,
    )
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


def scan_profitability_assessment_lenient(
    *,
    contract_symbol: Any,
    promotion_class: Any,
    selection_source: Any,
    entry_execution_price: Any,
    quote_freshness_status: Any,
) -> tuple[str, list[str], float]:
    """
    Deprecated compatibility wrapper for older callers.

    Stale, unknown, or research-only quote evidence fails closed with weight 0.
    """
    status, blockers = scan_profitability_assessment(
        contract_symbol=contract_symbol,
        promotion_class=promotion_class,
        selection_source=selection_source,
        entry_execution_price=entry_execution_price,
        quote_freshness_status=quote_freshness_status,
    )
    if not blockers:
        return ELIGIBLE_STATUS, blockers, 1.0
    return INELIGIBLE_STATUS, blockers, 0.0

    # Non-critical blockers that allow partial evidence credit
    non_critical = {
        "stale_quote_freshness",
        "unknown_quote_freshness",
    }
    critical_blockers = [b for b in blockers if b not in non_critical and not b.startswith("research_only_quote_basis:")]
    if not critical_blockers:
        # Only non-critical issues — count at 50% weight
        return INELIGIBLE_STATUS, blockers, 0.0
    return INELIGIBLE_STATUS, blockers, 0.0


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


def executable_vertical_spread_entry(
    *,
    long_leg: dict[str, Any] | None,
    short_leg: dict[str, Any] | None,
    slippage_pct: float = 0.0,
    quote_freshness_status: Any = None,
) -> dict[str, Any]:
    """Executable debit for opening a vertical debit spread.

    Entry execution buys the long leg at ask and sells the short leg at bid.
    Mid/net debit remains useful for display, but it is not executable.
    """
    long_leg = long_leg or {}
    short_leg = short_leg or {}
    freshness = normalize_quote_freshness_status(
        quote_freshness_status,
        long_leg.get("option_chain_status"),
        short_leg.get("option_chain_status"),
        long_leg.get("options_snapshot_status"),
        short_leg.get("options_snapshot_status"),
    )
    long_ask = safe_float(long_leg.get("ask"))
    short_bid = safe_float(short_leg.get("bid"))
    blockers: list[str] = []

    if freshness == "stale":
        blockers.append("stale_quote_freshness")
    elif freshness == "unknown":
        blockers.append("unknown_quote_freshness")
    if long_ask is None or long_ask <= 0:
        blockers.append("missing_long_leg_ask")
    if short_bid is None or short_bid <= 0:
        blockers.append("missing_short_leg_bid")

    execution_price: Optional[float] = None
    executable = False
    if not blockers:
        raw_debit = float(long_ask) - float(short_bid)
        if raw_debit <= 0:
            blockers.append("non_positive_spread_entry_debit")
        else:
            slippage = float(slippage_pct or 0.0) / 100.0
            execution_price = round(raw_debit * (1.0 + slippage), 4)
            executable = True

    long_mid = quote_midpoint(bid=long_leg.get("bid"), ask=long_leg.get("ask"))
    short_mid = quote_midpoint(bid=short_leg.get("bid"), ask=short_leg.get("ask"))
    display_price: Optional[float] = None
    display_basis: Optional[str] = None
    if long_mid is not None and short_mid is not None:
        display_price = round(float(long_mid) - float(short_mid), 4)
        display_basis = "spread_mid"
    else:
        long_display, long_basis = display_quote_price(
            bid=long_leg.get("bid"),
            ask=long_leg.get("ask"),
            last=long_leg.get("last"),
            model_price=long_leg.get("model_price"),
            preferred=long_leg.get("premium"),
        )
        short_display, short_basis = display_quote_price(
            bid=short_leg.get("bid"),
            ask=short_leg.get("ask"),
            last=short_leg.get("last"),
            model_price=short_leg.get("model_price"),
            preferred=short_leg.get("premium"),
        )
        if long_display is not None and short_display is not None:
            display_price = round(float(long_display) - float(short_display), 4)
            display_basis = f"spread_{long_basis or 'unknown'}_{short_basis or 'unknown'}"

    return {
        "execution_price": execution_price,
        "execution_basis": "spread_ask_bid" if executable else None,
        "executable": executable,
        "quote_freshness_status": freshness,
        "blockers": blockers,
        "profitability_blockers": list(blockers),
        "display_price": display_price if display_price is None else round(max(float(display_price), 0.0), 4),
        "display_basis": display_basis,
        "long_ask": long_ask,
        "short_bid": short_bid,
    }


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
    entry_execution_price: Any = None,
    exit_execution_price: Any = None,
    entry_price: Any = None,
    exit_price: Any = None,
    contracts: Any = 1,
    entry_fee_total_usd: Any = 0.0,
    exit_fee_total_usd: Any = 0.0,
    contract_multiplier: int = CONTRACT_MULTIPLIER,
) -> dict[str, Optional[float]]:
    return position_pnl_snapshot(
        entry_execution_price=entry_execution_price if entry_execution_price is not None else entry_price,
        exit_execution_price=exit_execution_price if exit_execution_price is not None else exit_price,
        contracts=contracts,
        entry_fee_total_usd=entry_fee_total_usd,
        exit_fee_total_usd=exit_fee_total_usd,
        contract_multiplier=contract_multiplier,
    )


def vertical_spread_pnl(
    *,
    long_entry_price: Any,
    long_exit_price: Any,
    short_entry_price: Any,
    short_exit_price: Any,
    contracts: Any = 1,
    commission_per_contract_usd: float = DEFAULT_COMMISSION_PER_CONTRACT_USD,
    include_entry_fee: bool = True,
    include_exit_fee: bool = True,
    spread_width: Any = None,
    close_as_single_order: bool = False,
) -> dict[str, Optional[float]]:
    """
    P&L for a vertical spread (bull call spread or bear put spread).

    A debit spread has two legs:
      - Long leg: buy to open, sell to close
      - Short leg: sell to open, buy to close

    Net debit (entry cost) = long_entry - short_entry
    Net exit value         = long_exit  - short_exit
    Gross P&L              = (net_exit - net_debit) * multiplier * contracts

    Fees: 4 transactions (open long, open short, close long, close short)
          = contracts * 4 * commission_per_contract_usd
    """
    l_entry = safe_float(long_entry_price)
    l_exit = safe_float(long_exit_price)
    s_entry = safe_float(short_entry_price)
    s_exit = safe_float(short_exit_price)
    contract_count = max(int(safe_int(contracts) or 0), 0)

    if (
        l_entry is None or l_entry <= 0
        or s_entry is None or s_entry < 0
        or l_exit is None
        or s_exit is None
        or contract_count <= 0
    ):
        return {
            "gross_pnl_usd": None,
            "net_pnl_usd": None,
            "gross_pnl_pct": None,
            "net_pnl_pct": None,
            "fee_total_usd": 0.0,
            "entry_fee_total_usd": 0.0,
            "exit_fee_total_usd": 0.0,
            "net_debit": None,
            "net_exit_value": None,
            "spread_width": safe_float(spread_width),
            "max_profit": None,
            "max_loss": None,
        }

    net_debit = float(l_entry) - float(s_entry)
    net_exit_value = float(l_exit) - float(s_exit)
    if net_debit <= 0:
        return {
            "gross_pnl_usd": None,
            "net_pnl_usd": None,
            "gross_pnl_pct": None,
            "net_pnl_pct": None,
            "fee_total_usd": 0.0,
            "entry_fee_total_usd": 0.0,
            "exit_fee_total_usd": 0.0,
            "net_debit": round(net_debit, 4),
            "net_exit_value": round(net_exit_value, 4),
            "spread_width": safe_float(spread_width),
            "max_profit": None,
            "max_loss": None,
        }

    gross_pnl_usd = (net_exit_value - net_debit) * CONTRACT_MULTIPLIER * contract_count

    # Fees: 2 legs on entry, 2 legs on exit = 4 sides total
    entry_sides = 2 if include_entry_fee else 0
    exit_sides = 2 if include_exit_fee else 0
    entry_fee = commission_total_usd(
        contracts=contracts, sides=entry_sides,
        commission_per_contract_usd=commission_per_contract_usd,
    )
    exit_fee = commission_total_usd(
        contracts=contracts, sides=exit_sides,
        commission_per_contract_usd=commission_per_contract_usd,
    )
    fee_total = entry_fee + exit_fee
    net_pnl_usd = gross_pnl_usd - fee_total

    # Capital at risk = net debit paid
    capital_at_risk = abs(net_debit) * CONTRACT_MULTIPLIER * contract_count
    gross_pnl_pct = (gross_pnl_usd / capital_at_risk * 100.0) if capital_at_risk > 0 else None
    net_pnl_pct = _net_return_pct(
        gross_pnl_usd=gross_pnl_usd,
        fee_total_usd=fee_total,
        capital_at_risk_usd=capital_at_risk,
    )

    width = safe_float(spread_width)
    max_profit = (float(width) - net_debit) if width is not None and width > 0 else None
    max_loss = net_debit if net_debit > 0 else None

    return {
        "gross_pnl_usd": round(gross_pnl_usd, 4),
        "net_pnl_usd": round(net_pnl_usd, 4),
        "gross_pnl_pct": round(gross_pnl_pct, 4) if gross_pnl_pct is not None else None,
        "net_pnl_pct": round(net_pnl_pct, 4) if net_pnl_pct is not None else None,
        "fee_total_usd": round(fee_total, 4),
        "entry_fee_total_usd": round(entry_fee, 4),
        "exit_fee_total_usd": round(exit_fee, 4),
        "net_debit": round(net_debit, 4),
        "net_exit_value": round(net_exit_value, 4),
        "spread_width": round(float(width), 4) if width is not None else None,
        "max_profit": round(max_profit, 4) if max_profit is not None else None,
        "max_loss": round(max_loss, 4) if max_loss is not None else None,
    }
