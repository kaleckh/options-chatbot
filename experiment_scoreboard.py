from __future__ import annotations

import glob
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from wfo_optimizer import (
    IMPORTED_DAILY_TRUTH_SOURCE,
    IMPORTED_TRUTH_SOURCE,
    MIN_IMPORTED_QUOTE_COVERAGE_PCT,
    build_options_stability_report,
)


def _is_imported_truth_source(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {IMPORTED_TRUTH_SOURCE, IMPORTED_DAILY_TRUTH_SOURCE}


DEFAULT_RESULT_PATH = Path(__file__).resolve().parent / "wfo_results.json"
SKIP_DIR_NAMES = {".git", ".next", ".pytest_cache", "__pycache__", "node_modules", "tmp"}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_run_at(value: Any) -> datetime:
    if not value:
        return datetime.min
    text = str(value).strip()
    if not text:
        return datetime.min
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def _normalize_status(value: Any) -> str:
    text = str(value or "block").strip().lower()
    if text in {"promote", "watch", "block"}:
        return text
    return "block"


def _status_rank(status: str) -> int:
    return {"block": 0, "watch": 1, "promote": 2}.get(_normalize_status(status), 0)


def _downgrade_status(status: str) -> str:
    normalized = _normalize_status(status)
    if normalized == "promote":
        return "watch"
    if normalized == "watch":
        return "block"
    return "block"


def _is_backtest_result(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("mode") or "").strip().lower() != "backtest":
        return False
    return "pricing_lane" in payload and "playbook" in payload


def _should_skip_path(path: Path) -> bool:
    normalized_parts = [part.lower() for part in path.parts]
    if SKIP_DIR_NAMES.intersection(normalized_parts):
        return True
    if any(
        part.startswith(".tmp")
        or part.startswith("pytest-of-")
        for part in normalized_parts
    ):
        return True
    return "day-trading" in normalized_parts


def discover_cached_result_paths(inputs: Sequence[str | Path] | None = None) -> list[Path]:
    if not inputs:
        return [DEFAULT_RESULT_PATH] if DEFAULT_RESULT_PATH.exists() else []

    discovered: list[Path] = []
    seen: set[Path] = set()

    def _add_path(path: Path, *, skip_ephemeral: bool = True) -> None:
        if not path.exists() or not path.is_file() or path.suffix.lower() != ".json":
            return
        resolved = path.resolve()
        if resolved in seen or (skip_ephemeral and _should_skip_path(resolved)):
            return
        seen.add(resolved)
        discovered.append(resolved)

    def _walk(item: str | Path) -> None:
        text = str(item)
        if any(ch in text for ch in "*?[]"):
            for match in glob.glob(text, recursive=True):
                _walk(Path(match))
            return

        path = Path(item)
        if path.is_dir():
            for child in path.rglob("*.json"):
                if _should_skip_path(child):
                    continue
                _add_path(child)
            return
        _add_path(path, skip_ephemeral=False)

    for item in inputs:
        _walk(item)

    return sorted(discovered)


def load_cached_backtest_entries(inputs: Sequence[str | Path] | None = None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in discover_cached_result_paths(inputs):
        try:
            with path.open("r", encoding="utf8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError):
            continue
        if not _is_backtest_result(payload):
            continue
        entries.append(
            {
                "path": str(path),
                "path_label": path.stem,
                "result": payload,
                "run_at": payload.get("run_at"),
            }
        )
    return sorted(entries, key=lambda item: (_parse_run_at(item.get("run_at")), item["path"]))


def _selection_source_counts(result: dict[str, Any]) -> dict[str, int]:
    explicit = result.get("selection_source_counts") or {}
    if explicit:
        return {str(key): _safe_int(value) for key, value in explicit.items()}

    counts: dict[str, int] = {}
    for trade in result.get("trades") or []:
        key = str(trade.get("selection_source") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _source_shares(result: dict[str, Any]) -> dict[str, Any]:
    counts = _selection_source_counts(result)
    total = max(
        _safe_int(result.get("total_trades")),
        sum(counts.values()),
        len(result.get("trades") or []),
    )
    if total <= 0:
        return {
            "counts": counts,
            "bootstrap_count": 0,
            "calibrated_count": 0,
            "unknown_count": 0,
            "bootstrap_share_pct": 0.0,
            "calibrated_share_pct": 0.0,
            "unknown_share_pct": 0.0,
        }

    bootstrap_count = sum(
        count for key, count in counts.items() if "bootstrap" in str(key).strip().lower()
    )
    unknown_count = sum(
        count for key, count in counts.items() if str(key).strip().lower() in {"", "unknown"}
    )
    calibrated_count = max(total - bootstrap_count - unknown_count, 0)
    return {
        "counts": counts,
        "bootstrap_count": bootstrap_count,
        "calibrated_count": calibrated_count,
        "unknown_count": unknown_count,
        "bootstrap_share_pct": round(bootstrap_count / total * 100.0, 1),
        "calibrated_share_pct": round(calibrated_count / total * 100.0, 1),
        "unknown_share_pct": round(unknown_count / total * 100.0, 1),
    }


def _variant_key(result: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(result.get("playbook") or "unknown"),
        _safe_int(result.get("lookback_years")),
        _safe_int(result.get("n_picks")),
        str(result.get("iv_adj")),
        str(result.get("profile") or "mixed"),
    )


def _variant_label(result: dict[str, Any]) -> str:
    return (
        f"{result.get('playbook', 'unknown')} | "
        f"{_safe_int(result.get('lookback_years'))}y | "
        f"picks={_safe_int(result.get('n_picks'))} | "
        f"iv={result.get('iv_adj')}"
    )


def _lane_summary(
    entry: dict[str, Any],
    stability_report: dict[str, Any],
) -> dict[str, Any]:
    result = entry["result"]
    source_shares = _source_shares(result)
    rolling_summary = dict(stability_report.get("rolling_summary") or {})
    return {
        "path": entry["path"],
        "path_label": entry["path_label"],
        "run_at": result.get("run_at"),
        "pricing_lane": str(result.get("pricing_lane") or "unknown"),
        "truth_source": str(result.get("truth_source") or "synthetic_research"),
        "playbook": result.get("playbook"),
        "lookback_years": _safe_int(result.get("lookback_years")),
        "n_picks": _safe_int(result.get("n_picks")),
        "iv_adj": _safe_float(result.get("iv_adj")),
        "total_trades": _safe_int(result.get("total_trades")),
        "priced_trade_count": _safe_int(result.get("priced_trade_count"), _safe_int(result.get("total_trades"))),
        "unpriced_trade_count": _safe_int(result.get("unpriced_trade_count")),
        "quote_coverage_pct": round(_safe_float(result.get("quote_coverage_pct"), 100.0), 1),
        "profit_factor": round(_safe_float(result.get("profit_factor")), 2),
        "avg_pnl_pct": round(_safe_float(result.get("avg_pnl_pct")), 2),
        "win_rate_pct": round(_safe_float(result.get("win_rate_pct")), 1),
        "directional_accuracy_pct": round(_safe_float(result.get("directional_accuracy_pct")), 1),
        "stability_status": _normalize_status(stability_report.get("overall_status")),
        "rolling_pass_rate_pct": round(_safe_float(rolling_summary.get("pass_rate_pct")), 1),
        "worst_rolling_profit_factor": round(_safe_float(rolling_summary.get("worst_profit_factor")), 2),
        "selection_source_counts": source_shares["counts"],
        "bootstrap_count": source_shares["bootstrap_count"],
        "bootstrap_share_pct": source_shares["bootstrap_share_pct"],
        "calibrated_count": source_shares["calibrated_count"],
        "calibrated_share_pct": source_shares["calibrated_share_pct"],
        "unknown_count": source_shares["unknown_count"],
        "unknown_share_pct": source_shares["unknown_share_pct"],
        "stability_recommendations": list(stability_report.get("recommendations") or []),
        "_run_at_sort": _parse_run_at(result.get("run_at")),
    }


def _fill_degradation(mid_lane: dict[str, Any] | None, pessimistic_lane: dict[str, Any] | None) -> dict[str, Any] | None:
    if not mid_lane or not pessimistic_lane:
        return None
    profit_factor_drop = round(
        _safe_float(mid_lane.get("profit_factor")) - _safe_float(pessimistic_lane.get("profit_factor")),
        2,
    )
    avg_pnl_pct_drop = round(
        _safe_float(mid_lane.get("avg_pnl_pct")) - _safe_float(pessimistic_lane.get("avg_pnl_pct")),
        2,
    )
    directional_accuracy_pct_drop = round(
        _safe_float(mid_lane.get("directional_accuracy_pct")) - _safe_float(pessimistic_lane.get("directional_accuracy_pct")),
        1,
    )
    materially_worse = profit_factor_drop >= 0.2 or avg_pnl_pct_drop >= 5.0
    return {
        "profit_factor_drop": profit_factor_drop,
        "avg_pnl_pct_drop": avg_pnl_pct_drop,
        "directional_accuracy_pct_drop": directional_accuracy_pct_drop,
        "materially_worse_under_pessimistic": materially_worse,
    }


def _conservative_status(
    *,
    anchor_lane: dict[str, Any],
    mid_lane: dict[str, Any] | None,
    pessimistic_lane: dict[str, Any] | None,
    min_trades: int,
    bootstrap_watch_share_pct: float,
    bootstrap_block_share_pct: float,
) -> tuple[str, list[str]]:
    status = _normalize_status(anchor_lane.get("stability_status"))
    reasons: list[str] = []

    if _safe_int(anchor_lane.get("total_trades")) < int(min_trades):
        status = "block"
        reasons.append(
            f"Anchor lane only has {_safe_int(anchor_lane.get('total_trades'))} trades against a {int(min_trades)}-trade minimum."
        )

    bootstrap_share_pct = _safe_float(anchor_lane.get("bootstrap_share_pct"))
    if bootstrap_share_pct >= float(bootstrap_block_share_pct):
        status = "block"
        reasons.append(
            f"Bootstrap share is {bootstrap_share_pct:.1f}%, so the replay still lacks enough calibrated cohort support."
        )
    elif bootstrap_share_pct >= float(bootstrap_watch_share_pct):
        if status == "promote":
            status = _downgrade_status(status)
        reasons.append(
            f"Bootstrap share is still {bootstrap_share_pct:.1f}%, so confidence stays capped."
        )

    if _safe_float(anchor_lane.get("calibrated_share_pct")) <= 0.0:
        if status == "promote":
            status = _downgrade_status(status)
        reasons.append("No trades in the anchor lane are coming from replay-calibrated cohorts yet.")

    if not _is_imported_truth_source(anchor_lane.get("truth_source")):
        if status == "promote":
            status = _downgrade_status(status)
        reasons.append("Synthetic-only lanes remain capped below promote until imported historical validation exists.")
    elif _safe_float(anchor_lane.get("quote_coverage_pct"), 100.0) < MIN_IMPORTED_QUOTE_COVERAGE_PCT:
        status = "block"
        reasons.append(
            f"Imported quote coverage is only {_safe_float(anchor_lane.get('quote_coverage_pct'), 0.0):.1f}%, below the {MIN_IMPORTED_QUOTE_COVERAGE_PCT:.0f}% floor."
        )

    if pessimistic_lane is None:
        if status == "promote":
            status = _downgrade_status(status)
        reasons.append("No pessimistic companion lane is cached, so the verdict cannot clear watch-level confidence.")
    else:
        if _safe_float(pessimistic_lane.get("profit_factor")) < 1.0 or _safe_float(pessimistic_lane.get("avg_pnl_pct")) <= 0.0:
            if status == "promote":
                status = _downgrade_status(status)
            reasons.append("Pessimistic fills do not preserve positive expectancy.")

    degradation = _fill_degradation(mid_lane, pessimistic_lane)
    if degradation and degradation["materially_worse_under_pessimistic"]:
        if status == "promote":
            status = _downgrade_status(status)
        reasons.append("Mid-lane edge degrades materially under pessimistic fills.")

    if _safe_float(anchor_lane.get("rolling_pass_rate_pct")) < 50.0 and status == "promote":
        status = _downgrade_status(status)
        reasons.append("Rolling-window pass rate is still too weak for a promote verdict.")

    if not reasons:
        reasons.append("This variant currently clears the conservative scoreboard bars.")

    return status, reasons


def _score_candidate(
    status: str,
    anchor_lane: dict[str, Any],
    degradation: dict[str, Any] | None,
) -> float:
    profit_factor = _safe_float(anchor_lane.get("profit_factor"))
    avg_pnl_pct = _safe_float(anchor_lane.get("avg_pnl_pct"))
    rolling_pass_rate_pct = _safe_float(anchor_lane.get("rolling_pass_rate_pct"))
    calibrated_share_pct = _safe_float(anchor_lane.get("calibrated_share_pct"))
    bootstrap_share_pct = _safe_float(anchor_lane.get("bootstrap_share_pct"))
    total_trades = _safe_float(anchor_lane.get("total_trades"))
    score = (
        _status_rank(status) * 1000.0
        + min(max(profit_factor, 0.0), 3.0) * 100.0
        + max(min(avg_pnl_pct, 50.0), -50.0) * 5.0
        + rolling_pass_rate_pct * 2.0
        + calibrated_share_pct
        - bootstrap_share_pct * 0.5
        + min(total_trades, 100.0)
    )
    if degradation:
        score -= max(_safe_float(degradation.get("profit_factor_drop")), 0.0) * 50.0
        score -= max(_safe_float(degradation.get("avg_pnl_pct_drop")), 0.0) * 2.0
    return round(score, 1)


def build_replay_scoreboard(
    entries: Sequence[dict[str, Any]] | None = None,
    *,
    result_paths: Sequence[str | Path] | None = None,
    min_trades: int = 20,
    min_profit_factor: float = 1.05,
    catastrophic_pf_floor: float = 0.85,
    bootstrap_watch_share_pct: float = 40.0,
    bootstrap_block_share_pct: float = 80.0,
    stability_builder: Callable[..., dict[str, Any]] = build_options_stability_report,
) -> dict[str, Any]:
    loaded_entries = list(entries) if entries is not None else load_cached_backtest_entries(result_paths)
    if not loaded_entries:
        return {"error": "No cached backtest results found"}

    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for entry in loaded_entries:
        result = entry["result"]
        stability_report = stability_builder(
            result=result,
            min_trades=min_trades,
            min_profit_factor=min_profit_factor,
            catastrophic_pf_floor=catastrophic_pf_floor,
        )
        lane = str(result.get("pricing_lane") or "unknown").strip().lower()
        if not lane:
            lane = "unknown"
        group = grouped.setdefault(
            _variant_key(result),
            {
                "variant_label": _variant_label(result),
                "playbook": result.get("playbook"),
                "lookback_years": _safe_int(result.get("lookback_years")),
                "n_picks": _safe_int(result.get("n_picks")),
                "iv_adj": _safe_float(result.get("iv_adj")),
                "profile": result.get("profile"),
                "lanes": {},
                "files_seen": [],
            },
        )
        lane_summary = _lane_summary(entry, stability_report)
        existing = group["lanes"].get(lane)
        if existing is None or lane_summary["_run_at_sort"] >= existing["_run_at_sort"]:
            group["lanes"][lane] = lane_summary
        group["files_seen"].append(entry["path"])

    candidates: list[dict[str, Any]] = []
    for group in grouped.values():
        mid_lane = group["lanes"].get("mid")
        pessimistic_lane = group["lanes"].get("pessimistic")
        imported_lane = group["lanes"].get(IMPORTED_TRUTH_SOURCE) or group["lanes"].get(IMPORTED_DAILY_TRUTH_SOURCE)
        anchor_lane = imported_lane or pessimistic_lane or mid_lane or next(iter(group["lanes"].values()))
        degradation = _fill_degradation(mid_lane, pessimistic_lane)
        scoreboard_status, verdict_reasons = _conservative_status(
            anchor_lane=anchor_lane,
            mid_lane=mid_lane,
            pessimistic_lane=pessimistic_lane,
            min_trades=min_trades,
            bootstrap_watch_share_pct=bootstrap_watch_share_pct,
            bootstrap_block_share_pct=bootstrap_block_share_pct,
        )
        scoreboard_score = _score_candidate(scoreboard_status, anchor_lane, degradation)
        candidates.append(
            {
                "label": group["variant_label"],
                "playbook": group["playbook"],
                "lookback_years": group["lookback_years"],
                "n_picks": group["n_picks"],
                "iv_adj": group["iv_adj"],
                "profile": group["profile"],
                "files_seen": sorted(set(group["files_seen"])),
                "anchor_lane": anchor_lane["pricing_lane"],
                "scoreboard_status": scoreboard_status,
                "scoreboard_score": scoreboard_score,
                "verdict_reasons": verdict_reasons,
                "lanes": {
                    lane_key: {
                        key: value
                        for key, value in lane_value.items()
                        if not key.startswith("_")
                    }
                    for lane_key, lane_value in group["lanes"].items()
                },
                "fill_degradation": degradation,
            }
        )

    candidates = sorted(
        candidates,
        key=lambda item: (
            _status_rank(item["scoreboard_status"]),
            _safe_float(item["scoreboard_score"]),
            _safe_float(item["lanes"][item["anchor_lane"]]["profit_factor"]),
            _safe_float(item["lanes"][item["anchor_lane"]]["avg_pnl_pct"]),
            _safe_float(item["lanes"][item["anchor_lane"]]["rolling_pass_rate_pct"]),
            _safe_float(item["lanes"][item["anchor_lane"]]["calibrated_share_pct"]),
            _safe_float(item["lanes"][item["anchor_lane"]]["total_trades"]),
        ),
        reverse=True,
    )

    for index, candidate in enumerate(candidates, start=1):
        candidate["rank"] = index

    status_counts = {
        "promote": sum(1 for item in candidates if item["scoreboard_status"] == "promote"),
        "watch": sum(1 for item in candidates if item["scoreboard_status"] == "watch"),
        "block": sum(1 for item in candidates if item["scoreboard_status"] == "block"),
    }

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "thresholds": {
            "min_trades": int(min_trades),
            "min_profit_factor": float(min_profit_factor),
            "catastrophic_pf_floor": float(catastrophic_pf_floor),
            "bootstrap_watch_share_pct": float(bootstrap_watch_share_pct),
            "bootstrap_block_share_pct": float(bootstrap_block_share_pct),
        },
        "summary": {
            "result_files_loaded": len(loaded_entries),
            "variants_ranked": len(candidates),
            "status_counts": status_counts,
        },
        "candidates": candidates,
    }
