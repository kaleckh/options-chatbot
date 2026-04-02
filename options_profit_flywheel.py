from __future__ import annotations

import argparse
import copy
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Optional

from options_profit_gate import evaluate_measurement_gate
from options_profit_state import (
    TARGET_SYMBOLS,
    default_symbol_manifest,
    ensure_options_profit_state,
    list_candidate_manifests,
    load_incumbents,
    load_live_profile,
    load_status,
    utc_now_iso,
    write_decision,
    write_incumbents,
    write_live_profile,
    write_status,
)


ROOT_DIR = Path(__file__).resolve().parent
for candidate in (ROOT_DIR, ROOT_DIR / "python-backend"):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from positions_repository import create_positions_repository  # type: ignore  # noqa: E402


TARGET_SYMBOL_SET = set(TARGET_SYMBOLS)
CANARY_REQUIRED_OUTCOMES = 10
LIVE_AUTOTUNE_SYMBOL = "SPY"


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
        if not math.isfinite(parsed):
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _score_profit_factor(value: Any) -> float:
    parsed = _safe_float(value)
    if parsed is None:
        return 0.0
    return max(min(parsed, 5.0), 0.0)


def _preferred_metric(metrics: dict[str, Any], *keys: str) -> float:
    for key in keys:
        value = _safe_float(metrics.get(key))
        if value is not None:
            return value
    return 0.0


def _composite_objective_score(forward_metrics: dict[str, Any], tracked_metrics: dict[str, Any]) -> float:
    forward_avg = _preferred_metric(
        forward_metrics,
        "net_realized_pnl_pct",
        "avg_net_pnl_pct",
        "avg_pnl_pct",
    )
    forward_pf = _score_profit_factor(
        _preferred_metric(
            forward_metrics,
            "net_profit_factor",
            "profit_factor",
        )
    )
    tracked_avg = _preferred_metric(
        tracked_metrics,
        "net_realized_pnl_pct",
        "avg_net_pnl_pct",
        "avg_pnl_pct",
    )
    tracked_pf = _score_profit_factor(
        _preferred_metric(
            tracked_metrics,
            "net_profit_factor",
            "profit_factor",
        )
    )
    return round((forward_avg * 0.6) + ((forward_pf - 1.0) * 25.0) + (tracked_avg * 0.4) + ((tracked_pf - 1.0) * 20.0), 4)


def _candidate_is_symbol_level(candidate: dict[str, Any]) -> bool:
    symbol = str(candidate.get("symbol") or "").strip().upper()
    symbols = [
        str(item).strip().upper()
        for item in list(candidate.get("symbols") or [])
        if str(item).strip()
    ]
    if symbol and symbol in TARGET_SYMBOL_SET and not symbols:
        return True
    return len(symbols) == 1 and symbols[0] in TARGET_SYMBOL_SET


def _candidate_symbol(candidate: dict[str, Any]) -> Optional[str]:
    symbol = str(candidate.get("symbol") or "").strip().upper()
    if symbol in TARGET_SYMBOL_SET:
        return symbol
    symbols = [
        str(item).strip().upper()
        for item in list(candidate.get("symbols") or [])
        if str(item).strip()
    ]
    if len(symbols) == 1 and symbols[0] in TARGET_SYMBOL_SET:
        return symbols[0]
    return None


