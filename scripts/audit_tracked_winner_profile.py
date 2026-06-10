from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

DEFAULT_DB_PATH = ROOT / "data" / "tracked_positions.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "tracked-winner-profiles"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_text(value: Any) -> str:
    return str(value or "").strip()


def _source(position: dict[str, Any]) -> dict[str, Any]:
    source = dict(position.get("source_pick_snapshot") or {})
    merged = dict(source)
    for key in (
        "ticker",
        "direction",
        "asset_class",
        "contract_symbol",
        "expiry",
        "strike",
        "entry_execution_price",
        "entry_execution_basis",
    ):
        if merged.get(key) in (None, "") and position.get(key) not in (None, ""):
            merged[key] = position.get(key)
    if not merged.get("strategy_type") and merged.get("short_strike") is not None:
        merged["strategy_type"] = "vertical_spread"
    return merged


def _debit_pct(row: dict[str, Any]) -> float | None:
    existing = _safe_float(row.get("debit_pct_of_width"))
    if existing is not None:
        return round(existing, 2)
    debit = _safe_float(row.get("net_debit"))
    if debit is None:
        debit = _safe_float(row.get("entry_execution_price"))
    width = _safe_float(row.get("spread_width"))
    if debit is None or width is None or width <= 0:
        return None
    return round(debit / width * 100.0, 2)


def _pnl(position: dict[str, Any]) -> float | None:
    for key in ("net_pnl_pct", "last_pnl_pct", "gross_pnl_pct"):
        value = _safe_float(position.get(key))
        if value is not None:
            return round(value, 4)
    return None


def _market_regime(row: dict[str, Any]) -> str:
    regime = _safe_text(row.get("market_regime")).lower()
    if regime:
        return regime
    spy_ret5 = _safe_float(row.get("spy_ret5"))
    if spy_ret5 is None:
        return "unknown"
    if spy_ret5 <= -0.5:
        return "bearish"
    if spy_ret5 >= 0.5:
        return "bullish"
    return "neutral"


def _bucket(value: float | None, cuts: tuple[float, ...], labels: tuple[str, ...]) -> str:
    if value is None:
        return "missing"
    for index, cut in enumerate(cuts):
        if value < cut:
            return labels[index]
    return labels[-1]


def _contract_proof_class(row: dict[str, Any], position: dict[str, Any]) -> str:
    promotion_class = _safe_text(row.get("promotion_class") or position.get("proof_class")).lower()
    selection_source = _safe_text(row.get("selection_source")).lower()
    if promotion_class == "promotable_exact_contract" or selection_source == "live_chain_exact_contract":
        return "promotable_exact_contract"
    if "comparable" in promotion_class or "comparable" in selection_source:
        return "comparable_exact_contract"
    if promotion_class:
        return promotion_class
    if selection_source:
        return selection_source
    return "unknown"


