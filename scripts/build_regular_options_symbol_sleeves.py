from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-symbol-sleeves"
DOCS_REPORT = ROOT / "docs" / "regular-options-symbol-sleeves.md"

BULLISH_TICKER_AUDIT = (
    ROOT
    / "data"
    / "profitability-lab"
    / "bullish-pullback-observation"
    / "ticker-audit"
    / "latest.json"
)
REGULAR_MULTILANE = ROOT / "data" / "profitability-lab" / "regular-options-multilane" / "latest.json"
ALL_PLANNED_LATEST = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-autoresearch"
    / "all-planned-sleeves"
    / "latest.json"
)
ALL_PLANNED_PARTIAL = ALL_PLANNED_LATEST.with_name("latest_partial.json")
LANE_LAB_LATEST = ROOT / "data" / "lane-lab" / "latest.json"
TRADING_DESK_GUARDRAILS = ROOT / "data" / "forward-tracking" / "trading_desk_profitability_guardrails_latest.json"
OPEN_POSITION_RISK = ROOT / "data" / "forward-tracking" / "regular_open_position_risk_latest.json"
SUGGESTED_TRADE_RISK = ROOT / "data" / "forward-tracking" / "suggested_trade_close_risk_latest.json"

TRUSTED_EXACT = "trusted_intraday_opra_nbbo_exact"
TRUSTED_UNRESOLVED = "trusted_intraday_unresolved"
DAILY_RESEARCH = "daily_eod_research_only"
RESEARCH_BACKFILL = "research_backfill_paper"
LIVE_SCAN_EXACT = "live_scan_exact_contract"
MARK_OR_STALE = "mark_or_stale_review"
BLOCKED_NO_DATA = "blocked_no_data"

SOURCE_PRECEDENCE = [
    "code_config_scan_playbooks",
    "exact_intraday_run_artifacts",
    "bullish_pullback_ticker_confidence_layer_artifacts",
    "tracked_and_suggested_trade_audits",
    "lane_lab_all_planned_readiness",
    "living_docs_cross_check",
]

