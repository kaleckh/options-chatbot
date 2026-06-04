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
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking"
DEFAULT_DOC = ROOT / "docs" / "regular-guardrail-starvation-audit.md"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _regular_playbook_ids(*, include_commodity: bool = False) -> list[str]:
    if include_commodity:
        return list(SCAN_PLAYBOOKS)
    return [playbook_id for playbook_id in SCAN_PLAYBOOKS if playbook_id not in COMMODITY_PLAYBOOK_IDS]


def _parse_playbooks(value: str | None, *, include_commodity: bool = False) -> list[str]:
    if not value:
        return _regular_playbook_ids(include_commodity=include_commodity)
    playbooks = [item.strip() for item in value.split(",") if item.strip()]
    unknown = [item for item in playbooks if item not in SCAN_PLAYBOOKS]
    if unknown:
        raise ValueError(f"Unknown playbook(s): {', '.join(unknown)}")
    forbidden = [item for item in playbooks if item in COMMODITY_PLAYBOOK_IDS]
    if forbidden and not include_commodity:
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


def _status_from_overall(overall: dict[str, Any], errors: list[dict[str, str]] | None = None) -> str:
    if errors:
        return "audit_errors"
    starvation_playbooks = list(overall.get("starvation_playbooks") or [])
    if starvation_playbooks:
        return "guardrail_starvation_detected"
    candidate_total = int(overall.get("candidate_count_total") or 0)
    completed = int(overall.get("playbooks_completed") or 0)
    zero_candidate_count = len(list(overall.get("zero_candidate_playbooks") or []))
    if completed and zero_candidate_count == completed and candidate_total == 0:
        return "upstream_zero_candidate_scan_pressure"
    if candidate_total > 0:
        return "candidates_present_not_guardrail_starved"
    return "no_guardrail_starvation_detected"


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
        "contract_symbol": pick.get("contract_symbol") or pick.get("contractSymbol"),
        "short_contract_symbol": pick.get("short_contract_symbol") or pick.get("shortContractSymbol"),
        "long_strike": pick.get("long_strike") if pick.get("long_strike") is not None else pick.get("strike"),
        "short_strike": pick.get("short_strike"),
        "net_debit": pick.get("net_debit"),
        "entry_execution_price": pick.get("entry_execution_price"),
        "entry_execution_basis": pick.get("entry_execution_basis"),
        "debit_pct_of_width": pick.get("debit_pct_of_width"),
        "quality_score": pick.get("quality_score"),
        "confidence": pick.get("confidence"),
        "ret5": signal.get("ret5") if signal else pick.get("ret5"),
        "guardrail_decision": _decision(pick.get("guardrail_decision")),
        "guardrail_reasons": list(pick.get("guardrail_reasons") or []),
        "suggested_size_tier": pick.get("suggested_size_tier"),
        "proof_eligible": pick.get("proof_eligible"),
        "candidate_execution_label": pick.get("candidate_execution_label"),
        "quote_time_utc": pick.get("quote_time_utc"),
        "quote_time_et": pick.get("quote_time_et"),
        "quote_freshness_status": pick.get("quote_freshness_status"),
        "selection_source": pick.get("selection_source"),
        "promotion_class": pick.get("promotion_class"),
    }


def _scan_symbol_scope(playbook: dict[str, Any], *, watchlist_size: int) -> dict[str, Any]:
    scan_tickers = list(((playbook.get("data_readiness") or {}).get("scan_tickers") or []))
    if not scan_tickers:
        scan_tickers = [
            str(item or "").strip().upper()
            for item in list(playbook.get("scan_tickers") or playbook.get("allowed_tickers") or [])
            if str(item or "").strip()
        ]
    if scan_tickers:
        return {
            "source": "playbook_scan_tickers",
            "symbol_count": len(list(dict.fromkeys(scan_tickers))),
            "symbols": list(dict.fromkeys(scan_tickers)),
        }
    return {
        "source": "default_watchlist",
        "symbol_count": int(watchlist_size),
        "symbols": [],
    }