def _load_json_path(path_value: Any) -> Optional[dict[str, Any]]:
    path_text = str(path_value or "").strip()
    if not path_text:
        return None
    path = Path(path_text)
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _extract_replay_gate(candidate: dict[str, Any]) -> dict[str, Any]:
    evaluation = dict(candidate.get("evaluation") or {})
    explicit_gate = dict(evaluation.get("replay_gate") or {})
    if explicit_gate:
        return explicit_gate

    research_manifest = _load_json_path(candidate.get("research_manifest_path"))
    research_policy = _load_json_path(candidate.get("policy_path"))
    research_result = _load_json_path(candidate.get("replay_result_path"))

    if research_policy:
        source = dict(research_policy.get("source") or {})
        promotion_status = str(research_policy.get("promotion_status") or "").strip().lower()
        stability = dict(research_policy.get("stability") or {})
        return {
            "passes": promotion_status == "promote",
            "promotion_status": promotion_status or None,
            "profit_factor": _safe_float((research_policy.get("overall") or {}).get("profit_factor")),
            "directional_accuracy_pct": _safe_float((research_policy.get("overall") or {}).get("directional_accuracy_pct")),
            "quote_coverage_pct": _safe_float(research_policy.get("quote_coverage_pct") or source.get("quote_coverage_pct")),
            "min_trades": int(((stability.get("quality_bar") or {}).get("min_trades") or 0)),
            "stability_status": str(stability.get("overall_status") or "").strip().lower() or None,
        }

    if research_manifest or research_result:
        source = dict((research_result or {}).get("source") or {})
        overall = dict((research_result or {}).get("overall") or {})
        stability = dict((research_result or {}).get("stability") or {})
        return {
            "passes": bool(candidate.get("replay_gate_passes")),
            "promotion_status": str((research_result or {}).get("promotion_status") or "").strip().lower() or None,
            "profit_factor": _safe_float(overall.get("profit_factor")),
            "directional_accuracy_pct": _safe_float(overall.get("directional_accuracy_pct")),
            "quote_coverage_pct": _safe_float((research_result or {}).get("quote_coverage_pct") or source.get("quote_coverage_pct")),
            "min_trades": int(((stability.get("quality_bar") or {}).get("min_trades") or 0)),
            "stability_status": str(stability.get("overall_status") or "").strip().lower() or None,
        }

    return {}


def _extract_objective_metrics(candidate: dict[str, Any]) -> dict[str, Any]:
    evaluation = dict(candidate.get("evaluation") or {})
    forward_metrics = dict(evaluation.get("forward_exact_contract") or {})
    tracked_metrics = dict(evaluation.get("tracked_realized") or {})
    return {
        "forward_exact_contract": forward_metrics,
        "tracked_realized": tracked_metrics,
        "objective_score": _composite_objective_score(forward_metrics, tracked_metrics),
    }


def _load_closed_positions() -> list[dict[str, Any]]:
    repo = create_positions_repository(os.getenv("DATABASE_URL"))
    if not getattr(repo, "is_available", False):
        return []
    try:
        return list(repo.list_positions("closed"))
    except Exception:
        return []


def _candidate_position_metrics(symbol: str, candidate_id: str, positions: list[dict[str, Any]]) -> dict[str, Any]:
    pnls: list[float] = []
    exact_outcome_count = 0
    for position in positions:
        source = dict(position.get("source_pick_snapshot") or {})
        position_symbol = str(position.get("ticker") or source.get("ticker") or "").strip().upper()
        cohort_id = str(
            source.get("profit_candidate_id")
            or source.get("cohort_id")
            or source.get("candidate_id")
            or ""
        ).strip()
        if position_symbol != symbol or cohort_id != candidate_id:
            continue
        net_pnl_pct = _safe_float(position.get("net_pnl_pct"))
        if net_pnl_pct is None:
            entry = _safe_float(position.get("entry_execution_price"))
            if entry is None:
                entry = _safe_float(position.get("entry_option_price"))
            exit_price = _safe_float(position.get("exit_execution_price"))
            if exit_price is None:
                exit_price = _safe_float(position.get("exit_option_price"))
            if entry is None or entry <= 0 or exit_price is None:
                continue
            net_pnl_pct = (exit_price / entry - 1.0) * 100.0
        if str(position.get("contract_symbol") or source.get("contract_symbol") or "").strip():
            exact_outcome_count += 1
        pnls.append(net_pnl_pct)
    positive = sum(value for value in pnls if value > 0)
    negative = abs(sum(value for value in pnls if value < 0))
    return {
        "closed_position_count": len(pnls),
        "exact_outcome_count": exact_outcome_count,
        "avg_pnl_pct": round(sum(pnls) / len(pnls), 4) if pnls else None,
        "avg_net_pnl_pct": round(sum(pnls) / len(pnls), 4) if pnls else None,
        "profit_factor": round(positive / negative, 4) if negative > 0 else None,
        "net_profit_factor": round(positive / negative, 4) if negative > 0 else None,
    }