HIGH_BETA_SYMBOLS = {"NVDA", "AMZN", "TSLA", "COIN", "PLTR", "MSTR", "ARM", "SMCI", "AMD", "META", "NFLX"}
INDEX_SECTOR_SYMBOLS = {"SPY", "QQQ", "DIA", "XLK", "IWM", "TLT", "XLE", "XLF", "KRE", "SMH"}
SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _round(value: Any, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(_safe_float(value), digits)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf8"))


def _load_fresh_partial_payload(full_path: Path, partial_path: Path) -> dict[str, Any]:
    if not partial_path.exists():
        return {}
    if full_path.exists():
        try:
            if partial_path.stat().st_mtime <= full_path.stat().st_mtime:
                return {}
        except OSError:
            return {}
    return _load_json(partial_path)


def _rel(path: Path | str | None) -> str | None:
    if path is None:
        return None
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        return str(candidate.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(candidate)


def _abs_path(path: str | Path | None) -> Path | None:
    if not path:
        return None
    candidate = Path(str(path))
    return candidate if candidate.is_absolute() else ROOT / candidate


def _generated_at(payload: dict[str, Any]) -> str | None:
    for key in ("generated_at_utc", "generated_at", "run_at", "created_at"):
        if payload.get(key):
            return str(payload.get(key))
    return None


def latest_stale_info(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"stale": False, "newer_siblings": []}
    newer: list[str] = []
    if path.name.startswith("latest"):
        latest_mtime = path.stat().st_mtime
        for sibling in path.parent.glob("*.json"):
            if sibling.name == path.name:
                continue
            if sibling.stat().st_mtime > latest_mtime + 0.001:
                newer.append(_rel(sibling) or str(sibling))
    return {"stale": bool(newer), "newer_siblings": sorted(newer)[:25]}


def input_manifest_entry(path: Path, source_type: str) -> dict[str, Any]:
    entry = {
        "path": _rel(path),
        "source_type": source_type,
        "exists": path.exists(),
        "generated_at": None,
        "mtime_utc": None,
        "stale_latest": False,
        "newer_siblings": [],
        "status": "missing",
    }
    if not path.exists():
        return entry
    try:
        payload = _load_json(path)
        entry["generated_at"] = _generated_at(payload)
    except Exception as exc:
        entry["status"] = f"unreadable:{exc}"
        return entry
    entry["mtime_utc"] = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )
    stale = latest_stale_info(path)
    entry["stale_latest"] = bool(stale["stale"])
    entry["newer_siblings"] = stale["newer_siblings"]
    entry["status"] = "stale" if entry["stale_latest"] else "ok"
    return entry


def normalize_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    return symbol if SYMBOL_RE.match(symbol) else ""


def add_symbol_source(
    universe: dict[str, dict[str, Any]],
    symbol: Any,
    source_tier: str,
    detail: str,
) -> None:
    normalized = normalize_symbol(symbol)
    if not normalized:
        return
    row = universe.setdefault(
        normalized,
        {
            "symbol": normalized,
            "source_tiers": [],
            "source_details": [],
        },
    )
    if source_tier not in row["source_tiers"]:
        row["source_tiers"].append(source_tier)
    if detail and detail not in row["source_details"]:
        row["source_details"].append(detail)


def _symbol_list_from_playbook(playbook: dict[str, Any]) -> list[tuple[str, str]]:
    fields = [
        "scan_tickers",
        "allowed_tickers",
        "expansion_tickers",
        "historical_data_ready_tickers",
        "core_tickers",
        "conditional_tickers",
        "profitability_repair_allowed_tickers",
        "profitability_repair_excluded_tickers",
    ]
    found: list[tuple[str, str]] = []
    for field in fields:
        values = playbook.get(field) or []
        if not isinstance(values, list):
            continue
        for value in values:
            symbol = normalize_symbol(value)
            if symbol:
                found.append((symbol, field))
    return found


def collect_playbook_universe(universe: dict[str, dict[str, Any]]) -> dict[str, Any]:
    try:
        from supervised_scan import get_scan_playbooks

        playbooks = get_scan_playbooks()
    except Exception as exc:
        return {"status": "error", "error": str(exc), "playbook_count": 0}

    regular_playbooks = []
    for playbook in playbooks:
        playbook_id = str(playbook.get("id") or "")
        if playbook_id == "ai_commodity_infra_observation":
            continue
        regular_playbooks.append(playbook_id)
        for symbol, field in _symbol_list_from_playbook(playbook):
            add_symbol_source(
                universe,
                symbol,
                "current_queue/configured_scan_universe",
                f"playbook:{playbook_id}:{field}",
            )
    return {"status": "ok", "playbook_count": len(regular_playbooks), "playbooks": regular_playbooks}


def _proof_grade_for_run(run: dict[str, Any]) -> str:
    truth = str(run.get("truth_source") or "").lower()
    realism = str(run.get("execution_realism") or "").lower()
    if truth == "historical_imported" and realism == "quote_backed_intraday_replay":
        return TRUSTED_EXACT
    if "daily" in truth:
        return DAILY_RESEARCH
    if truth == "historical_imported":
        return TRUSTED_UNRESOLVED
    return BLOCKED_NO_DATA


def _is_exact_imported_trade(trade: dict[str, Any], evidence_class: str) -> bool:
    if evidence_class != TRUSTED_EXACT:
        return False
    resolution = str(trade.get("entry_contract_resolution") or "").lower()
    fill_basis = str(trade.get("exit_fill_basis") or "").lower()
    return bool(trade.get("priced", True)) and resolution.startswith("exact") and fill_basis == "imported_spread_mark"


def _trade_pnl(trade: dict[str, Any]) -> float:
    return _safe_float(trade.get("net_pnl_pct", trade.get("pnl_pct")))


def _trade_direction(trade: dict[str, Any]) -> str:
    raw = str(trade.get("type") or trade.get("direction") or "").strip().lower()
    return raw if raw in {"call", "put"} else "unknown"


def _run_metrics(run: dict[str, Any]) -> dict[str, Any]:
    metrics = run.get("authoritative_profitability_metrics") or run.get("exact_contract_metrics") or {}
    return {
        "candidate_trade_count": _safe_int(run.get("candidate_trade_count")),
        "priced_trade_count": _safe_int(run.get("priced_trade_count") or run.get("total_trades")),
        "unpriced_trade_count": _safe_int(run.get("unpriced_trade_count")),
        "profit_factor": _round(metrics.get("profit_factor")),
        "avg_pnl_pct": _round(metrics.get("avg_pnl_pct")),
        "win_rate_pct": _round(metrics.get("win_rate_pct") or metrics.get("directional_accuracy_pct")),
    }


def metrics_from_pnls(pnls: list[float], candidate_count: int, unresolved_count: int) -> dict[str, Any]:
    wins = [value for value in pnls if value > 0]
    losses = [value for value in pnls if value < 0]
    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    exact_count = len(pnls)
    coverage = (exact_count / candidate_count * 100.0) if candidate_count else 0.0
    if gross_loss > 0:
        profit_factor = gross_win / gross_loss
    elif gross_win > 0:
        profit_factor = gross_win
    else:
        profit_factor = 0.0
    return {
        "candidates": candidate_count,
        "exact_trusted_priced_trades": exact_count,
        "unresolved_rows": unresolved_count,
        "quote_coverage": round(coverage, 2),
        "profit_factor": round(profit_factor, 2),
        "avg_pnl": round(sum(pnls) / exact_count, 2) if exact_count else 0.0,
        "median_pnl": round(float(median(pnls)), 2) if pnls else None,
        "win_rate": round(len(wins) / exact_count * 100.0, 2) if exact_count else 0.0,
        "gross_win": round(gross_win, 2),
        "gross_loss": round(gross_loss, 2),
    }


def sample_status(exact_count: int) -> str:
    if exact_count <= 0:
        return "none"
    if exact_count < 10:
        return "thin"
    if exact_count < 25:
        return "adequate"
    return "robust"


def _zero_bid_rate_from_side_aware(side_aware: dict[str, Any] | None) -> float | None:
    if not isinstance(side_aware, dict):
        return None
    modes = side_aware.get("modes") or {}
    conservative = modes.get("conservative") or {}
    direct = conservative.get("zero_bid_exit_rate_pct")
    if direct is not None:
        return _round(direct)
    combined_priced = _safe_int(conservative.get("combined_priced_count") or conservative.get("combined_lane_a_priced_count"))
    zero_priced = _safe_int(conservative.get("zero_bid_priced_count"))
    if combined_priced:
        return round((zero_priced / combined_priced) * 100.0, 2)
    return None


def _lane_a_zero_bid_rate(multilane_payload: dict[str, Any]) -> float | None:
    side_aware = multilane_payload.get("side_aware_zero_bid_replay") or {}
    return _zero_bid_rate_from_side_aware(side_aware)


def classify_symbol_lane(card: dict[str, Any]) -> tuple[str, list[str]]:
    metrics = card.get("metrics") or {}
    exact = _safe_int(metrics.get("exact_trusted_priced_trades"))
    candidates = _safe_int(metrics.get("candidates"))
    unresolved = _safe_int(metrics.get("unresolved_rows"))
    pf = _safe_float(metrics.get("profit_factor"))
    avg = _safe_float(metrics.get("avg_pnl"))
    coverage = _safe_float(metrics.get("quote_coverage"))
    evidence_class = str(card.get("evidence_class") or BLOCKED_NO_DATA)
    source_tiers = set(card.get("source_tiers") or [])
    bp_decision = str(card.get("bp_decision") or "")
    guardrail_hits = _safe_int((card.get("guardrail_hits") or {}).get("combined_promoted_top_negative_blocked_count"))
    zero_bid_rate = card.get("zero_bid_exit_rate")
    sample = sample_status(exact)

    reasons: list[str] = []
    if evidence_class != TRUSTED_EXACT:
        reasons.append(f"evidence_class:{evidence_class}")
    if sample in {"none", "thin"}:
        reasons.append(f"sample_status:{sample}")
    if coverage < 97.5 and candidates:
        reasons.append("quote_coverage_below_97_5")
    if unresolved > 0:
        reasons.append("unresolved_rows_remain")
    if zero_bid_rate is not None and _safe_float(zero_bid_rate) > 2.0:
        reasons.append("zero_bid_exit_rate_above_2")
    if guardrail_hits > 0:
        reasons.append("trading_desk_guardrail_negative_concentration")

    if candidates == 0 and exact == 0:
        return "needs-paper" if source_tiers else "not_applicable", reasons or ["no_candidate_evidence"]

    if bp_decision == "keep-in-current-lane":
        return "keep", reasons or ["bullish_pullback_sab_confidence_keep"]

    if bp_decision == "remove":
        if exact >= 6 and pf < 1.0 and avg < 0:
            return "rejected", reasons + ["bullish_pullback_remove_negative_exact_evidence"]
        return "quarantine", reasons + ["bullish_pullback_remove_queue_recommendation"]

    if evidence_class != TRUSTED_EXACT:
        return "needs-paper", reasons

    if zero_bid_rate is not None and _safe_float(zero_bid_rate) > 10.0:
        return "quarantine", reasons

    if exact >= 6 and pf < 1.0 and avg < 0:
        return "rejected", reasons + ["adequate_negative_exact_intraday_evidence"]

    if guardrail_hits > 0 and not (pf >= 1.5 and avg > 0 and exact >= 10):
        return "quarantine", reasons

    if pf >= 1.5 and avg > 0:
        if exact >= 10 and coverage >= 90.0:
            return "keep", reasons or ["positive_exact_intraday_symbol_lane"]
        return "watch", reasons + ["positive_but_thin_or_incomplete"]

    if exact > 0:
        return "watch" if avg > 0 else "rejected", reasons or ["weak_exact_intraday_evidence"]

    return "needs-paper", reasons or ["no_exact_priced_rows"]


def _card_key(lane_id: str, symbol: str) -> str:
    return f"{lane_id}:{symbol}"


def _new_card(lane_id: str, lane_family: str, strategy_logic_id: str, symbol: str) -> dict[str, Any]:
    return {
        "lane_id": lane_id,
        "lane_family": lane_family,
        "strategy_logic_id": strategy_logic_id,
        "symbol": symbol,
        "sleeve_id": f"{lane_id}:{symbol}",
        "status": None,
        "evidence_class": BLOCKED_NO_DATA,
        "status_reason": "",
        "reason_codes": [],
        "source_artifacts": [],
        "source_tiers": [],
        "metrics": metrics_from_pnls([], 0, 0),
        "sample_status": "none",
        "metric_source": "raw_trades",
        "stress_pf": None,
        "rolling_oos_status": None,
        "zero_bid_exit_rate": None,
        "guardrail_hits": {},
        "open_position_state": {},
        "executable_exit_pnl": None,
        "paper_or_mark_pnl": None,
        "blockers": [],
        "next_step": "",
        "_pnls": [],
        "_candidate_count": 0,
        "_unresolved_count": 0,
        "_evidence_rank": 0,
    }


def _evidence_rank(evidence_class: str) -> int:
    return {
        TRUSTED_EXACT: 6,
        LIVE_SCAN_EXACT: 5,
        TRUSTED_UNRESOLVED: 4,
        RESEARCH_BACKFILL: 3,
        DAILY_RESEARCH: 2,
        MARK_OR_STALE: 1,
        BLOCKED_NO_DATA: 0,
    }.get(evidence_class, 0)


def _merge_list(row: dict[str, Any], key: str, value: str | None) -> None:
    if not value:
        return
    if value not in row[key]:
        row[key].append(value)


def _set_evidence(row: dict[str, Any], evidence_class: str) -> None:
    if _evidence_rank(evidence_class) > _safe_int(row.get("_evidence_rank")):
        row["evidence_class"] = evidence_class
        row["_evidence_rank"] = _evidence_rank(evidence_class)


def collect_run_sources(
    *,
    bullish_ticker_audit: dict[str, Any],
    multilane: dict[str, Any],
    all_planned: dict[str, Any],
    all_planned_partial: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    sources: dict[tuple[str, str], dict[str, Any]] = {}

    def add_source(source: dict[str, Any]) -> None:
        path = _abs_path(source.get("run_path") or source.get("source_result_path") or source.get("result_path"))
        if path is None:
            return
        key = (str(source["lane_id"]), str(path.resolve()))
        if key not in sources:
            source["run_path"] = str(path)
            sources[key] = source

    for lane in multilane.get("lanes") or []:
        add_source(
            {
                "lane_id": str(lane.get("lane_id") or ""),
                "lane_family": str(lane.get("family") or lane.get("lane_id") or ""),
                "strategy_logic_id": str(lane.get("source_playbook") or lane.get("lane_id") or ""),
                "source_tier": "exact_intraday_run_artifacts",
                "source_result_path": lane.get("source_result_path"),
                "stress_pf": (lane.get("robustness") or {}).get("stress_5pct_per_side_profit_factor"),
                "rolling_oos_status": (lane.get("robustness") or {}).get("rolling_status"),
            }
        )

    for payload in [all_planned, all_planned_partial or {}]:
        for variant in payload.get("variants") or []:
            variant_id = str(variant.get("variant_id") or "")
            if not variant_id:
                continue
            add_source(
                {
                    "lane_id": variant_id,
                    "lane_family": str(variant.get("lane_id") or variant_id),
                    "strategy_logic_id": variant_id,
                    "source_tier": "lane_lab_all_planned_research",
                    "source_result_path": variant.get("run_path"),
                    "stress_pf": (variant.get("robustness") or {}).get("stress_5pct_per_side_profit_factor"),
                    "rolling_oos_status": (variant.get("robustness") or {}).get("rolling_status"),
                    "zero_bid_exit_rate": _zero_bid_rate_from_side_aware(variant.get("side_aware_zero_bid_replay")),
                    "worth_status": variant.get("worth_status"),
                }
            )

    for row in bullish_ticker_audit.get("rows") or []:
        add_source(
            {
                "lane_id": "bullish_pullback_observation",
                "lane_family": "bullish_pullback_observation",
                "strategy_logic_id": "per_ticker_bullish_pullback",
                "source_tier": "bullish_pullback_ticker_confidence_layer_artifacts",
                "source_result_path": row.get("result_path"),
                "symbol_hint": row.get("ticker"),
                "bp_decision": row.get("decision"),
            }
        )

    lane_a_zero_bid = _lane_a_zero_bid_rate(multilane)
    for source in sources.values():
        if "lane_a" in str(source.get("lane_id") or "").lower() and source.get("zero_bid_exit_rate") is None:
            source["zero_bid_exit_rate"] = lane_a_zero_bid
    return list(sources.values())


def add_run_source_cards(cards: dict[str, dict[str, Any]], source: dict[str, Any]) -> None:
    run_path = _abs_path(source.get("run_path"))
    if run_path is None or not run_path.exists():
        return
    run = _load_json(run_path)
    evidence_class = _proof_grade_for_run(run)
    lane_id = str(source.get("lane_id") or run.get("playbook") or "unknown_lane")
    lane_family = str(source.get("lane_family") or lane_id)
    strategy_logic_id = str(source.get("strategy_logic_id") or run.get("playbook") or lane_id)
    source_artifact = _rel(run_path)

    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"pnls": [], "candidates": 0, "unresolved": 0})
    for trade in run.get("trades") or []:
        symbol = normalize_symbol(trade.get("ticker"))
        if not symbol:
            continue
        grouped[symbol]["candidates"] += 1
        if _is_exact_imported_trade(trade, evidence_class):
            grouped[symbol]["pnls"].append(_trade_pnl(trade))
    for trade in run.get("unpriced_trades") or []:
        symbol = normalize_symbol(trade.get("ticker"))
        if not symbol:
            continue
        grouped[symbol]["candidates"] += 1
        grouped[symbol]["unresolved"] += 1

    for symbol, data in grouped.items():
        key = _card_key(lane_id, symbol)
        card = cards.setdefault(key, _new_card(lane_id, lane_family, strategy_logic_id, symbol))
        _merge_list(card, "source_artifacts", source_artifact)
        _merge_list(card, "source_tiers", str(source.get("source_tier") or "exact_intraday_run_artifacts"))
        card["_pnls"].extend(data["pnls"])
        card["_candidate_count"] += data["candidates"]
        card["_unresolved_count"] += data["unresolved"]
        if data["pnls"]:
            _set_evidence(card, evidence_class)
        elif data["unresolved"] and evidence_class == TRUSTED_EXACT:
            _set_evidence(card, TRUSTED_UNRESOLVED)
        else:
            _set_evidence(card, evidence_class)
        card["stress_pf"] = card["stress_pf"] if card["stress_pf"] is not None else source.get("stress_pf")
        card["rolling_oos_status"] = card["rolling_oos_status"] or source.get("rolling_oos_status")
        card["zero_bid_exit_rate"] = card["zero_bid_exit_rate"] if card["zero_bid_exit_rate"] is not None else source.get(
            "zero_bid_exit_rate"
        )
        if source.get("worth_status"):
            card.setdefault("source_worth_statuses", [])
            if source["worth_status"] not in card["source_worth_statuses"]:
                card["source_worth_statuses"].append(source["worth_status"])