def _summarize_scan_result(
    playbook_id: str,
    result: dict[str, Any],
    *,
    top_limit: int,
    watchlist_size: int,
) -> dict[str, Any]:
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
    playbook = result.get("playbook") or {}
    return {
        "playbook_id": playbook_id,
        "label": playbook.get("label"),
        "scan_symbol_scope": _scan_symbol_scope(playbook, watchlist_size=watchlist_size),
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
        playbook_reports.append(
            _summarize_scan_result(
                playbook_id,
                result,
                top_limit=top_limit,
                watchlist_size=watchlist_size,
            )
        )

    totals = Counter()
    starvation_playbooks: list[str] = []
    top_reasons: Counter[str] = Counter()
    top_drops: Counter[str] = Counter()
    top_drop_details: Counter[tuple[str, str]] = Counter()
    top_drop_detail_tickers: dict[tuple[str, str], list[str]] = defaultdict(list)
    zero_candidate_playbooks: list[str] = []
    candidate_count_total = 0
    returned_count_total = 0
    for report in playbook_reports:
        candidate_count_total += int(report.get("candidate_count") or 0)
        returned_count_total += int(report.get("returned_count") or 0)
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
    overall = {
        "playbooks_requested": len(playbook_ids),
        "playbooks_completed": len(playbook_reports),
        "candidate_count_total": candidate_count_total,
        "returned_count_total": returned_count_total,
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
    }
    overall["status"] = _status_from_overall(overall, errors)
    return {
        "generated_at_utc": _utc_now_iso(),
        "scope": (
            "all_supervised_guardrail_starvation"
            if any(playbook_id in COMMODITY_PLAYBOOK_IDS for playbook_id in playbook_ids)
            else "regular_supervised_guardrail_starvation"
        ),
        "read_only": True,
        "commodity_playbooks_excluded": (
            []
            if any(playbook_id in COMMODITY_PLAYBOOK_IDS for playbook_id in playbook_ids)
            else sorted(COMMODITY_PLAYBOOK_IDS)
        ),
        "playbooks": playbook_reports,
        "errors": errors,
        "overall": overall,
        "settings": {
            "n_picks": n_picks,
            "watchlist_size": watchlist_size,
            "use_recommended_policy": use_recommended_policy,
            "include_blocked_guardrail_picks": True,
            "enforce_portfolio_caps": enforce_portfolio_caps,
            "truth_lane": truth_lane,
            "market_open_at_run": market_open_at_run,
            "audit_all_configured_tickers": True,
            "include_commodity_playbooks": any(
                playbook_id in COMMODITY_PLAYBOOK_IDS for playbook_id in playbook_ids
            ),
        },
    }


def markdown_report(report: dict[str, Any]) -> str:
    overall = report.get("overall") if isinstance(report.get("overall"), dict) else {}
    settings = report.get("settings") if isinstance(report.get("settings"), dict) else {}
    lines = [
        "# Regular Guardrail Starvation Audit",
        "",
        f"- Generated: `{report.get('generated_at_utc')}`",
        f"- Status: `{overall.get('status')}`",
        f"- Playbooks completed/requested: `{overall.get('playbooks_completed')}` / `{overall.get('playbooks_requested')}`",
        f"- Candidate/returned totals: `{overall.get('candidate_count_total')}` / `{overall.get('returned_count_total')}`",
        f"- Candidate guardrail decisions: `{overall.get('candidate_decision_counts')}`",
        f"- Starvation playbooks: `{overall.get('starvation_playbooks')}`",
        f"- Zero-candidate playbooks: `{len(list(overall.get('zero_candidate_playbooks') or []))}`",
        f"- Market open at run: `{settings.get('market_open_at_run')}`",
        f"- All configured ticker scopes audited: `{settings.get('audit_all_configured_tickers')}`",
        f"- Commodity playbooks included: `{settings.get('include_commodity_playbooks')}`",
        "",
        "## Leading Upstream Drops",
        "",
    ]
    for item in list(overall.get("top_drop_counts") or []):
        lines.append(f"- `{item.get('value')}`: `{item.get('count')}`")
    lines.extend(["", "## Leading Drop Details", ""])
    for item in list(overall.get("top_upstream_drop_details") or []):
        tickers = ", ".join(str(ticker) for ticker in list(item.get("tickers") or []))
        lines.append(
            f"- `{item.get('drop_key')}`: `{item.get('count')}` - {item.get('detail')} (`{tickers}`)"
        )
    lines.extend(["", "## Interpretation", ""])
    status = str(overall.get("status") or "")
    if status == "upstream_zero_candidate_scan_pressure":
        lines.append(
            "- Current no-pick state is upstream scanner/data/liquidity pressure, not promoted guardrail starvation."
        )
    elif status == "guardrail_starvation_detected":
        lines.append("- Inspect blocked candidate rows before loosening promoted profitability guardrails.")
    elif status == "candidates_present_not_guardrail_starved":
        lines.append("- Candidates are present and guardrails are not filtering all viable rows.")
    else:
        lines.append("- No guardrail starvation signal was detected.")
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, output_dir: Path = DEFAULT_OUTPUT_DIR, doc_path: Path = DEFAULT_DOC) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"regular_guardrail_starvation_{stamp}.json"
    latest_json = output_dir / "regular_guardrail_starvation_latest.json"
    payload = json.dumps(report, indent=2, sort_keys=True)
    json_path.write_text(payload + "\n", encoding="utf8")
    latest_json.write_text(payload + "\n", encoding="utf8")
    doc_path.write_text(markdown_report(report), encoding="utf8")
    return {"json": str(json_path), "latest_json": str(latest_json), "markdown": str(doc_path)}


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
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--doc-path", type=Path, default=DEFAULT_DOC)
    parser.add_argument(
        "--include-commodity",
        action="store_true",
        help="Include the separate AI commodity/infrastructure strategy lane in the cross-strategy daily audit.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full report JSON.")
    parser.add_argument("--include-playbooks", action="store_true", help="Include compact per-playbook details in non-JSON console output.")
    parser.add_argument("--no-write", action="store_true", help="Run without writing latest JSON/Markdown artifacts.")
    args = parser.parse_args(argv)

    report = build_report(
        playbook_ids=_parse_playbooks(args.playbooks, include_commodity=bool(args.include_commodity)),
        n_picks=max(int(args.n_picks), 0),
        watchlist_size=max(int(args.watchlist_size), 0),
        use_recommended_policy=bool(args.use_recommended_policy),
        enforce_portfolio_caps=bool(args.enforce_portfolio_caps),
        truth_lane=str(args.truth_lane or LIVE_SCAN_TRUTH_LANE),
        top_limit=max(int(args.top_limit), 1),
    )
    artifacts: dict[str, str] | None = None
    if not args.no_write:
        artifacts = write_outputs(report, output_dir=args.output_dir, doc_path=args.doc_path)
    if args.json:
        payload: dict[str, Any] = {"report": report}
        if artifacts:
            payload["artifacts"] = artifacts
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        console_payload: dict[str, Any] = {
            "overall": report["overall"],
            "settings": report["settings"],
            "errors": report["errors"],
            "artifacts": artifacts,
        }
        if args.include_playbooks:
            console_payload["playbooks"] = [
                {
                    "playbook_id": item["playbook_id"],
                    "scan_symbol_scope": item["scan_symbol_scope"],
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
            ]
        print(
            json.dumps(
                console_payload,
                indent=2,
                sort_keys=True,
            )
        )
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
