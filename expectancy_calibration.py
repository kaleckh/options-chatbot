from __future__ import annotations

import json
import math
import os
import copy
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional


RESULTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wfo_results.json")

DEFAULT_SURFACE_MIN_TRADES = 5
DEFAULT_DIRECTION_BUCKET_SIZE = 10
DEFAULT_QUALITY_BUCKET_SIZE = 10
DEFAULT_TECH_BUCKET_SIZE = 10
DEFAULT_SHRINKAGE_TRADES = 5.0
DEFAULT_SPARSE_WARNING_TRADES = 5
_SURFACE_SOURCE_EXCLUDE_KEYS = {"trades", "equity_curve", "unpriced_trades"}
_SURFACE_PROVENANCE_KEYS = (
    "run_at",
    "mode",
    "profile",
    "source_profile",
    "lookback_years",
    "n_picks",
    "iv_adj",
    "pricing_lane",
    "playbook",
    "truth_source",
    "promotion_status",
    "quote_coverage_pct",
    "strategy_domain",
    "source_mode",
    "source_type",
    "source_label",
    "source_run_at",
    "source_lookback_years",
    "source_n_picks",
    "source_iv_adj",
    "source_pricing_lane",
    "source_playbook",
    "source_truth_source",
    "source_promotion_status",
    "source_quote_coverage_pct",
    "source_strategy_domain",
    "source_contract_selection_basis",
    "source_universe_filters",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _surface_source_metadata(source_metadata: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not source_metadata:
        return {}
    return {
        key: value
        for key, value in dict(source_metadata).items()
        if key not in _SURFACE_SOURCE_EXCLUDE_KEYS
    }


def _surface_provenance(surface: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not surface:
        return {}
    provenance = {key: surface.get(key) for key in _SURFACE_PROVENANCE_KEYS if key in surface}
    metadata = dict(surface.get("source_metadata") or {})
    if metadata:
        provenance["source_metadata"] = metadata
    return provenance


def normalized_market_regime(value: Any = None, spy_ret5: Any = None) -> str:
    if value is not None:
        text = str(value).strip().lower()
        if text in {"bull", "bullish"}:
            return "bullish"
        if text in {"bear", "bearish"}:
            return "bearish"
        if text in {"neutral", "sideways", "flat"}:
            return "neutral"
    spy_move = _safe_float(spy_ret5, 0.0)
    if spy_move <= -0.5:
        return "bearish"
    if spy_move >= 0.5:
        return "bullish"
    return "neutral"


def composite_market_regime_score(
    *,
    spy_ret5: float = 0.0,
    spy_ret20: float = 0.0,
    spy_above_sma50: bool = False,
    vix_level: float = 20.0,
) -> dict[str, Any]:
    """
    Composite regime score (0-100) using multiple timeframe signals.
    <30 bearish, 30-70 neutral, >70 bullish.
    """
    score = 0.0
    score += 25.0 if spy_ret5 > 0 else 0.0       # short-term momentum
    score += 25.0 if spy_ret20 > 0 else 0.0       # medium-term trend
    score += 30.0 if spy_above_sma50 else 0.0      # structural trend
    score += 20.0 if vix_level < 20 else (10.0 if vix_level < 25 else 0.0)  # vol environment
    if score < 30:
        regime = "bearish"
    elif score > 70:
        regime = "bullish"
    else:
        regime = "neutral"
    return {
        "regime": regime,
        "score": round(score, 1),
        "components": {
            "spy_ret5_bullish": spy_ret5 > 0,
            "spy_ret20_bullish": spy_ret20 > 0,
            "spy_above_sma50": spy_above_sma50,
            "vix_level": round(vix_level, 2),
        },
    }


def normalized_trade_direction(value: Any = None) -> str:
    text = str(value or "").strip().lower()
    if text in {"call", "calls", "c"}:
        return "call"
    if text in {"put", "puts", "p"}:
        return "put"
    return "unknown"


def score_bucket(score: Any, bucket_size: int = 10) -> str:
    value = _safe_float(score, 0.0)
    step = max(1, int(bucket_size))
    lo = max(0, min(100, int(value // step) * step))
    hi = min(100, lo + step - 1)
    if hi >= 100:
        return f"{lo:02d}-100"
    return f"{lo:02d}-{hi:02d}"


def direction_score_bucket(score: Any, bucket_size: int = DEFAULT_DIRECTION_BUCKET_SIZE) -> str:
    return score_bucket(score, bucket_size=bucket_size)


def quality_score_bucket(score: Any, bucket_size: int = DEFAULT_QUALITY_BUCKET_SIZE) -> str:
    return score_bucket(score, bucket_size=bucket_size)


def tech_score_bucket(score: Any, bucket_size: int = DEFAULT_TECH_BUCKET_SIZE) -> str:
    return score_bucket(score, bucket_size=bucket_size)


def _profit_factor(pnl_values: list[float]) -> float | None:
    if not pnl_values:
        return 0.0
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    if gross_loss <= 0:
        return None
    return round(gross_win / gross_loss, 2)


def _surface_level_definitions(include_tech_band: bool) -> tuple[list[dict[str, Any]], list[str]]:
    levels: list[dict[str, Any]] = [
        {
            "id": "overall",
            "label": "overall",
            "fields": [],
            "parent": None,
        },
        {
            "id": "direction",
            "label": "direction",
            "fields": ["direction"],
            "parent": "overall",
        },
        {
            "id": "regime_direction",
            "label": "regime + direction",
            "fields": ["market_regime", "direction"],
            "parent": "direction",
        },
        {
            "id": "direction_dir",
            "label": "direction + direction band",
            "fields": ["direction", "direction_band"],
            "parent": "direction",
        },
        {
            "id": "regime_direction_dir",
            "label": "regime + direction + direction band",
            "fields": ["market_regime", "direction", "direction_band"],
            "parent": "direction_dir",
        },
        {
            "id": "direction_dir_quality",
            "label": "direction + direction band + quality band",
            "fields": ["direction", "direction_band", "quality_band"],
            "parent": "direction_dir",
        },
        {
            "id": "regime_direction_dir_quality",
            "label": "regime + direction + direction band + quality band",
            "fields": ["market_regime", "direction", "direction_band", "quality_band"],
            "parent": "direction_dir_quality",
        },
    ]
    lookup_order = [
        "regime_direction_dir_quality",
        "direction_dir_quality",
        "regime_direction_dir",
        "direction_dir",
        "regime_direction",
        "direction",
        "overall",
    ]
    if include_tech_band:
        levels.append(
            {
                "id": "regime_direction_dir_quality_tech",
                "label": "regime + direction + direction band + quality band + tech band",
                "fields": ["market_regime", "direction", "direction_band", "quality_band", "tech_band"],
                "parent": "regime_direction_dir_quality",
            }
        )
        lookup_order.insert(0, "regime_direction_dir_quality_tech")
    return levels, lookup_order


def _group_key(fields: list[str], values: dict[str, Any]) -> str:
    if not fields:
        return "overall"
    return "|".join(str(values.get(field, "missing")) for field in fields)


def _summarize_group(
    trades: list[dict[str, Any]],
    *,
    fields: list[str],
    field_values: dict[str, Any],
    level_id: str,
) -> dict[str, Any]:
    pnl_values = [_safe_float(trade.get("pnl_pct"), 0.0) for trade in trades]
    win_rate = sum(1 for value in pnl_values if value > 0) / max(len(pnl_values), 1) * 100.0
    directional_hits = sum(1 for trade in trades if trade.get("directional_correct"))
    quality_values = [_safe_float(trade.get("quality_score"), 0.0) for trade in trades]
    direction_values = [_safe_float(trade.get("direction_score"), 0.0) for trade in trades]
    tech_values = [_safe_float(trade.get("tech_score"), 0.0) for trade in trades]
    raw_avg = sum(pnl_values) / max(len(pnl_values), 1)
    gross_win = sum(value for value in pnl_values if value > 0)
    gross_loss = abs(sum(value for value in pnl_values if value < 0))
    out = {
        "level": level_id,
        "group_key": _group_key(fields, field_values),
        "fields": list(fields),
        "field_values": dict(field_values),
        "market_regime": field_values.get("market_regime"),
        "direction": field_values.get("direction"),
        "direction_band": field_values.get("direction_band"),
        "quality_band": field_values.get("quality_band"),
        "tech_band": field_values.get("tech_band"),
        "trades": len(trades),
        "avg_pnl_pct_raw": round(raw_avg, 2),
        "avg_pnl_pct": round(raw_avg, 2),
        "win_rate_pct_raw": round(win_rate, 1),
        "win_rate_pct": round(win_rate, 1),
        "directional_accuracy_pct": round(directional_hits / max(len(trades), 1) * 100.0, 1),
        "profit_factor": _profit_factor(pnl_values),
        "no_loss_sample": bool(pnl_values and gross_loss <= 0 and gross_win > 0),
        "avg_quality_score": round(sum(quality_values) / max(len(quality_values), 1), 1),
        "avg_direction_score": round(sum(direction_values) / max(len(direction_values), 1), 1),
        "avg_tech_score": round(sum(tech_values) / max(len(tech_values), 1), 1),
        "pnl_std": round((sum((v - raw_avg) ** 2 for v in pnl_values) / max(len(pnl_values) - 1, 1)) ** 0.5, 2) if len(pnl_values) > 1 else 0.0,
        "ci_lower_95": round(raw_avg - 1.96 * ((sum((v - raw_avg) ** 2 for v in pnl_values) / max(len(pnl_values) - 1, 1)) ** 0.5) / max(len(pnl_values), 1) ** 0.5, 2) if len(pnl_values) > 1 else round(raw_avg, 2),
        "ci_upper_95": round(raw_avg + 1.96 * ((sum((v - raw_avg) ** 2 for v in pnl_values) / max(len(pnl_values) - 1, 1)) ** 0.5) / max(len(pnl_values), 1) ** 0.5, 2) if len(pnl_values) > 1 else round(raw_avg, 2),
    }
    return out


def _attach_shrinkage(
    nodes_by_level: dict[str, dict[str, dict[str, Any]]],
    levels: list[dict[str, Any]],
    *,
    shrinkage_trades: float,
    sparse_warning_trades: int,
) -> None:
    definitions = {level["id"]: level for level in levels}
    for level in levels:
        level_id = level["id"]
        parent_id = level.get("parent")
        for node in nodes_by_level.get(level_id, {}).values():
            raw_avg = _safe_float(node.get("avg_pnl_pct_raw"), 0.0)
            raw_win_rate = _safe_float(node.get("win_rate_pct_raw"), 0.0)
            if not parent_id:
                node["parent_level"] = None
                node["parent_group_key"] = None
                node["parent_avg_pnl_pct"] = None
                node["parent_win_rate_pct"] = None
                node["shrinkage_trades"] = float(shrinkage_trades)
                node["avg_pnl_pct"] = round(raw_avg, 2)
                node["win_rate_pct"] = round(raw_win_rate, 1)
                node["used_parent_shrinkage"] = False
                node["sparse_cohort"] = int(node.get("trades", 0) or 0) < int(sparse_warning_trades)
                continue

            parent_fields = definitions[parent_id]["fields"]
            parent_field_values = {field: node["field_values"].get(field) for field in parent_fields}
            parent_key = _group_key(parent_fields, parent_field_values)
            parent_node = (nodes_by_level.get(parent_id) or {}).get(parent_key)
            parent_avg = _safe_float(parent_node.get("avg_pnl_pct"), raw_avg) if parent_node else raw_avg
            parent_win_rate = _safe_float(parent_node.get("win_rate_pct"), raw_win_rate) if parent_node else raw_win_rate
            trades = float(node.get("trades", 0) or 0.0)
            shrink = float(shrinkage_trades)
            shrunk_avg = ((raw_avg * trades) + (parent_avg * shrink)) / max(trades + shrink, 1.0)
            shrunk_win_rate = ((raw_win_rate * trades) + (parent_win_rate * shrink)) / max(trades + shrink, 1.0)
            node["parent_level"] = parent_id
            node["parent_group_key"] = parent_key
            node["parent_avg_pnl_pct"] = round(parent_avg, 2)
            node["parent_win_rate_pct"] = round(parent_win_rate, 1)
            node["shrinkage_trades"] = float(shrinkage_trades)
            node["avg_pnl_pct"] = round(shrunk_avg, 2)
            node["win_rate_pct"] = round(shrunk_win_rate, 1)
            node["used_parent_shrinkage"] = abs(round(shrunk_avg, 6) - round(raw_avg, 6)) > 0.0
            node["sparse_cohort"] = int(node.get("trades", 0) or 0) < int(sparse_warning_trades)


def _level_density(
    level: dict[str, Any],
    nodes: dict[str, dict[str, Any]],
    *,
    total_trades: int,
    min_trades: int,
) -> dict[str, Any]:
    counts = [int(node.get("trades", 0) or 0) for node in nodes.values()]
    dense_counts = [count for count in counts if count >= int(min_trades)]
    dense_trade_coverage = sum(dense_counts)
    return {
        "level": level["id"],
        "label": level["label"],
        "fields": list(level["fields"]),
        "cohorts": len(counts),
        "dense_cohorts": len(dense_counts),
        "sparse_cohorts": len([count for count in counts if count < int(min_trades)]),
        "max_trades": max(counts) if counts else 0,
        "avg_trades_per_cohort": round(sum(counts) / max(len(counts), 1), 2),
        "dense_trade_coverage_pct": round(dense_trade_coverage / max(total_trades, 1) * 100.0, 1),
    }


def _surface_warnings(
    density_rows: list[dict[str, Any]],
    *,
    min_trades: int,
) -> list[str]:
    warnings: list[str] = []
    for row in density_rows:
        if row["cohorts"] == 0:
            warnings.append(f"{row['level']}: no cohorts were constructed.")
            continue
        if row["max_trades"] < int(min_trades):
            warnings.append(
                f"{row['level']}: no dense cohorts reached {int(min_trades)} trades "
                f"(max={row['max_trades']})."
            )
        elif row["dense_trade_coverage_pct"] < 40.0:
            warnings.append(
                f"{row['level']}: dense coverage is only {row['dense_trade_coverage_pct']:.1f}% "
                f"of replay trades."
            )
    return warnings


def _should_include_tech_band_from_counts(
    without_tech_counts: dict[str, int],
    with_tech_counts: dict[str, int],
    *,
    min_trades: int,
) -> bool:
    dense_without = sum(count for count in without_tech_counts.values() if count >= int(min_trades))
    dense_with = sum(count for count in with_tech_counts.values() if count >= int(min_trades))
    return dense_with > dense_without


def _summarize_group_from_stats(
    stats: dict[str, Any],
    *,
    fields: list[str],
    field_values: dict[str, Any],
    level_id: str,
) -> dict[str, Any]:
    trades = int(stats.get("trades", 0) or 0)
    pnl_sum = float(stats.get("pnl_sum", 0.0) or 0.0)
    gross_win = float(stats.get("gross_win", 0.0) or 0.0)
    gross_loss = float(stats.get("gross_loss", 0.0) or 0.0)
    win_count = int(stats.get("win_count", 0) or 0)
    quality_sum = float(stats.get("quality_sum", 0.0) or 0.0)
    direction_sum = float(stats.get("direction_sum", 0.0) or 0.0)
    tech_sum = float(stats.get("tech_sum", 0.0) or 0.0)
    raw_avg = pnl_sum / max(trades, 1)
    win_rate = win_count / max(trades, 1) * 100.0
    return {
        "level": level_id,
        "group_key": _group_key(fields, field_values),
        "fields": list(fields),
        "field_values": dict(field_values),
        "market_regime": field_values.get("market_regime"),
        "direction": field_values.get("direction"),
        "direction_band": field_values.get("direction_band"),
        "quality_band": field_values.get("quality_band"),
        "tech_band": field_values.get("tech_band"),
        "trades": trades,
        "avg_pnl_pct_raw": round(raw_avg, 2),
        "avg_pnl_pct": round(raw_avg, 2),
        "win_rate_pct_raw": round(win_rate, 1),
        "win_rate_pct": round(win_rate, 1),
        "directional_accuracy_pct": round(int(stats.get("directional_hits", 0) or 0) / max(trades, 1) * 100.0, 1),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "no_loss_sample": bool(trades and gross_loss <= 0 and gross_win > 0),
        "avg_quality_score": round(quality_sum / max(trades, 1), 1),
        "avg_direction_score": round(direction_sum / max(trades, 1), 1),
        "avg_tech_score": round(tech_sum / max(trades, 1), 1),
        "pnl_std": round(max(0.0, (float(stats.get("pnl_sq_sum", 0.0) or 0.0) / max(trades, 1) - raw_avg ** 2)) ** 0.5, 2) if trades > 1 else None,
        "ci_lower_95": round(raw_avg - 1.96 * max(0.0, (float(stats.get("pnl_sq_sum", 0.0) or 0.0) / max(trades, 1) - raw_avg ** 2)) ** 0.5 / max(trades, 1) ** 0.5, 2) if trades > 1 else None,
        "ci_upper_95": round(raw_avg + 1.96 * max(0.0, (float(stats.get("pnl_sq_sum", 0.0) or 0.0) / max(trades, 1) - raw_avg ** 2)) ** 0.5 / max(trades, 1) ** 0.5, 2) if trades > 1 else None,
    }


def _empty_group_stats(field_values: dict[str, Any]) -> dict[str, Any]:
    return {
        "trades": 0,
        "pnl_sum": 0.0,
        "gross_win": 0.0,
        "gross_loss": 0.0,
        "win_count": 0,
        "directional_hits": 0,
        "quality_sum": 0.0,
        "direction_sum": 0.0,
        "tech_sum": 0.0,
        "pnl_sq_sum": 0.0,
        "field_values": dict(field_values),
    }


class CalibrationAccumulator:
    def __init__(
        self,
        *,
        min_trades: int = DEFAULT_SURFACE_MIN_TRADES,
        bucket_size: int = DEFAULT_DIRECTION_BUCKET_SIZE,
        quality_bucket_size: int = DEFAULT_QUALITY_BUCKET_SIZE,
        tech_bucket_size: int = DEFAULT_TECH_BUCKET_SIZE,
        shrinkage_trades: float = DEFAULT_SHRINKAGE_TRADES,
        sparse_warning_trades: int = DEFAULT_SPARSE_WARNING_TRADES,
    ) -> None:
        self.min_trades = int(min_trades)
        self.bucket_size = int(bucket_size)
        self.quality_bucket_size = int(quality_bucket_size)
        self.tech_bucket_size = int(tech_bucket_size)
        self.shrinkage_trades = float(shrinkage_trades)
        self.sparse_warning_trades = int(sparse_warning_trades)
        self._total_trades = 0
        self._without_tech_counts: dict[str, int] = defaultdict(int)
        self._with_tech_counts: dict[str, int] = defaultdict(int)
        self._level_stats: dict[str, dict[str, dict[str, Any]]] = {}
        self._all_levels, self._lookup_order = _surface_level_definitions(True)
        self._snapshot_core_cache: Optional[dict[str, Any]] = None
        self._snapshot_core_cache_trade_count = -1

    @property
    def trade_count(self) -> int:
        return self._total_trades

    def add_trade(self, trade: dict[str, Any]) -> dict[str, Any]:
        normalized = _normalize_trade_for_surface(
            trade,
            direction_bucket_size=int(self.bucket_size),
            quality_bucket_size=int(self.quality_bucket_size),
            tech_bucket_size=int(self.tech_bucket_size),
        )
        self._total_trades += 1
        self._snapshot_core_cache = None
        self._snapshot_core_cache_trade_count = -1
        base_key = "|".join(
            [
                normalized.get("market_regime"),
                normalized.get("direction"),
                normalized.get("direction_band"),
                normalized.get("quality_band"),
            ]
        )
        tech_key = "|".join([base_key, normalized.get("tech_band")])
        self._without_tech_counts[base_key] += 1
        self._with_tech_counts[tech_key] += 1

        for level in self._all_levels:
            fields = list(level["fields"])
            key = _group_key(fields, normalized)
            level_nodes = self._level_stats.setdefault(level["id"], {})
            stats = level_nodes.get(key)
            if stats is None:
                field_values = {field: normalized.get(field) for field in fields} if fields else {}
                stats = _empty_group_stats(field_values)
                level_nodes[key] = stats
            stats["trades"] += 1
            pnl = _safe_float(normalized.get("pnl_pct"), 0.0)
            stats["pnl_sum"] += pnl
            stats["pnl_sq_sum"] = stats.get("pnl_sq_sum", 0.0) + pnl * pnl
            if pnl > 0:
                stats["gross_win"] += pnl
                stats["win_count"] += 1
            else:
                stats["gross_loss"] += abs(pnl)
            if normalized.get("directional_correct"):
                stats["directional_hits"] += 1
            stats["quality_sum"] += float(normalized.get("quality_score", 0.0) or 0.0)
            stats["direction_sum"] += float(normalized.get("direction_score", 0.0) or 0.0)
            stats["tech_sum"] += float(normalized.get("tech_score", 0.0) or 0.0)
        return normalized

    def snapshot(self, *, source_metadata: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        if not self._total_trades:
            return None

        metadata = dict(source_metadata or {})
        source_metadata_payload = _surface_source_metadata(metadata)
        if (
            self._snapshot_core_cache is None
            or self._snapshot_core_cache_trade_count != self._total_trades
        ):
            include_tech_band = _should_include_tech_band_from_counts(
                self._without_tech_counts,
                self._with_tech_counts,
                min_trades=self.min_trades,
            )
            levels, lookup_order = _surface_level_definitions(include_tech_band)
            nodes_by_level: dict[str, dict[str, dict[str, Any]]] = {}

            for level in levels:
                level_id = level["id"]
                level_nodes = self._level_stats.get(level_id, {})
                nodes_by_level[level_id] = {
                    key: _summarize_group_from_stats(
                        stats,
                        fields=list(level["fields"]),
                        field_values=dict(stats.get("field_values") or {}),
                        level_id=level_id,
                    )
                    for key, stats in level_nodes.items()
                }

            _attach_shrinkage(
                nodes_by_level,
                levels,
                shrinkage_trades=float(self.shrinkage_trades),
                sparse_warning_trades=int(self.sparse_warning_trades),
            )

            density_rows = [
                _level_density(
                    level,
                    nodes_by_level.get(level["id"], {}),
                    total_trades=self._total_trades,
                    min_trades=int(self.min_trades),
                )
                for level in levels
            ]
            warnings = _surface_warnings(density_rows, min_trades=int(self.min_trades))
            overall = dict((nodes_by_level.get("overall") or {}).get("overall") or {})
            self._snapshot_core_cache = {
                "min_trades": int(self.min_trades),
                "bucket_size": int(self.bucket_size),
                "direction_bucket_size": int(self.bucket_size),
                "quality_bucket_size": int(self.quality_bucket_size),
                "tech_bucket_size": int(self.tech_bucket_size),
                "shrinkage_trades": float(self.shrinkage_trades),
                "sparse_warning_trades": int(self.sparse_warning_trades),
                "include_tech_band": include_tech_band,
                "lookup_order": list(lookup_order),
                "levels": nodes_by_level,
                "overall": overall,
                "diagnostics": {
                    "level_density": density_rows,
                    "sparse_warnings": warnings,
                },
            }
            self._snapshot_core_cache_trade_count = self._total_trades
        core_payload = copy.deepcopy(self._snapshot_core_cache or {})

        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "source_mode": metadata.get("mode"),
            "source_profile": metadata.get("profile"),
            "source_run_at": metadata.get("run_at"),
            "source_lookback_years": metadata.get("lookback_years"),
            "source_n_picks": metadata.get("n_picks"),
            "source_iv_adj": metadata.get("iv_adj"),
            "source_pricing_lane": metadata.get("pricing_lane"),
            "source_playbook": metadata.get("playbook"),
            "source_truth_source": metadata.get("truth_source"),
            "source_promotion_status": metadata.get("promotion_status"),
            "source_quote_coverage_pct": metadata.get("quote_coverage_pct"),
            "source_strategy_domain": metadata.get("strategy_domain"),
            "source_contract_selection_basis": metadata.get("contract_selection_basis"),
            "source_universe_filters": metadata.get("universe_filters"),
            "source_metadata": source_metadata_payload,
            **core_payload,
        }


def _normalize_trade_for_surface(
    trade: dict[str, Any],
    *,
    direction_bucket_size: int,
    quality_bucket_size: int,
    tech_bucket_size: int,
) -> dict[str, Any]:
    direction_score = _safe_float(trade.get("direction_score"), 0.0)
    quality_score = _safe_float(trade.get("quality_score"), 0.0)
    tech_score = _safe_float(trade.get("tech_score"), 0.0)
    direction = normalized_trade_direction(
        trade.get("type", trade.get("trade_type", trade.get("direction")))
    )
    return {
        **trade,
        "market_regime": normalized_market_regime(trade.get("market_regime"), trade.get("spy_ret5")),
        "direction": direction,
        "direction_band": direction_score_bucket(direction_score, bucket_size=direction_bucket_size),
        "quality_band": quality_score_bucket(quality_score, bucket_size=quality_bucket_size),
        "tech_band": tech_score_bucket(tech_score, bucket_size=tech_bucket_size),
        "direction_score": direction_score,
        "quality_score": quality_score,
        "tech_score": tech_score,
        "pnl_pct": _safe_float(trade.get("pnl_pct"), 0.0),
    }


def load_backtest_result(results_file: Optional[str] = None) -> Optional[dict[str, Any]]:
    path = results_file or RESULTS_FILE
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def build_expectancy_surface_from_trades(
    trades: list[dict[str, Any]],
    *,
    source_metadata: Optional[dict[str, Any]] = None,
    min_trades: int = DEFAULT_SURFACE_MIN_TRADES,
    bucket_size: int = DEFAULT_DIRECTION_BUCKET_SIZE,
    quality_bucket_size: int = DEFAULT_QUALITY_BUCKET_SIZE,
    tech_bucket_size: int = DEFAULT_TECH_BUCKET_SIZE,
    shrinkage_trades: float = DEFAULT_SHRINKAGE_TRADES,
    sparse_warning_trades: int = DEFAULT_SPARSE_WARNING_TRADES,
) -> Optional[dict[str, Any]]:
    if not trades:
        return None

    accumulator = CalibrationAccumulator(
        min_trades=min_trades,
        bucket_size=bucket_size,
        quality_bucket_size=quality_bucket_size,
        tech_bucket_size=tech_bucket_size,
        shrinkage_trades=shrinkage_trades,
        sparse_warning_trades=sparse_warning_trades,
    )
    for trade in trades:
        accumulator.add_trade(trade)
    return accumulator.snapshot(source_metadata=source_metadata)


def build_expectancy_surface(
    result: Optional[dict[str, Any]] = None,
    *,
    results_file: Optional[str] = None,
    min_trades: int = DEFAULT_SURFACE_MIN_TRADES,
    bucket_size: int = DEFAULT_DIRECTION_BUCKET_SIZE,
    quality_bucket_size: int = DEFAULT_QUALITY_BUCKET_SIZE,
    tech_bucket_size: int = DEFAULT_TECH_BUCKET_SIZE,
    shrinkage_trades: float = DEFAULT_SHRINKAGE_TRADES,
    sparse_warning_trades: int = DEFAULT_SPARSE_WARNING_TRADES,
) -> Optional[dict[str, Any]]:
    source = result or load_backtest_result(results_file)
    if not source:
        return None
    return build_expectancy_surface_from_trades(
        list(source.get("trades") or []),
        source_metadata=source,
        min_trades=min_trades,
        bucket_size=bucket_size,
        quality_bucket_size=quality_bucket_size,
        tech_bucket_size=tech_bucket_size,
        shrinkage_trades=shrinkage_trades,
        sparse_warning_trades=sparse_warning_trades,
    )


EXPECTANCY_SURFACE_DIR_ENV = "OPTIONS_PROFIT_STATE_DIR"
EXPECTANCY_SURFACE_FILE_NAME = "expectancy_surface.json"


def _expectancy_surface_path() -> str | None:
    state_dir = os.getenv(EXPECTANCY_SURFACE_DIR_ENV, "").strip()
    if not state_dir:
        return None
    return os.path.join(state_dir, EXPECTANCY_SURFACE_FILE_NAME)


def save_expectancy_surface(surface: dict[str, Any]) -> str | None:
    """Persist an expectancy surface to disk for cross-session reuse."""
    path = _expectancy_surface_path()
    if not path or not surface:
        return None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(surface, handle, indent=2)
        os.replace(tmp_path, path)
        return path
    except OSError:
        return None


def load_persisted_expectancy_surface() -> dict[str, Any] | None:
    """Load a previously persisted expectancy surface from disk."""
    path = _expectancy_surface_path()
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            surface = json.load(handle)
        if not isinstance(surface, dict) or "levels" not in surface:
            return None
        return surface
    except (OSError, json.JSONDecodeError):
        return None


def lookup_calibrated_expectancy(
    surface: Optional[dict[str, Any]],
    *,
    direction_score: Any,
    quality_score: Any = None,
    market_regime: Any = None,
    trade_type: Any = None,
    direction: Any = None,
    tech_score: Any = None,
    require_positive: bool = False,
    allow_overall: bool = True,
) -> Optional[dict[str, Any]]:
    if not surface:
        return None

    normalized_values = {
        "market_regime": normalized_market_regime(market_regime),
        "direction": normalized_trade_direction(trade_type if trade_type is not None else direction),
        "direction_band": direction_score_bucket(
            direction_score,
            bucket_size=int(surface.get("direction_bucket_size", surface.get("bucket_size", DEFAULT_DIRECTION_BUCKET_SIZE)) or DEFAULT_DIRECTION_BUCKET_SIZE),
        ),
        "quality_band": quality_score_bucket(
            quality_score,
            bucket_size=int(surface.get("quality_bucket_size", DEFAULT_QUALITY_BUCKET_SIZE) or DEFAULT_QUALITY_BUCKET_SIZE),
        ),
        "tech_band": tech_score_bucket(
            tech_score,
            bucket_size=int(surface.get("tech_bucket_size", DEFAULT_TECH_BUCKET_SIZE) or DEFAULT_TECH_BUCKET_SIZE),
        ),
    }
    lookup_order = list(surface.get("lookup_order") or [])
    levels = surface.get("levels") or {}

    for level_id in lookup_order:
        if level_id == "overall" and not allow_overall:
            continue
        level_nodes = levels.get(level_id) or {}
        if not level_nodes:
            continue
        sample_node = next(iter(level_nodes.values()))
        fields = list(sample_node.get("fields") or [])
        if "tech_band" in fields and not bool(surface.get("include_tech_band")):
            continue
        key = _group_key(fields, normalized_values)
        candidate = level_nodes.get(key)
        if not candidate:
            continue
        if require_positive and _safe_float(candidate.get("avg_pnl_pct"), 0.0) <= 0.0:
            continue
        out = dict(candidate)
        out["lookup_source"] = level_id
        out["lookup_fields"] = list(fields)
        out["market_regime"] = normalized_values["market_regime"]
        out["direction"] = normalized_values["direction"]
        out["direction_band"] = normalized_values["direction_band"]
        out["quality_band"] = normalized_values["quality_band"]
        out["tech_band"] = normalized_values["tech_band"]
        out["dense_cohort"] = not bool(out.get("sparse_cohort"))
        out["cohort_density"] = "dense" if out["dense_cohort"] else "sparse"
        out["calibration_density"] = out["cohort_density"]
        out["calibration_is_dense"] = bool(out["dense_cohort"])
        out["sparse_warning"] = (
            f"{level_id} cohort is sparse with only {int(out.get('trades', 0) or 0)} trades."
            if out.get("sparse_cohort")
            else None
        )
        out["surface_provenance"] = _surface_provenance(surface)
        return out
    return None