def _incumbent_metrics(symbol: str, incumbents: dict[str, Any]) -> dict[str, Any]:
    symbol_state = dict((incumbents.get("symbols") or {}).get(symbol) or {})
    objective = dict(symbol_state.get("objective") or {})
    return {
        "forward_exact_contract": dict(objective.get("forward_exact_contract") or {}),
        "tracked_realized": dict(objective.get("tracked_realized") or {}),
        "objective_score": _safe_float(objective.get("objective_score")) or 0.0,
    }


def _replay_gate_passes(replay_gate: dict[str, Any]) -> bool:
    if not replay_gate:
        return False
    explicit = replay_gate.get("passes")
    if explicit is not None:
        return bool(explicit)
    promotion_status = str(replay_gate.get("promotion_status") or "").strip().lower()
    stability_status = str(replay_gate.get("stability_status") or "").strip().lower()
    return promotion_status == "promote" and stability_status in {"promote", "watch", ""}


def _candidate_is_eligible(
    candidate: dict[str, Any],
    symbol: str,
    incumbent_metrics: dict[str, Any],
) -> tuple[bool, list[str], dict[str, Any]]:
    replay_gate = _extract_replay_gate(candidate)
    objective_metrics = _extract_objective_metrics(candidate)
    blockers: list[str] = []

    if not _candidate_is_symbol_level(candidate):
        blockers.append("candidate_not_symbol_level")
    if _candidate_symbol(candidate) != symbol:
        blockers.append("candidate_symbol_mismatch")
    if symbol != LIVE_AUTOTUNE_SYMBOL:
        blockers.append("shadow_only_symbol")
    if not _replay_gate_passes(replay_gate):
        blockers.append("replay_gate_failed")

    forward_metrics = dict(objective_metrics.get("forward_exact_contract") or {})
    tracked_metrics = dict(objective_metrics.get("tracked_realized") or {})
    if int(forward_metrics.get("eligible_trade_count") or 0) < 25:
        blockers.append("insufficient_exact_forward_support")
    if int(tracked_metrics.get("closed_position_count") or 0) <= 0:
        blockers.append("missing_tracked_realized_support")
    if float(objective_metrics.get("objective_score") or 0.0) <= float(incumbent_metrics.get("objective_score") or 0.0):
        blockers.append("objective_not_better_than_incumbent")

    return (not blockers, blockers, {"replay_gate": replay_gate, "objective": objective_metrics})


def _best_candidates(
    candidates: list[dict[str, Any]],
    incumbents: dict[str, Any],
) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for symbol in TARGET_SYMBOLS:
        incumbent_metrics = _incumbent_metrics(symbol, incumbents)
        symbol_candidates: list[dict[str, Any]] = []
        for candidate in candidates:
            if _candidate_symbol(candidate) != symbol:
                continue
            eligible, blockers, details = _candidate_is_eligible(candidate, symbol, incumbent_metrics)
            candidate_summary = {
                "candidate_id": str(candidate.get("candidate_id") or "").strip(),
                "symbol": symbol,
                "eligible": eligible,
                "blockers": blockers,
                "details": details,
                "manifest": candidate,
                "delta_vs_incumbent": round(
                    float((details.get("objective") or {}).get("objective_score") or 0.0)
                    - float(incumbent_metrics.get("objective_score") or 0.0),
                    4,
                ),
            }
            symbol_candidates.append(candidate_summary)
        if not symbol_candidates:
            continue
        symbol_candidates.sort(key=lambda item: (bool(item["eligible"]), float(item["delta_vs_incumbent"])), reverse=True)
        ranked.append(symbol_candidates[0])
    ranked.sort(key=lambda item: float(item["delta_vs_incumbent"]), reverse=True)
    return ranked