def _normalized_row(position: dict[str, Any]) -> dict[str, Any]:
    row = _source(position)
    pnl = _pnl(position)
    quality = _safe_float(row.get("quality_score"))
    direction_score = _safe_float(row.get("direction_score"))
    debit_pct = _debit_pct(row)
    return {
        "id": position.get("id"),
        "status": position.get("status"),
        "ticker": _safe_text(position.get("ticker") or row.get("ticker")).upper(),
        "direction": _safe_text(row.get("direction") or row.get("type") or position.get("direction")).lower(),
        "asset_class": _safe_text(row.get("asset_class") or position.get("asset_class")).lower(),
        "strategy_type": _safe_text(row.get("strategy_type")).lower(),
        "market_regime": _market_regime(row),
        "quality_score": quality,
        "quality_bucket": _bucket(quality, (60, 70, 80, 90), ("lt60", "60_69", "70_79", "80_89", "90_plus")),
        "direction_score": direction_score,
        "direction_bucket": _bucket(direction_score, (60, 70, 80, 90), ("lt60", "60_69", "70_79", "80_89", "90_plus")),
        "debit_pct_of_width": debit_pct,
        "debit_bucket": _bucket(debit_pct, (25, 30, 35, 40, 55), ("lt25", "25_29", "30_34", "35_39", "40_54", "55_plus")),
        "contract_proof_class": _contract_proof_class(row, position),
        "selection_source": _safe_text(row.get("selection_source")).lower(),
        "net_pnl_pct": pnl,
        "is_winner": pnl is not None and pnl > 0,
        "is_loser": pnl is not None and pnl < 0,
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pnl_values = [float(row["net_pnl_pct"]) for row in rows if row.get("net_pnl_pct") is not None]
    winners = [value for value in pnl_values if value > 0]
    losers = [value for value in pnl_values if value < 0]
    gross_profit = sum(winners)
    gross_loss = -sum(losers)
    if gross_loss > 0:
        profit_factor: float | None = round(gross_profit / gross_loss, 2)
    elif gross_profit > 0:
        profit_factor = None
    else:
        profit_factor = None
    return {
        "count": len(rows),
        "priced_count": len(pnl_values),
        "winner_count": len(winners),
        "loser_count": len(losers),
        "win_rate_pct": round(len(winners) / len(pnl_values) * 100.0, 1) if pnl_values else 0.0,
        "avg_pnl_pct": round(sum(pnl_values) / len(pnl_values), 2) if pnl_values else None,
        "profit_factor": profit_factor,
        "no_loss_sample": bool(pnl_values and gross_loss <= 0 and gross_profit > 0),
        "total_net_pnl_pct_points": round(sum(pnl_values), 2) if pnl_values else 0.0,
    }


def _group(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[_safe_text(row.get(key)) or "unknown"].append(row)
    output = [{"key": group_key, **_metrics(group_rows)} for group_key, group_rows in groups.items()]
    output.sort(
        key=lambda item: (
            float(item.get("profit_factor") or 0.0),
            float(item.get("avg_pnl_pct") or -999.0),
            int(item.get("count") or 0),
        ),
        reverse=True,
    )
    return output


def _intersection(rows: list[dict[str, Any]], key: str) -> list[str]:
    counter = Counter(_safe_text(row.get(key)) or "unknown" for row in rows)
    return [value for value, count in counter.items() if count == len(rows)]


def _candidate_lane(rows: list[dict[str, Any]]) -> dict[str, Any]:
    winners = [row for row in rows if row.get("is_winner")]
    if not winners:
        return {
            "id": "tracked_winner_observation",
            "status": "no_winners",
            "rules": {},
        }
    tickers = Counter(row["ticker"] for row in winners)
    asset_classes = Counter(row["asset_class"] for row in winners)
    regimes = Counter(row["market_regime"] for row in winners)
    directions = Counter(row["direction"] for row in winners)
    strategy_types = Counter(row["strategy_type"] for row in winners)
    debit_values = [float(row["debit_pct_of_width"]) for row in winners if row.get("debit_pct_of_width") is not None]
    quality_values = [float(row["quality_score"]) for row in winners if row.get("quality_score") is not None]
    return {
        "id": "tracked_winner_observation",
        "status": "candidate",
        "promotion_allowed": False,
        "rules": {
            "allowed_tickers": [ticker for ticker, count in tickers.items() if count >= 2],
            "dominant_asset_classes": [value for value, _ in asset_classes.most_common(3)],
            "dominant_market_regimes": [value for value, _ in regimes.most_common(3)],
            "dominant_directions": [value for value, _ in directions.most_common(3)],
            "dominant_strategy_types": [value for value, _ in strategy_types.most_common(3)],
            "observed_quality_floor": round(min(quality_values), 2) if quality_values else None,
            "observed_debit_pct_ceiling": round(max(debit_values), 2) if debit_values else None,
            "suggested_starting_filter": {
                "direction": directions.most_common(1)[0][0] if directions else None,
                "strategy_type": strategy_types.most_common(1)[0][0] if strategy_types else None,
                "market_regime": regimes.most_common(1)[0][0] if regimes else None,
                "max_debit_pct_of_width": 40.0 if debit_values and max(debit_values) <= 40 else None,
                "min_quality_score": 60.0 if quality_values and min(quality_values) >= 60 else None,
            },
        },
        "reason": "This lane describes what current tracked winners share; keep it as peer-lane research evidence until closed exact-contract outcomes prove it.",
    }


def build_tracked_winner_profile(positions: list[dict[str, Any]], *, min_winner_pnl_pct: float = 0.0) -> dict[str, Any]:
    rows = [_normalized_row(position) for position in positions]
    winners = [row for row in rows if row.get("net_pnl_pct") is not None and float(row["net_pnl_pct"]) > min_winner_pnl_pct]
    losers = [row for row in rows if row.get("net_pnl_pct") is not None and float(row["net_pnl_pct"]) < 0]
    profile = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": "tracked_positions",
        "min_winner_pnl_pct": float(min_winner_pnl_pct),
        "overall": _metrics(rows),
        "winners": _metrics(winners),
        "losers": _metrics(losers),
        "winner_count_by_ticker": dict(Counter(row["ticker"] for row in winners).most_common()),
        "winner_count_by_asset_class": dict(Counter(row["asset_class"] for row in winners).most_common()),
        "winner_count_by_contract_proof_class": dict(Counter(row["contract_proof_class"] for row in winners).most_common()),
        "winner_groups": {
            "ticker": _group(winners, "ticker"),
            "asset_class": _group(winners, "asset_class"),
            "market_regime": _group(winners, "market_regime"),
            "quality_bucket": _group(winners, "quality_bucket"),
            "debit_bucket": _group(winners, "debit_bucket"),
            "contract_proof_class": _group(winners, "contract_proof_class"),
        },
        "loser_groups": {
            "ticker": _group(losers, "ticker"),
            "asset_class": _group(losers, "asset_class"),
            "market_regime": _group(losers, "market_regime"),
            "quality_bucket": _group(losers, "quality_bucket"),
            "debit_bucket": _group(losers, "debit_bucket"),
            "contract_proof_class": _group(losers, "contract_proof_class"),
        },
        "winner_intersections": {
            "direction": _intersection(winners, "direction"),
            "strategy_type": _intersection(winners, "strategy_type"),
            "market_regime": _intersection(winners, "market_regime"),
        },
        "candidate_lane": _candidate_lane(rows),
        "positions": rows,
        "limitations": [
            "Open tracked P&L is marked-to-market, not closed realized proof.",
            "Comparable-contract rows are not the same as promotable exact-contract forward proof.",
            "This profile should generate an observation lane, not promotion by itself.",
        ],
    }
    profile["profile_fingerprint"] = build_tracked_winner_profile_fingerprint(profile)
    return profile


def build_tracked_winner_profile_fingerprint(profile: dict[str, Any]) -> str:
    payload = {
        "kind": "tracked_winner_profile",
        "source": profile.get("source"),
        "overall": profile.get("overall"),
        "winners": profile.get("winners"),
        "winner_count_by_ticker": profile.get("winner_count_by_ticker"),
        "candidate_lane": profile.get("candidate_lane"),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf8")
    return hashlib.sha256(encoded).hexdigest()


def find_duplicate_tracked_winner_profile(output_dir: Path, fingerprint: str) -> Path | None:
    for profile_path in sorted(Path(output_dir).glob("tracked_winner_profile_*.json")):
        try:
            profile = _read_json(profile_path)
        except (OSError, json.JSONDecodeError):
            continue
        if profile.get("profile_fingerprint") == fingerprint:
            return profile_path
    return None


def _load_positions(db_path: Path, status: str | None) -> list[dict[str, Any]]:
    from positions_repository import SqliteTrackedPositionsRepository

    repo = SqliteTrackedPositionsRepository(str(db_path))
    repo.init_schema()
    return repo.list_positions(status)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit common traits in profitable tracked positions.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--status", default="open", choices=["open", "closed", "all"])
    parser.add_argument("--min-winner-pnl-pct", type=float, default=0.0)
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    status = None if args.status == "all" else args.status
    positions = _load_positions(Path(args.db_path), status)
    profile = build_tracked_winner_profile(positions, min_winner_pnl_pct=args.min_winner_pnl_pct)
    profile["db_path"] = str(Path(args.db_path))
    profile["position_status_filter"] = args.status
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    duplicate = find_duplicate_tracked_winner_profile(output_dir, str(profile.get("profile_fingerprint") or ""))
    if duplicate is not None and not args.force:
        compact = {
            "status": "duplicate_skipped",
            "duplicate_of": str(duplicate),
            "fingerprint": profile.get("profile_fingerprint"),
            "overall": profile.get("overall"),
            "winners": profile.get("winners"),
            "candidate_lane": profile.get("candidate_lane"),
        }
        print(json.dumps(profile if args.json else compact, indent=2))
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = output_dir / f"tracked_winner_profile_{stamp}.json"
    latest_path = output_dir / "latest.json"
    serialized = json.dumps(profile, indent=2)
    output_path.write_text(serialized, encoding="utf8")
    latest_path.write_text(serialized, encoding="utf8")
    compact = {
        "output": str(output_path),
        "latest": str(latest_path),
        "overall": profile.get("overall"),
        "winners": profile.get("winners"),
        "winner_count_by_ticker": profile.get("winner_count_by_ticker"),
        "candidate_lane": profile.get("candidate_lane"),
        "limitations": profile.get("limitations"),
    }
    print(json.dumps(profile if args.json else compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
