from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "python-backend"
for candidate in (ROOT, BACKEND_DIR):
    candidate_text = str(candidate)
    if candidate_text not in sys.path:
        sys.path.insert(0, candidate_text)

from local_env import load_local_env
from positions_repository import create_positions_repository
from supervised_scan import LIVE_SCAN_TRUTH_LANE, SCAN_PLAYBOOKS, run_supervised_scan

import options_chatbot as oc


COMMODITY_PLAYBOOK_IDS = {"ai_commodity_infra_observation"}


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _regular_playbook_ids() -> list[str]:
    return [playbook_id for playbook_id in SCAN_PLAYBOOKS if playbook_id not in COMMODITY_PLAYBOOK_IDS]


def _parse_playbooks(value: str | None) -> list[str]:
    if not value:
        return _regular_playbook_ids()
    playbooks = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in playbooks if item not in SCAN_PLAYBOOKS]
    if unknown:
        raise ValueError(f"Unknown playbook(s): {', '.join(unknown)}")
    forbidden = [item for item in playbooks if item in COMMODITY_PLAYBOOK_IDS]
    if forbidden:
        raise ValueError(
            "Commodity playbooks are intentionally excluded from this regular-lane audit: "
            + ", ".join(forbidden)
        )
    return playbooks


def _decision(value: Any) -> str:
    normalized = str(value or "clear").strip().lower()
    return normalized if normalized in {"clear", "caution", "blocked"} else "unknown"