def enrich_with_bullish_ticker_audit(
    cards: dict[str, dict[str, Any]],
    universe: dict[str, dict[str, Any]],
    payload: dict[str, Any],
) -> dict[str, Any]:
    rows_by_symbol = {}
    for row in payload.get("rows") or []:
        symbol = normalize_symbol(row.get("ticker"))
        if not symbol:
            continue
        rows_by_symbol[symbol] = row
        add_symbol_source(
            universe,
            symbol,
            "bullish_pullback_ticker_confidence_layer_artifacts",
            f"bullish_pullback_ticker_audit:{row.get('decision')}",
        )
        if row.get("decision") == "keep-in-current-lane":
            add_symbol_source(universe, symbol, "current_queue/configured_scan_universe", "bullish_pullback_keep_queue")
        key = _card_key("bullish_pullback_observation", symbol)
        card = cards.setdefault(
            key,
            _new_card("bullish_pullback_observation", "bullish_pullback_observation", "per_ticker_bullish_pullback", symbol),
        )
        card["bp_decision"] = row.get("decision")
        card["bp_recommended_lane"] = row.get("recommended_lane")
        card["confidence_tier"] = row.get("confidence_tier")
        card["status_reason"] = row.get("rationale") or ""
        card["next_step"] = row.get("next_action") or ""
        _merge_list(card, "source_tiers", "bullish_pullback_ticker_confidence_layer_artifacts")
        if row.get("result_path"):
            _merge_list(card, "source_artifacts", _rel(row.get("result_path")))
        if not card["_candidate_count"] and _safe_int(row.get("candidate_trade_count")):
            card["_candidate_count"] = _safe_int(row.get("candidate_trade_count"))
            card["_unresolved_count"] = _safe_int(row.get("unpriced_trade_count"))
            exact = _safe_int(row.get("exact_quoted_trade_count"))
            avg = _safe_float(row.get("avg_pnl_pct"))
            card["_pnls"] = [avg for _ in range(exact)] if exact and avg else []
            if exact:
                _set_evidence(card, TRUSTED_EXACT)
    return rows_by_symbol