def _apply_candidate(
    *,
    choice: dict[str, Any],
    incumbents: dict[str, Any],
    live_profile: dict[str, Any],
) -> dict[str, Any]:
    symbol = str(choice["symbol"]).upper()
    manifest = dict(choice["manifest"] or {})
    candidate_id = str(manifest.get("candidate_id") or choice["candidate_id"]).strip()
    now = utc_now_iso()

    previous_active = copy.deepcopy(
        ((incumbents.get("symbols") or {}).get(symbol) or {}).get("active")
        or default_symbol_manifest(symbol)
    )
    candidate_live_manifest = {
        "symbol": symbol,
        "candidate_id": candidate_id,
        "base_profile": str(manifest.get("base_profile") or "index"),
        "overrides": copy.deepcopy(manifest.get("overrides") or {}),
        "source": str(manifest.get("source") or manifest.get("path") or "options_profit_cycle"),
        "mode": "canary",
        "applied_at": now,
    }
    pre_decision_path = write_decision(
        {
            "action": "pre_apply_candidate",
            "symbol": symbol,
            "candidate_id": candidate_id,
            "previous_active": previous_active,
            "candidate_live_manifest": candidate_live_manifest,
            "objective": choice["details"]["objective"],
            "delta_vs_incumbent": choice["delta_vs_incumbent"],
        },
        candidate_id=candidate_id,
        stage="pre_apply",
    )

    updated_live = copy.deepcopy(live_profile)
    updated_live.setdefault("symbols", {})
    updated_live["symbols"][symbol] = candidate_live_manifest
    write_live_profile(updated_live)

    updated_incumbents = copy.deepcopy(incumbents)
    updated_incumbents.setdefault("symbols", {})
    updated_incumbents["symbols"][symbol] = {
        "symbol": symbol,
        "active": candidate_live_manifest,
        "previous": previous_active,
        "canary": {
            "candidate_id": candidate_id,
            "symbol": symbol,
            "started_at": now,
            "required_outcomes": CANARY_REQUIRED_OUTCOMES,
            "baseline_objective": _incumbent_metrics(symbol, incumbents),
        },
        "objective": choice["details"]["objective"],
    }
    write_incumbents(updated_incumbents)

    post_decision_path = write_decision(
        {
            "action": "post_apply_candidate",
            "symbol": symbol,
            "candidate_id": candidate_id,
            "live_profile_path": str((ROOT_DIR / "data" / "options-profit" / "live_profile.json")),
            "pre_apply_decision_path": pre_decision_path,
            "active_manifest": candidate_live_manifest,
        },
        candidate_id=candidate_id,
        stage="post_apply",
    )
    return {
        "action": "apply_candidate",
        "symbol": symbol,
        "candidate_id": candidate_id,
        "pre_apply_decision_path": pre_decision_path,
        "post_apply_decision_path": post_decision_path,
        "active_manifest": candidate_live_manifest,
    }


def _rollback_canary(
    *,
    symbol: str,
    reason: str,
    incumbents: dict[str, Any],
    live_profile: dict[str, Any],
) -> dict[str, Any]:
    symbol_state = dict((incumbents.get("symbols") or {}).get(symbol) or {})
    previous_active = copy.deepcopy(symbol_state.get("previous") or default_symbol_manifest(symbol))
    active = copy.deepcopy(symbol_state.get("active") or {})
    candidate_id = str(
        ((symbol_state.get("canary") or {}).get("candidate_id"))
        or active.get("candidate_id")
        or f"{symbol.lower()}_rollback"
    ).strip()

    write_decision(
        {
            "action": "pre_rollback_canary",
            "symbol": symbol,
            "candidate_id": candidate_id,
            "reason": reason,
            "current_active": active,
            "rollback_to": previous_active,
        },
        candidate_id=candidate_id,
        stage="pre_rollback",
    )

    updated_live = copy.deepcopy(live_profile)
    updated_live.setdefault("symbols", {})
    previous_active["mode"] = "incumbent"
    previous_active["applied_at"] = utc_now_iso()
    updated_live["symbols"][symbol] = previous_active
    write_live_profile(updated_live)

    updated_incumbents = copy.deepcopy(incumbents)
    updated_incumbents.setdefault("symbols", {})
    updated_incumbents["symbols"][symbol] = {
        "symbol": symbol,
        "active": previous_active,
        "previous": None,
        "canary": None,
        "objective": symbol_state.get("objective"),
    }
    write_incumbents(updated_incumbents)

    post_path = write_decision(
        {
            "action": "post_rollback_canary",
            "symbol": symbol,
            "candidate_id": candidate_id,
            "reason": reason,
            "active_manifest": previous_active,
        },
        candidate_id=candidate_id,
        stage="post_rollback",
    )
    return {
        "action": "rollback_canary",
        "symbol": symbol,
        "candidate_id": candidate_id,
        "reason": reason,
        "decision_path": post_path,
    }


