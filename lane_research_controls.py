from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any, Iterable


def _safe_float(value: Any) -> float | None:
    try:
        if isinstance(value, bool) or value in (None, ""):
            return None
        parsed = float(value)
        if parsed != parsed:
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except (TypeError, ValueError):
        return None


def _normalized_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _theme_map_from_ai_universe() -> dict[str, str]:
    try:
        from ai_commodity_universe import iter_ai_commodity_symbols

        return {
            _normalized_symbol(row.get("symbol")): str(row.get("primary_theme") or "").strip() or "unknown"
            for row in iter_ai_commodity_symbols()
            if _normalized_symbol(row.get("symbol"))
        }
    except Exception:
        return {}


def _record_theme(record: dict[str, Any], theme_map: dict[str, str]) -> str:
    for key in ("primary_theme", "theme", "sub_theme"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    tags = record.get("theme_tags")
    if isinstance(tags, list) and tags:
        value = str(tags[0] or "").strip()
        if value:
            return value
    symbol = _normalized_symbol(record.get("ticker") or record.get("symbol"))
    return theme_map.get(symbol) or "unknown"


USD_PNL_KEYS = ("pnl_dollars", "net_pnl_usd", "pnl_usd")
PCT_PNL_KEYS = ("pnl_pct", "net_pnl_pct")


def _record_pnl(record: dict[str, Any], *, allow_pct: bool = True) -> float:
    keys = USD_PNL_KEYS + (PCT_PNL_KEYS if allow_pct else ())
    for key in keys:
        value = _safe_float(record.get(key))
        if value is not None:
            return float(value)
    return 0.0


def _group_contribution(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "net_pnl": 0.0, "positive_pnl": 0.0})
    has_usd_pnl = any(any(_safe_float(row.get(pnl_key)) is not None for pnl_key in USD_PNL_KEYS) for row in rows)
    allow_pct = not has_usd_pnl
    total_positive = sum(max(_record_pnl(row, allow_pct=allow_pct), 0.0) for row in rows)
    for row in rows:
        label = str(row.get(key) or "unknown").strip() or "unknown"
        pnl = _record_pnl(row, allow_pct=allow_pct)
        grouped[label]["count"] += 1
        grouped[label]["net_pnl"] += pnl
        grouped[label]["positive_pnl"] += max(pnl, 0.0)
    result = []
    for label, item in grouped.items():
        positive_share = item["positive_pnl"] / total_positive if total_positive > 0 else 0.0
        result.append(
            {
                key: label,
                "count": int(item["count"]),
                "net_pnl": round(float(item["net_pnl"]), 4),
                "pnl_basis": "usd" if has_usd_pnl else "pct",
                "positive_pnl_share": round(float(positive_share), 4),
            }
        )
    result.sort(key=lambda item: (-float(item["positive_pnl_share"]), -abs(float(item["net_pnl"])), str(item[key])))
    return result


def build_event_macro_concentration_controls(
    records: Iterable[dict[str, Any]] | None,
    *,
    lane_id: str,
    max_symbol_profit_share: float = 0.35,
    max_theme_profit_share: float = 0.50,
    max_sector_profit_share: float = 0.60,
    event_window_days: int = 2,
) -> dict[str, Any]:
    rows = [dict(row) for row in list(records or []) if isinstance(row, dict)]
    theme_map = _theme_map_from_ai_universe()
    enriched: list[dict[str, Any]] = []
    event_risk_records: list[dict[str, Any]] = []
    missing_event_metadata = 0
    missing_macro_metadata = 0

    for row in rows:
        symbol = _normalized_symbol(row.get("ticker") or row.get("symbol"))
        entry_date = _parse_date(row.get("entry_date") or row.get("opened_at") or row.get("scan_date"))
        earnings_date = _parse_date(row.get("earnings_date") or row.get("next_earnings_date"))
        event_flag = bool(row.get("event_risk_flag") or row.get("corporate_action_flag"))
        event_window = None
        if entry_date is not None and earnings_date is not None:
            event_window = (earnings_date - entry_date).days
            if 0 <= event_window <= max(int(event_window_days), 0):
                event_flag = True
        if earnings_date is None and not row.get("event_risk_flag") and not row.get("corporate_action_flag"):
            missing_event_metadata += 1
        macro_regime = str(row.get("macro_regime") or row.get("market_regime") or "").strip().lower()
        if not macro_regime:
            macro_regime = "unknown"
            missing_macro_metadata += 1
        enriched_row = {
            **row,
            "symbol": symbol,
            "sector": str(row.get("sector") or "unknown").strip() or "unknown",
            "theme": _record_theme(row, theme_map),
            "macro_regime": macro_regime,
            "event_window_days": event_window,
            "event_risk_flag": event_flag,
        }
        enriched.append(enriched_row)
        if event_flag:
            event_risk_records.append(
                {
                    "symbol": symbol,
                    "entry_date": entry_date.isoformat() if entry_date else None,
                    "earnings_date": earnings_date.isoformat() if earnings_date else None,
                    "event_window_days": event_window,
                    "event_risk_flag": event_flag,
                }
            )

    by_symbol = _group_contribution(enriched, "symbol")
    by_sector = _group_contribution(enriched, "sector")
    by_theme = _group_contribution(enriched, "theme")
    by_macro = _group_contribution(enriched, "macro_regime")

    promotion_blockers: list[str] = []
    if not enriched:
        promotion_blockers.append("insufficient_records_for_research_controls")
    if missing_event_metadata:
        promotion_blockers.append("missing_event_metadata")
    if missing_macro_metadata:
        promotion_blockers.append("missing_macro_regime_metadata")
    if by_symbol and float(by_symbol[0]["positive_pnl_share"]) > float(max_symbol_profit_share):
        promotion_blockers.append("symbol_profit_concentration")
    if by_sector and float(by_sector[0]["positive_pnl_share"]) > float(max_sector_profit_share):
        promotion_blockers.append("sector_profit_concentration")
    if by_theme and float(by_theme[0]["positive_pnl_share"]) > float(max_theme_profit_share):
        promotion_blockers.append("theme_profit_concentration")

    return {
        "lane_id": lane_id,
        "policy": "research_only_no_production_gate_changes",
        "record_count": len(enriched),
        "event_controls": {
            "event_window_days": int(event_window_days),
            "event_risk_count": len(event_risk_records),
            "missing_event_metadata_count": missing_event_metadata,
            "event_risk_records": event_risk_records[:10],
        },
        "macro_controls": {
            "missing_macro_regime_count": missing_macro_metadata,
            "by_macro_regime": by_macro,
        },
        "concentration_controls": {
            "max_symbol_profit_share": float(max_symbol_profit_share),
            "max_sector_profit_share": float(max_sector_profit_share),
            "max_theme_profit_share": float(max_theme_profit_share),
            "by_symbol": by_symbol,
            "by_sector": by_sector,
            "by_theme": by_theme,
        },
        "promotion_blockers": sorted(set(promotion_blockers)),
        "promotion_allowed": not promotion_blockers,
    }