def _top_negative_guardrail_hits(payload: dict[str, Any]) -> dict[str, int]:
    combined = payload.get("combined_promoted_guardrails") or {}
    return {normalize_symbol(k): _safe_int(v) for k, v in (combined.get("top_negative_tickers_blocked") or {}).items() if normalize_symbol(k)}


def enrich_with_guardrails(cards: dict[str, dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
    hits = _top_negative_guardrail_hits(payload)
    for card in cards.values():
        symbol = card["symbol"]
        if symbol in hits:
            card["guardrail_hits"]["combined_promoted_top_negative_blocked_count"] = hits[symbol]
    combined = payload.get("combined_promoted_guardrails") or {}
    return {
        "promoted_guardrails": payload.get("promoted_guardrails") or [],
        "baseline": payload.get("baseline") or {},
        "kept": combined.get("kept") or {},
        "blocked": combined.get("blocked") or {},
        "top_negative_tickers_blocked": hits,
    }


def _risk_rows_by_symbol(payload: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for key in ("actionable_positions", "top_negative_open_positions", "attention_trades"):
        for row in payload.get(key) or []:
            symbol = normalize_symbol(row.get("ticker"))
            if symbol:
                rows[symbol].append(row)
    return rows


def enrich_with_position_risk(
    cards: dict[str, dict[str, Any]],
    universe: dict[str, dict[str, Any]],
    open_risk: dict[str, Any],
    suggested_risk: dict[str, Any],
) -> dict[str, Any]:
    open_rows = _risk_rows_by_symbol(open_risk)
    suggested_rows = _risk_rows_by_symbol(suggested_risk)
    symbols = set(open_rows) | set(suggested_rows)
    for symbol in symbols:
        add_symbol_source(universe, symbol, "open_tracked_positions_and_current_suggested_trades", "risk_audit")
        matching_keys = [key for key, card in cards.items() if card["symbol"] == symbol]
        if not matching_keys:
            key = _card_key("trading_desk_open_risk", symbol)
            cards[key] = _new_card("trading_desk_open_risk", "trading_desk", "open_position_and_suggested_trade_risk", symbol)
            matching_keys = [key]
        for key in matching_keys:
            card = cards[key]
            _merge_list(card, "source_tiers", "tracked_and_suggested_trade_audits")
            if open_rows.get(symbol):
                row = open_rows[symbol][0]
                card["open_position_state"] = {
                    "open_risk_rows": len(open_rows[symbol]),
                    "first_action_bucket": row.get("action_bucket"),
                    "first_pricing_state": row.get("pricing_state"),
                    "first_next_safe_action": row.get("next_safe_action"),
                    "first_position_id": row.get("id"),
                }
                card["executable_exit_pnl"] = row.get("current_pnl_pct") if row.get("exit_execution_price") is not None else None
                card["paper_or_mark_pnl"] = row.get("mark_pnl_pct")
                if row.get("exit_execution_price") is None:
                    _set_evidence(card, MARK_OR_STALE)
            if suggested_rows.get(symbol):
                row = suggested_rows[symbol][0]
                card.setdefault("suggested_trade_state", {})
                card["suggested_trade_state"] = {
                    "attention_rows": len(suggested_rows[symbol]),
                    "first_action_bucket": row.get("action_bucket"),
                    "first_pricing_state": row.get("pricing_state"),
                    "first_next_safe_action": row.get("next_safe_action"),
                    "first_trade_id": row.get("id"),
                }
                if row.get("exit_execution_price") is None:
                    _set_evidence(card, MARK_OR_STALE)
    return {
        "open_position_summary": open_risk.get("summary") or {},
        "open_position_action_counts": open_risk.get("action_counts") or {},
        "open_position_actionable_ids": open_risk.get("actionable_position_ids") or [],
        "suggested_trade_summary": suggested_risk.get("summary") or {},
        "suggested_trade_action_counts": suggested_risk.get("action_counts") or {},
        "suggested_trade_attention_ids": suggested_risk.get("attention_trade_ids") or [],
    }


def collect_lane_lab_universe(universe: dict[str, dict[str, Any]], payload: dict[str, Any]) -> dict[str, Any]:
    lane_count = 0
    for lane in payload.get("lanes") or []:
        lane_id = str(lane.get("id") or "")
        if lane_id == "ai_commodity_infra_observation":
            continue
        lane_count += 1
        for field in ("required_symbols", "symbols", "allowed_tickers"):
            for value in lane.get(field) or []:
                add_symbol_source(universe, value, "lane_lab_all_planned_research", f"lane_lab:{lane_id}:{field}")
        metrics = lane.get("metrics") or {}
        for row in metrics.get("by_ticker") or []:
            add_symbol_source(universe, row.get("ticker"), "historical_paper_research_backfill", f"lane_lab:{lane_id}:by_ticker")
    return {"regular_lane_count": lane_count}


def finalize_cards(cards: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for card in cards.values():
        card["metrics"] = metrics_from_pnls(card["_pnls"], _safe_int(card["_candidate_count"]), _safe_int(card["_unresolved_count"]))
        card["sample_status"] = sample_status(_safe_int(card["metrics"]["exact_trusted_priced_trades"]))
        status, reasons = classify_symbol_lane(card)
        card["status"] = status
        card["reason_codes"] = sorted(set(reasons))
        card["blockers"] = card["reason_codes"]
        if not card.get("status_reason"):
            card["status_reason"] = "; ".join(card["reason_codes"])
        if not card.get("next_step"):
            card["next_step"] = _default_next_step(card)
        for hidden in ("_pnls", "_candidate_count", "_unresolved_count", "_evidence_rank"):
            card.pop(hidden, None)
        card["source_artifacts"] = sorted(card.get("source_artifacts") or [])
        card["source_tiers"] = sorted(card.get("source_tiers") or [])
        rows.append(card)
    rows.sort(key=lambda row: (str(row.get("lane_family")), str(row.get("lane_id")), str(row.get("symbol"))))
    return rows


def _default_next_step(card: dict[str, Any]) -> str:
    status = str(card.get("status") or "")
    if status == "keep":
        return "Keep in the relevant paper-shadow queue; do not call production-proof unless the lane-level proof gates clear."
    if status == "watch":
        return "Keep as a watch/scout sleeve and collect more exact or forward-paper evidence before queue changes."
    if status == "quarantine":
        return "Keep out of current picks under current guardrails until a new frozen hypothesis clears exact evidence."
    if status == "rejected":
        return "Do not retune this failed shape as a count hack; reopen only with a new causal hypothesis."
    if status == "needs-paper":
        return "Collect exact replay rows or forward paper logs before ranking this symbol-lane pair."
    return "No action for this symbol-lane pair."


def _best_rows(rows: list[dict[str, Any]], family_filter: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    filtered = [
        row
        for row in rows
        if row.get("status") in {"keep", "watch"}
        and _safe_int((row.get("metrics") or {}).get("exact_trusted_priced_trades")) > 0
        and _safe_float((row.get("metrics") or {}).get("avg_pnl")) > 0
    ]
    if family_filter:
        needle = family_filter.lower()
        filtered = [
            row
            for row in rows
            if needle in str(row.get("lane_family") or "").lower() or needle in str(row.get("lane_id") or "").lower()
        ]
    return sorted(
        filtered,
        key=lambda row: (
            _safe_int((row.get("metrics") or {}).get("exact_trusted_priced_trades")),
            _safe_float((row.get("metrics") or {}).get("profit_factor")),
            _safe_float((row.get("metrics") or {}).get("avg_pnl")),
        ),
        reverse=True,
    )[:limit]


def _worst_rows(rows: list[dict[str, Any]], family_filter: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    filtered = [row for row in rows if _safe_int((row.get("metrics") or {}).get("exact_trusted_priced_trades")) > 0]
    if family_filter:
        needle = family_filter.lower()
        filtered = [
            row
            for row in filtered
            if needle in str(row.get("lane_family") or "").lower() or needle in str(row.get("lane_id") or "").lower()
        ]
    return sorted(
        filtered,
        key=lambda row: (
            _safe_float((row.get("metrics") or {}).get("avg_pnl")),
            _safe_float((row.get("metrics") or {}).get("profit_factor")),
        ),
    )[:limit]


def build_report(
    *,
    bullish_ticker_audit_path: Path = BULLISH_TICKER_AUDIT,
    multilane_path: Path = REGULAR_MULTILANE,
    all_planned_path: Path = ALL_PLANNED_LATEST,
    all_planned_partial_path: Path = ALL_PLANNED_PARTIAL,
    lane_lab_path: Path = LANE_LAB_LATEST,
    guardrails_path: Path = TRADING_DESK_GUARDRAILS,
    open_position_risk_path: Path = OPEN_POSITION_RISK,
    suggested_trade_risk_path: Path = SUGGESTED_TRADE_RISK,
    include_playbooks: bool = True,
) -> dict[str, Any]:
    inputs = [
        input_manifest_entry(bullish_ticker_audit_path, "bullish_pullback_ticker_audit"),
        input_manifest_entry(multilane_path, "regular_options_multilane"),
        input_manifest_entry(all_planned_path, "all_planned_sleeves_full"),
        input_manifest_entry(all_planned_partial_path, "all_planned_sleeves_partial"),
        input_manifest_entry(lane_lab_path, "lane_lab"),
        input_manifest_entry(guardrails_path, "trading_desk_guardrails"),
        input_manifest_entry(open_position_risk_path, "open_position_risk"),
        input_manifest_entry(suggested_trade_risk_path, "suggested_trade_close_risk"),
    ]

    bullish_ticker_audit = _load_json(bullish_ticker_audit_path) if bullish_ticker_audit_path.exists() else {}
    multilane = _load_json(multilane_path) if multilane_path.exists() else {}
    all_planned = _load_json(all_planned_path) if all_planned_path.exists() else {}
    all_planned_partial = _load_fresh_partial_payload(all_planned_path, all_planned_partial_path)
    lane_lab = _load_json(lane_lab_path) if lane_lab_path.exists() else {}
    guardrails = _load_json(guardrails_path) if guardrails_path.exists() else {}
    open_risk = _load_json(open_position_risk_path) if open_position_risk_path.exists() else {}
    suggested_risk = _load_json(suggested_trade_risk_path) if suggested_trade_risk_path.exists() else {}

    universe: dict[str, dict[str, Any]] = {}
    playbook_readback = collect_playbook_universe(universe) if include_playbooks else {"status": "skipped"}
    lane_lab_readback = collect_lane_lab_universe(universe, lane_lab)

    cards: dict[str, dict[str, Any]] = {}
    run_sources = collect_run_sources(
        bullish_ticker_audit=bullish_ticker_audit,
        multilane=multilane,
        all_planned=all_planned,
        all_planned_partial=all_planned_partial,
    )
    for source in run_sources:
        add_run_source_cards(cards, source)
    bp_rows_by_symbol = enrich_with_bullish_ticker_audit(cards, universe, bullish_ticker_audit)
    guardrail_readback = enrich_with_guardrails(cards, guardrails)
    open_position_readback = enrich_with_position_risk(cards, universe, open_risk, suggested_risk)

    for symbol in guardrail_readback.get("top_negative_tickers_blocked") or {}:
        add_symbol_source(universe, symbol, "tracked_and_suggested_trade_audits", "trading_desk_guardrail_negative_concentration")

    lane_symbol_rows = finalize_cards(cards)
    status_counts = Counter(str(row.get("status")) for row in lane_symbol_rows)
    evidence_counts = Counter(str(row.get("evidence_class")) for row in lane_symbol_rows)
    reason_counts = Counter(reason for row in lane_symbol_rows for reason in row.get("reason_codes") or [])

    bp_rows = [row for row in lane_symbol_rows if row.get("lane_id") == "bullish_pullback_observation"]
    bp_carriers = [row["symbol"] for row in bp_rows if row.get("status") == "keep"]
    queue_removals = sorted(
        symbol for symbol, row in bp_rows_by_symbol.items() if str(row.get("decision") or "") in {"remove"}
    )
    queue_quarantine = sorted(
        row["symbol"]
        for row in bp_rows
        if row.get("status") in {"quarantine", "rejected"} and row["symbol"] not in queue_removals
    )
    high_beta_rows = [
        row
        for row in lane_symbol_rows
        if row["symbol"] in HIGH_BETA_SYMBOLS or "high_beta" in str(row.get("lane_family") or "").lower()
    ]
    high_beta_real_crushers = [
        {
            "symbol": row["symbol"],
            "lane_id": row["lane_id"],
            "status": row["status"],
            "exact": row["metrics"]["exact_trusted_priced_trades"],
            "profit_factor": row["metrics"]["profit_factor"],
            "avg_pnl": row["metrics"]["avg_pnl"],
            "reason_codes": row["reason_codes"],
        }
        for row in high_beta_rows
        if row.get("status") == "keep"
        and _safe_int(row["metrics"].get("exact_trusted_priced_trades")) >= 10
        and _safe_float(row["metrics"].get("quote_coverage")) >= 90.0
        and _safe_float(row["metrics"].get("profit_factor")) >= 1.5
        and _safe_float(row["metrics"].get("avg_pnl")) > 0
        and not any(reason in row.get("reason_codes", []) for reason in ("zero_bid_exit_rate_above_2", "sample_status:thin"))
    ][:20]
    high_beta_noisy_or_failed = [
        {
            "symbol": row["symbol"],
            "lane_id": row["lane_id"],
            "status": row["status"],
            "exact": row["metrics"]["exact_trusted_priced_trades"],
            "profit_factor": row["metrics"]["profit_factor"],
            "avg_pnl": row["metrics"]["avg_pnl"],
            "reason_codes": row["reason_codes"],
        }
        for row in high_beta_rows
        if row.get("status") in {"quarantine", "rejected"}
        or "sample_status:thin" in row.get("reason_codes", [])
        or "zero_bid_exit_rate_above_2" in row.get("reason_codes", [])
    ][:30]

    universe_rows = sorted(universe.values(), key=lambda row: row["symbol"])
    report = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "scope": "regular_supervised_options_symbol_sleeves",
        "proof_policy": {
            "proof_grade_class": TRUSTED_EXACT,
            "strict_proof_claims_require": [
                "exact trusted intraday OPRA/NBBO contract rows",
                "executable bid/ask spread entry and exit evidence",
                "no unresolved candidates in the claimed proof set",
                "separate executable exit P&L from paper or display marks",
            ],
            "disallowed_for_production_proof": [
                DAILY_RESEARCH,
                RESEARCH_BACKFILL,
                MARK_OR_STALE,
                TRUSTED_UNRESOLVED,
                "midpoint_only",
                "last_trade",
                "stale_snapshot",
            ],
        },
        "inputs": inputs,
        "source_precedence": SOURCE_PRECEDENCE,
        "source_readback": {
            "playbooks": playbook_readback,
            "lane_lab": lane_lab_readback,
            "run_source_count": len(run_sources),
        },
        "universe": {
            "symbol_count": len(universe_rows),
            "symbols": universe_rows,
            "source_tier_counts": dict(
                sorted(Counter(tier for row in universe_rows for tier in row.get("source_tiers") or []).items())
            ),
        },
        "lane_symbol_rows": lane_symbol_rows,
        "classification_counts": dict(sorted(status_counts.items())),
        "evidence_class_counts": dict(sorted(evidence_counts.items())),
        "queues": {
            "bullish_pullback_keep": (bullish_ticker_audit.get("symbols") or {}).get("keep_in_current_lane", []),
            "bullish_pullback_move_to_frozen_hypotheses": (bullish_ticker_audit.get("symbols") or {}).get(
                "move_to_different_lane", []
            ),
            "bullish_pullback_remove_recommendations": queue_removals,
            "bullish_pullback_quarantine_or_rejected": queue_quarantine,
            "queue_changes_are_recommendations_only": True,
        },
        "blockers": {
            "reason_code_counts": dict(sorted(reason_counts.items())),
            "top_reason_codes": reason_counts.most_common(12),
        },
        "open_position_risk": open_position_readback,
        "final_readback": {
            "tracked_symbol_count": len(universe_rows),
            "lane_symbol_row_count": len(lane_symbol_rows),
            "bullish_pullback_carrier_symbols": bp_carriers,
            "bullish_high_beta_real_crushers": high_beta_real_crushers,
            "bullish_high_beta_noisy_or_failed": high_beta_noisy_or_failed,
            "queue_remove_recommendations": queue_removals,
            "top_blockers": reason_counts.most_common(8),
            "best_rows": _best_rows(lane_symbol_rows, limit=12),
            "worst_rows": _worst_rows(lane_symbol_rows, limit=12),
        },
    }
    return report


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ")


def _metrics_cell(row: dict[str, Any]) -> list[str]:
    metrics = row.get("metrics") or {}
    return [
        str(metrics.get("exact_trusted_priced_trades", 0)),
        str(metrics.get("candidates", 0)),
        str(metrics.get("unresolved_rows", 0)),
        str(metrics.get("quote_coverage", 0.0)),
        str(metrics.get("profit_factor", 0.0)),
        str(metrics.get("avg_pnl", 0.0)),
    ]


def _table_rows(rows: list[dict[str, Any]], limit: int = 40) -> list[str]:
    lines = [
        "| Symbol | Lane | Status | Evidence | Exact | Cand | Unres | Cov % | PF | Avg % | Reason |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows[:limit]:
        reason = ", ".join((row.get("reason_codes") or [])[:3])
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(row.get("symbol")),
                    _fmt(row.get("lane_id")),
                    _fmt(row.get("status")),
                    _fmt(row.get("evidence_class")),
                    *_metrics_cell(row),
                    _fmt(reason),
                ]
            )
            + " |"
        )
    return lines


def render_markdown(report: dict[str, Any]) -> str:
    rows = report.get("lane_symbol_rows") or []
    bp_rows = [row for row in rows if row.get("lane_id") == "bullish_pullback_observation"]
    bp_rows = sorted(bp_rows, key=lambda row: (str(row.get("status")), -_safe_int((row.get("metrics") or {}).get("exact_trusted_priced_trades"))))
    high_beta_rows = [
        row
        for row in rows
        if row.get("symbol") in HIGH_BETA_SYMBOLS or "high_beta" in str(row.get("lane_family") or "").lower()
    ]
    tracked_winner_rows = [
        row
        for row in rows
        if "tracked_winner" in str(row.get("lane_family") or "").lower()
        or "tracked_winner" in str(row.get("lane_id") or "").lower()
    ]
    sector_rows = [
        row
        for row in rows
        if row.get("symbol") in INDEX_SECTOR_SYMBOLS
        or any(token in str(row.get("lane_family") or "").lower() for token in ("sector", "etf", "index", "iwm", "tlt", "xle", "xlf", "smh", "kre"))
    ]
    final = report.get("final_readback") or {}
    open_risk = report.get("open_position_risk") or {}
    lines = [
        "# Regular Options Symbol Sleeves",
        "",
        "This report is generated from `scripts/build_regular_options_symbol_sleeves.py`. It is a per-symbol audit/reporting layer under existing regular supervised options lanes, not a ticker-specific strategy-tuning surface.",
        "",
        "## Summary",
        "",
        f"- Tracked symbols found: `{final.get('tracked_symbol_count')}`.",
        f"- Symbol-lane rows: `{final.get('lane_symbol_row_count')}`.",
        f"- Classification counts: `{json.dumps(report.get('classification_counts') or {}, sort_keys=True)}`.",
        f"- Evidence classes: `{json.dumps(report.get('evidence_class_counts') or {}, sort_keys=True)}`.",
        f"- Bullish Pullback carrier symbols: `{', '.join(final.get('bullish_pullback_carrier_symbols') or []) or 'none'}`.",
        f"- Queue removals are recommendations only: `{report.get('queues', {}).get('queue_changes_are_recommendations_only')}`.",
        "",
        "## Proof Policy",
        "",
        "- Strict proof claims require exact trusted intraday OPRA/NBBO contract rows with executable bid/ask evidence.",
        "- Daily/EOD, research backfill, stale/display marks, unresolved candidates, midpoint-only, and last-trade rows remain non-production proof.",
        "- Executable exit P&L is kept separate from paper/mark P&L in the open-risk readback.",
        "",
        "## Best Rows",
        "",
        *_table_rows(final.get("best_rows") or [], limit=12),
        "",
        "## Worst Rows",
        "",
        *_table_rows(final.get("worst_rows") or [], limit=12),
        "",
        "## Bullish Pullback",
        "",
        f"- Keep queue: `{', '.join(report.get('queues', {}).get('bullish_pullback_keep') or []) or 'none'}`.",
        f"- Move to frozen hypotheses: `{', '.join(report.get('queues', {}).get('bullish_pullback_move_to_frozen_hypotheses') or []) or 'none'}`.",
        f"- Remove recommendations: `{', '.join(report.get('queues', {}).get('bullish_pullback_remove_recommendations') or []) or 'none'}`.",
        "",
        *_table_rows(bp_rows, limit=80),
        "",
        "## Bullish / High-Beta",
        "",
        "High-beta upside is treated as a question, not an assumption. Rows below are exact-option evidence first; priced-only or zero-bid-damaged rows should not be called crushers.",
        "",
        *_table_rows(sorted(high_beta_rows, key=lambda row: (row.get("symbol"), row.get("lane_id"))), limit=80),
        "",
        "## Tracked Winner",
        "",
        *_table_rows(sorted(tracked_winner_rows, key=lambda row: (row.get("symbol"), row.get("lane_id"))), limit=80),
        "",
        "## Sector / Index ETF",
        "",
        *_table_rows(sorted(sector_rows, key=lambda row: (row.get("symbol"), row.get("lane_id"))), limit=80),
        "",
        "## Open Position And Suggested-Trade Risk",
        "",
        f"- Open-position summary: `{json.dumps(open_risk.get('open_position_summary') or {}, sort_keys=True)}`.",
        f"- Open-position actionable ids: `{json.dumps(open_risk.get('open_position_actionable_ids') or [])}`.",
        f"- Suggested-trade summary: `{json.dumps(open_risk.get('suggested_trade_summary') or {}, sort_keys=True)}`.",
        f"- Suggested-trade attention ids: `{json.dumps(open_risk.get('suggested_trade_attention_ids') or [])}`.",
        "",
        "## Blockers",
        "",
    ]
    for reason, count in (report.get("blockers") or {}).get("top_reason_codes") or []:
        lines.append(f"- `{reason}`: `{count}` rows.")
    lines.extend(
        [
            "",
            "## Inputs",
            "",
            "| Source | Status | Generated | Path |",
            "|---|---|---|---|",
        ]
    )
    for entry in report.get("inputs") or []:
        lines.append(
            "| "
            + " | ".join(
                [
                    _fmt(entry.get("source_type")),
                    _fmt(entry.get("status")),
                    _fmt(entry.get("generated_at") or entry.get("mtime_utc")),
                    _fmt(entry.get("path")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = OUTPUT_DIR, docs_report: Path = DOCS_REPORT) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"regular_options_symbol_sleeves_{stamp}.json"
    latest_json = output_dir / "latest.json"
    md_path = output_dir / f"regular_options_symbol_sleeves_{stamp}.md"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": str(json_path),
        "latest_json": str(latest_json),
        "markdown": str(md_path),
        "latest_markdown": str(latest_md),
        "docs_report": str(docs_report),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    payload = json.dumps(report_with_artifacts, indent=2, sort_keys=True)
    markdown = render_markdown(report_with_artifacts)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build regular options per-symbol sleeve cards.")
    parser.add_argument("--json", action="store_true", help="Print the generated report JSON.")
    parser.add_argument("--no-write", action="store_true", help="Build without writing artifacts.")
    args = parser.parse_args(argv)

    report = build_report()
    if not args.no_write:
        report["artifacts"] = write_outputs(report)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif not args.no_write:
        print(f"wrote {report['artifacts']['latest_json']}")
        print(f"wrote {report['artifacts']['docs_report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