def _maybe_finalize_or_rollback_canary(
    *,
    incumbents: dict[str, Any],
    live_profile: dict[str, Any],
    gate: dict[str, Any],
    closed_positions: list[dict[str, Any]],
) -> Optional[dict[str, Any]]:
    for symbol in (LIVE_AUTOTUNE_SYMBOL,):
        symbol_state = dict((incumbents.get("symbols") or {}).get(symbol) or {})
        canary = dict(symbol_state.get("canary") or {})
        if not canary:
            continue
        if gate.get("state") != "healthy":
            return _rollback_canary(
                symbol=symbol,
                reason=f"measurement_gate_{gate.get('state')}",
                incumbents=incumbents,
                live_profile=live_profile,
            )
        candidate_id = str(canary.get("candidate_id") or "").strip()
        observed = _candidate_position_metrics(symbol, candidate_id, closed_positions)
        required_outcomes = int(canary.get("required_outcomes") or CANARY_REQUIRED_OUTCOMES)
        if int(observed.get("closed_position_count") or 0) < required_outcomes:
            return {
                "action": "canary_pending",
                "symbol": symbol,
                "candidate_id": candidate_id,
                "observed_outcomes": int(observed.get("closed_position_count") or 0),
                "required_outcomes": required_outcomes,
            }
        baseline = dict(canary.get("baseline_objective") or {})
        baseline_score = _safe_float(baseline.get("objective_score")) or 0.0
        observed_score = _composite_objective_score({}, observed)
        if observed_score <= baseline_score:
            return _rollback_canary(
                symbol=symbol,
                reason="canary_underperformed_baseline",
                incumbents=incumbents,
                live_profile=live_profile,
            )

        finalized = copy.deepcopy(incumbents)
        finalized["symbols"][symbol]["canary"] = None
        finalized["symbols"][symbol]["active"]["mode"] = "incumbent"
        finalized["symbols"][symbol]["objective"] = {
            "forward_exact_contract": {},
            "tracked_realized": observed,
            "objective_score": observed_score,
        }
        write_incumbents(finalized)
        write_decision(
            {
                "action": "finalize_canary",
                "symbol": symbol,
                "candidate_id": candidate_id,
                "observed": observed,
                "observed_score": observed_score,
            },
            candidate_id=candidate_id,
            stage="finalize",
        )
        return {
            "action": "finalize_canary",
            "symbol": symbol,
            "candidate_id": candidate_id,
            "observed": observed,
            "observed_score": observed_score,
        }
    return None