def _top_counts(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": key, "count": count} for key, count in counter.most_common(limit)]


def _top_drop_detail_counts(counter: Counter[tuple[str, str]], limit: int) -> list[dict[str, Any]]:
    return [
        {"drop_key": key, "detail": detail, "count": count}
        for (key, detail), count in counter.most_common(limit)
    ]


_NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\$?\d+(?:\.\d+)?%?")


def _reason_label(reason: Any) -> str:
    text = " ".join(str(reason or "").split())
    if not text:
        return "unspecified"
    text = _NUMBER_RE.sub("#", text)
    return text[:220]


def _compact_drop_details(drop_key: str, details: Any) -> dict[str, Any]:
    if not isinstance(details, dict):
        return {}
    compact: dict[str, Any] = {}
    for key in (
        "reason",
        "trade_type",
        "signal_variant",
        "candidate_execution_label",
        "required_signal",
        "eligible",
        "history_days",
        "liquidity_tier",
        "avg_volume_20d",
        "avg_dollar_volume_20d",
        "tech_score",
        "min_tech_score",
        "direction_score",
        "min_direction_score",
        "ret5",
        "ret20",
        "price",
        "sma20",
        "sma50",
        "call_entry_momentum_pct",
        "put_entry_momentum_pct",
    ):
        if key in details:
            compact[key] = details.get(key)
    if "allowed_directions" in details:
        compact["allowed_directions"] = list(details.get("allowed_directions") or [])
    liquidity = details.get("liquidity")
    if isinstance(liquidity, dict):
        compact["liquidity_reasons"] = list(liquidity.get("reasons") or [])
        for key in (
            "spread_pct",
            "worst_leg_bid_ask_spread_pct",
            "spread_bid_ask_pct_of_mid",
            "min_leg_volume",
            "min_leg_open_interest",
            "quote_age_hours",
            "max_quote_age_hours",
        ):
            if key in liquidity:
                compact[key] = liquidity.get(key)
    selected_spread = details.get("selected_spread")
    if isinstance(selected_spread, dict):
        for key in ("net_debit", "spread_width", "debit_pct_of_width", "spread_bid_ask_pct_of_mid"):
            if key in selected_spread:
                compact[f"selected_{key}"] = selected_spread.get(key)
    return compact


def _drop_detail_label(drop_key: str, details: Any) -> str:
    compact = _compact_drop_details(drop_key, details)
    if drop_key == "direction_filter":
        trade_type = compact.get("trade_type") or "unknown"
        allowed = ",".join(str(item) for item in compact.get("allowed_directions") or [])
        return f"{trade_type} not in allowed directions {allowed or 'unknown'}"
    if drop_key == "momentum":
        required = compact.get("required_signal")
        if required:
            return str(required)
        return "momentum/trend signal not met"
    if drop_key == "option_liquidity":
        reason = compact.get("reason") or "liquidity_gate"
        liq_reasons = ",".join(str(item) for item in compact.get("liquidity_reasons") or [])
        return f"{reason}: {liq_reasons}" if liq_reasons else str(reason)
    if drop_key == "history_or_liquidity":
        reason = compact.get("reason") or "underlying history/liquidity gate"
        tier = compact.get("liquidity_tier")
        return f"{reason}; tier={tier}" if tier else str(reason)
    if drop_key in {"tech_score", "direction_score"}:
        score = compact.get(drop_key)
        minimum = compact.get(f"min_{drop_key}")
        return f"{drop_key} {score} below {minimum}"
    return _reason_label(compact or details)


def _pick_snapshot(pick: dict[str, Any]) -> dict[str, Any]:
    signal = pick.get("signal_details") if isinstance(pick.get("signal_details"), dict) else {}
    return {
        "ticker": pick.get("ticker"),
        "direction": pick.get("direction") or pick.get("option_type") or pick.get("type"),
        "expiry": pick.get("expiry") or pick.get("expiration_date"),
        "long_strike": pick.get("long_strike"),
        "short_strike": pick.get("short_strike"),
        "net_debit": pick.get("net_debit"),
        "debit_pct_of_width": pick.get("debit_pct_of_width"),
        "quality_score": pick.get("quality_score"),
        "confidence": pick.get("confidence"),
        "ret5": signal.get("ret5") if signal else pick.get("ret5"),
        "guardrail_decision": _decision(pick.get("guardrail_decision")),
        "guardrail_reasons": list(pick.get("guardrail_reasons") or []),
        "suggested_size_tier": pick.get("suggested_size_tier"),
        "proof_eligible": pick.get("proof_eligible"),
        "candidate_execution_label": pick.get("candidate_execution_label"),
    }


def _summarize_scan_result(playbook_id: str, result: dict[str, Any], *, top_limit: int) -> dict[str, Any]:
    candidate_picks = list(result.get("candidate_audit_picks") or [])
    returned_picks = list(result.get("picks") or [])
    decision_counts = Counter(_decision(pick.get("guardrail_decision")) for pick in candidate_picks)
    reason_counts: Counter[str] = Counter()
    blocked_tickers: Counter[str] = Counter()
    clear_tickers: Counter[str] = Counter()
    for pick in candidate_picks:
        decision = _decision(pick.get("guardrail_decision"))
        ticker = str(pick.get("ticker") or "").strip().upper() or "UNKNOWN"
        if decision == "blocked":
            blocked_tickers[ticker] += 1
            for reason in list(pick.get("guardrail_reasons") or []):
                reason_counts[_reason_label(reason)] += 1
        elif decision == "clear":
            clear_tickers[ticker] += 1
    funnel = dict(result.get("scan_funnel") or {})
    drop_counts = dict(funnel.get("drop_counts") or {})
    scan_drop_reasons = result.get("scan_drop_reasons") if isinstance(result.get("scan_drop_reasons"), dict) else {}
    drop_detail_counts: Counter[tuple[str, str]] = Counter()
    drop_tickers_by_detail: dict[tuple[str, str], list[str]] = defaultdict(list)
    drop_samples_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for symbol, payload in sorted(dict(scan_drop_reasons).items()):
        if not isinstance(payload, dict):
            continue
        drop_key = str(payload.get("drop_key") or "unknown")
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        label = _drop_detail_label(drop_key, details)
        detail_key = (drop_key, label)
        drop_detail_counts[detail_key] += 1
        if len(drop_tickers_by_detail[detail_key]) < top_limit:
            drop_tickers_by_detail[detail_key].append(str(symbol))
        if len(drop_samples_by_key[drop_key]) < top_limit:
            drop_samples_by_key[drop_key].append(
                {
                    "ticker": str(symbol),
                    "detail": label,
                    "details": _compact_drop_details(drop_key, details),
                }
            )
    raw_candidates = int(funnel.get("raw_candidates") or result.get("candidate_count") or len(candidate_picks) or 0)
    guardrail_filtered = int(funnel.get("guardrail_filtered_out") or decision_counts.get("blocked", 0) or 0)
    clear_candidates = decision_counts.get("clear", 0)
    block_rate = round((guardrail_filtered / raw_candidates) * 100.0, 2) if raw_candidates else None
    clear_rate = round((clear_candidates / raw_candidates) * 100.0, 2) if raw_candidates else None
    starvation_flag = bool(raw_candidates and clear_candidates == 0 and guardrail_filtered > 0)
    return {
        "playbook_id": playbook_id,
        "label": (result.get("playbook") or {}).get("label"),
        "policy_fail_closed": bool(result.get("policy_fail_closed")),
        "policy_error": result.get("policy_error"),
        "candidate_count": int(result.get("candidate_count") or raw_candidates),
        "returned_count": int(result.get("returned_count") or len(returned_picks)),
        "scan_funnel": funnel,
        "drop_counts": drop_counts,
        "guardrail_decision_counts": dict(result.get("guardrail_decision_counts") or decision_counts),
        "candidate_decision_counts": dict(sorted(decision_counts.items())),
        "block_rate_pct": block_rate,
        "clear_rate_pct": clear_rate,
        "starvation_flag": starvation_flag,
        "top_block_reasons": _top_counts(reason_counts, top_limit),
        "top_upstream_drop_details": [
            {
                **item,
                "tickers": drop_tickers_by_detail.get((item["drop_key"], item["detail"]), []),
            }
            for item in _top_drop_detail_counts(drop_detail_counts, top_limit)
        ],
        "drop_samples_by_key": dict(sorted(drop_samples_by_key.items())),
        "top_blocked_tickers": _top_counts(blocked_tickers, top_limit),
        "top_clear_tickers": _top_counts(clear_tickers, top_limit),
        "returned_picks": [_pick_snapshot(pick) for pick in returned_picks[:top_limit]],
        "top_blocked_candidates": [
            _pick_snapshot(pick)
            for pick in candidate_picks
            if _decision(pick.get("guardrail_decision")) == "blocked"
        ][:top_limit],
    }


def build_report(
    *,
    playbook_ids: list[str],
    n_picks: int,
    watchlist_size: int,
    use_recommended_policy: bool,
    enforce_portfolio_caps: bool,
    truth_lane: str,
    top_limit: int,
) -> dict[str, Any]:
    load_local_env(ROOT)
    repository = create_positions_repository(os.getenv("DATABASE_URL"))
    try:
        market_open_at_run = bool(oc._market_is_open())
    except Exception:
        market_open_at_run = None
    playbook_reports: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for playbook_id in playbook_ids:
        try:
            result = run_supervised_scan(
                scan_func=oc.scan_daily_top_trades,
                positions_repository=repository,
                n_picks=n_picks,
                watchlist_size=watchlist_size,
                playbook_id=playbook_id,
                use_recommended_policy=use_recommended_policy,
                include_blocked_guardrail_picks=True,
                enforce_portfolio_caps=enforce_portfolio_caps,
                truth_lane=truth_lane,
            )
        except Exception as exc:  # keep one data/provider failure from hiding the rest
            errors.append({"playbook_id": playbook_id, "error": str(exc)})
            continue
        playbook_reports.append(_summarize_scan_result(playbook_id, result, top_limit=top_limit))

    totals = Counter()
    starvation_playbooks: list[str] = []
    top_reasons: Counter[str] = Counter()
    top_drops: Counter[str] = Counter()
    top_drop_details: Counter[tuple[str, str]] = Counter()
    top_drop_detail_tickers: dict[tuple[str, str], list[str]] = defaultdict(list)
    zero_candidate_playbooks: list[str] = []
    for report in playbook_reports:
        for key, value in dict(report.get("candidate_decision_counts") or {}).items():
            totals[str(key)] += int(value or 0)
        if report.get("starvation_flag"):
            starvation_playbooks.append(str(report.get("playbook_id")))
        if int(report.get("candidate_count") or 0) == 0:
            zero_candidate_playbooks.append(str(report.get("playbook_id")))
        for item in list(report.get("top_block_reasons") or []):
            top_reasons[str(item.get("value"))] += int(item.get("count") or 0)
        for key, value in dict(report.get("drop_counts") or {}).items():
            top_drops[str(key)] += int(value or 0)
        for item in list(report.get("top_upstream_drop_details") or []):
            detail_key = (str(item.get("drop_key")), str(item.get("detail")))
            top_drop_details[detail_key] += int(item.get("count") or 0)
            for ticker in list(item.get("tickers") or []):
                if len(top_drop_detail_tickers[detail_key]) < top_limit and ticker not in top_drop_detail_tickers[detail_key]:
                    top_drop_detail_tickers[detail_key].append(str(ticker))
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": "regular_supervised_guardrail_starvation",
        "read_only": True,
        "commodity_playbooks_excluded": sorted(COMMODITY_PLAYBOOK_IDS),
        "playbooks": playbook_reports,
        "errors": errors,
        "overall": {
            "playbooks_requested": len(playbook_ids),
            "playbooks_completed": len(playbook_reports),
            "candidate_decision_counts": dict(sorted(totals.items())),
            "starvation_playbooks": starvation_playbooks,
            "zero_candidate_playbooks": zero_candidate_playbooks,
            "top_block_reasons": _top_counts(top_reasons, top_limit),
            "top_drop_counts": _top_counts(top_drops, top_limit),
            "top_upstream_drop_details": [
                {
                    **item,
                    "tickers": top_drop_detail_tickers.get((item["drop_key"], item["detail"]), []),
                }
                for item in _top_drop_detail_counts(top_drop_details, top_limit)
            ],
        },
        "settings": {
            "n_picks": n_picks,
            "watchlist_size": watchlist_size,
            "use_recommended_policy": use_recommended_policy,
            "include_blocked_guardrail_picks": True,
            "enforce_portfolio_caps": enforce_portfolio_caps,
            "truth_lane": truth_lane,
            "market_open_at_run": market_open_at_run,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only regular-lane audit for scan guardrail starvation."
    )
    parser.add_argument("--playbooks", help="Comma-separated regular playbook IDs. Defaults to every non-commodity playbook.")
    parser.add_argument("--n-picks", type=int, default=10)
    parser.add_argument("--watchlist-size", type=int, default=len(getattr(oc, "DEFAULT_WATCHLIST", []) or []))
    parser.add_argument("--use-recommended-policy", action="store_true")
    parser.add_argument("--enforce-portfolio-caps", action="store_true")
    parser.add_argument("--truth-lane", default=LIVE_SCAN_TRUTH_LANE)
    parser.add_argument("--top-limit", type=int, default=8)
    parser.add_argument("--json", action="store_true", help="Print the full report JSON.")
    parser.add_argument("--no-write", action="store_true", help="Accepted for workflow symmetry; this script never writes.")
    args = parser.parse_args(argv)

    report = build_report(
        playbook_ids=_parse_playbooks(args.playbooks),
        n_picks=max(int(args.n_picks), 0),
        watchlist_size=max(int(args.watchlist_size), 0),
        use_recommended_policy=bool(args.use_recommended_policy),
        enforce_portfolio_caps=bool(args.enforce_portfolio_caps),
        truth_lane=str(args.truth_lane or LIVE_SCAN_TRUTH_LANE),
        top_limit=max(int(args.top_limit), 1),
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(
            json.dumps(
                {
                    "overall": report["overall"],
                    "settings": report["settings"],
                    "errors": report["errors"],
                    "playbooks": [
                        {
                            "playbook_id": item["playbook_id"],
                            "candidate_count": item["candidate_count"],
                            "returned_count": item["returned_count"],
                            "candidate_decision_counts": item["candidate_decision_counts"],
                            "block_rate_pct": item["block_rate_pct"],
                            "clear_rate_pct": item["clear_rate_pct"],
                            "starvation_flag": item["starvation_flag"],
                            "top_block_reasons": item["top_block_reasons"],
                            "top_drop_counts": _top_counts(Counter(dict(item.get("drop_counts") or {})), args.top_limit),
                            "top_upstream_drop_details": item["top_upstream_drop_details"],
                            "top_blocked_tickers": item["top_blocked_tickers"],
                            "top_clear_tickers": item["top_clear_tickers"],
                        }
                        for item in report["playbooks"]
                    ],
                },
                indent=2,
                sort_keys=True,
            )
        )
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