def run_options_profit_cycle(
    *,
    recorded_before_utc: str | None = None,
) -> dict[str, Any]:
    ensure_options_profit_state()
    gate = evaluate_measurement_gate(recorded_before_utc=recorded_before_utc)
    live_profile = load_live_profile()
    incumbents = load_incumbents()
    previous_status = load_status()
    closed_positions = _load_closed_positions()

    canary_action = _maybe_finalize_or_rollback_canary(
        incumbents=incumbents,
        live_profile=live_profile,
        gate=gate,
        closed_positions=closed_positions,
    )
    if canary_action and canary_action["action"] in {"rollback_canary", "finalize_canary"}:
        incumbents = load_incumbents()
        live_profile = load_live_profile()

    decision: dict[str, Any]
    candidate_rankings: list[dict[str, Any]] = []
    if canary_action and canary_action["action"] in {"canary_pending", "rollback_canary", "finalize_canary"}:
        decision = {
            "action": "no_op",
            "reason": f"canary_action_{canary_action['action']}",
        }
    elif gate.get("state") == "healthy":
        candidates = list_candidate_manifests()
        candidate_rankings = _best_candidates(candidates, incumbents)
        eligible_choices = [
            item
            for item in candidate_rankings
            if item.get("eligible") and str(item.get("symbol") or "").strip().upper() == LIVE_AUTOTUNE_SYMBOL
        ]
        if eligible_choices:
            decision = _apply_candidate(
                choice=eligible_choices[0],
                incumbents=incumbents,
                live_profile=live_profile,
            )
        else:
            decision = {
                "action": "no_op",
                "reason": "no_eligible_live_symbol_challenger",
            }
    else:
        decision = {
            "action": "no_op",
            "reason": f"measurement_gate_{gate.get('state')}",
        }

    status = {
        "generated_at": utc_now_iso(),
        "measurement_gate": {
            "state": gate.get("state"),
            "blockers": list(gate.get("blockers") or []),
            "checks": dict(gate.get("checks") or {}),
        },
        "active_incumbents": dict((load_live_profile().get("symbols") or {})),
        "current_canary": {
            symbol: dict(((load_incumbents().get("symbols") or {}).get(symbol) or {}).get("canary") or {})
            for symbol in TARGET_SYMBOLS
            if dict(((load_incumbents().get("symbols") or {}).get(symbol) or {}).get("canary") or {})
        } or None,
        "last_decision": decision,
        "blockers": list(gate.get("blockers") or []),
        "candidate_rankings": [
            {
                "candidate_id": item["candidate_id"],
                "symbol": item["symbol"],
                "eligible": item["eligible"],
                "blockers": item["blockers"],
                "delta_vs_incumbent": item["delta_vs_incumbent"],
            }
            for item in candidate_rankings
        ],
        "previous_status_generated_at": previous_status.get("generated_at"),
    }
    write_status(status)

    decision_path = write_decision(
        {
            "action": decision.get("action"),
            "reason": decision.get("reason"),
            "measurement_gate_state": gate.get("state"),
            "blockers": gate.get("blockers"),
            "candidate_rankings": status["candidate_rankings"],
            "canary_action": canary_action,
        },
        candidate_id=str(decision.get("candidate_id") or "status"),
    )
    status["last_decision_path"] = decision_path
    write_status(status)

    return {
        "measurement_gate": gate,
        "decision": decision,
        "status": status,
        "canary_action": canary_action,
        "decision_path": decision_path,
    }


def current_options_profit_status() -> dict[str, Any]:
    ensure_options_profit_state()
    status = load_status()
    if status:
        return status
    return {
        "generated_at": utc_now_iso(),
        "measurement_gate": {
            "state": "blocked",
            "blockers": ["Options profit cycle has not run yet."],
            "checks": {},
        },
        "active_incumbents": dict((load_live_profile().get("symbols") or {})),
        "current_canary": None,
        "last_decision": {
            "action": "not_started",
            "reason": "Options profit cycle has not run yet.",
        },
        "blockers": ["Options profit cycle has not run yet."],
        "candidate_rankings": [],
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the bounded options profit flywheel for SPY/QQQ manifests."
    )
    parser.add_argument(
        "--recorded-before-utc",
        default=None,
        help="Optional cutoff for forward evidence considered by the measurement gate.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full cycle payload as JSON.")
    args = parser.parse_args(argv)

    result = run_options_profit_cycle(recorded_before_utc=args.recorded_before_utc)
    if args.json:
        print(json.dumps(result, indent=2, allow_nan=False))
    else:
        summary = {
            "measurement_gate_state": result["measurement_gate"]["state"],
            "decision": result["decision"],
            "decision_path": result["decision_path"],
            "status_path": str((ROOT_DIR / "data" / "options-profit" / "status.json")),
        }
        print(json.dumps(summary, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
