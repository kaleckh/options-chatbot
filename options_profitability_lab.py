from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Optional

from options_profit_gate import evaluate_measurement_gate
from wfo_optimizer import build_options_experiment_matrix, load_last_results_by_truth_lane, run_historical_backtest


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = ROOT_DIR / "data" / "profitability-lab"


DEFAULT_VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "id": "incumbent_broad",
        "label": "Incumbent Broad",
        "description": "Current broad replay policy; this is the control surface.",
        "playbook": "broad",
    },
    {
        "id": "short_term_calls",
        "label": "Short-Term Calls",
        "description": "Call-only short-term challenger for bullish continuation.",
        "playbook": "short_term",
        "allowed_directions": ["call"],
    },
    {
        "id": "short_term_puts",
        "label": "Short-Term Puts",
        "description": "Put-only short-term challenger kept as a candidate until forward evidence confirms it.",
        "playbook": "short_term",
        "allowed_directions": ["put"],
    },
    {
        "id": "bullish_momentum",
        "label": "Bullish Momentum",
        "description": "Bullish equity momentum slice.",
        "playbook": "bullish_momentum",
        "allowed_directions": ["call"],
    },
    {
        "id": "bullish_index_calls",
        "label": "Bullish Index Calls",
        "description": "Candidate challenger for the broad replay's strongest exact-contract slice: SPY/QQQ calls in bullish regimes.",
        "playbook": "bullish_index_calls",
        "allowed_directions": ["call"],
    },
    {
        "id": "bullish_index_calls_score70",
        "label": "Bullish Index Calls Score 70+",
        "description": "Stricter candidate challenger: SPY/QQQ calls in bullish regimes with quality score at least 70.",
        "playbook": "bullish_index_calls_score70",
        "allowed_directions": ["call"],
    },
    {
        "id": "bullish_qqq_calls_score70",
        "label": "Bullish QQQ Calls Score 70+",
        "description": "Narrow candidate challenger: QQQ calls in bullish regimes with quality score at least 70.",
        "playbook": "bullish_qqq_calls_score70",
        "allowed_directions": ["call"],
    },
    {
        "id": "bullish_index_calls_quality90_debit55",
        "label": "Bullish Index Calls Quality 90+ Debit <55%",
        "description": "Candidate challenger: SPY/QQQ bullish call spreads with quality score at least 90 and entry debit below 55% of spread width.",
        "playbook": "bullish_index_calls_quality90_debit55",
        "allowed_directions": ["call"],
    },
    {
        "id": "bullish_index_calls_score70_debit55",
        "label": "Bullish Index Calls Score 70+ Debit <55%",
        "description": "Candidate challenger: SPY/QQQ bullish call spreads with quality score at least 70 and entry debit below 55% of spread width.",
        "playbook": "bullish_index_calls_score70_debit55",
        "allowed_directions": ["call"],
    },
    {
        "id": "bearish_defensive",
        "label": "Bearish Defensive",
        "description": "Bearish defensive put slice.",
        "playbook": "bearish_defensive",
        "allowed_directions": ["put"],
    },
)


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def lab_run_id(prefix: str = "profit_lab") -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        parsed = float(value)
        if parsed != parsed:
            return None
        return parsed
    except (TypeError, ValueError):
        return None


def _load_variant_definitions(variant_ids: Optional[list[str]] = None) -> list[dict[str, Any]]:
    variants = [dict(variant) for variant in DEFAULT_VARIANTS]
    if not variant_ids:
        return variants
    allowed = {str(item).strip() for item in variant_ids if str(item).strip()}
    return [variant for variant in variants if variant["id"] in allowed]


def _summarize_matrix(matrix: dict[str, Any]) -> dict[str, Any]:
    overall = dict(matrix.get("overall") or {})
    authoritative_metrics = dict(matrix.get("authoritative_profitability_metrics") or {})
    authoritative_gate = dict(matrix.get("authoritative_profitability_gate") or {})
    passing = list(matrix.get("passing_experiments") or [])
    top = list(matrix.get("experiments") or [])
    return {
        "source": matrix.get("source"),
        "source_run_at": matrix.get("source_run_at"),
        "lookback_years": matrix.get("lookback_years"),
        "pricing_lane": matrix.get("pricing_lane"),
        "authoritative_lens": matrix.get("authoritative_profitability_lens"),
        "overall": {
            "trades": overall.get("trades"),
            "profit_factor": overall.get("profit_factor"),
            "avg_pnl_pct": overall.get("avg_pnl_pct"),
            "directional_accuracy_pct": overall.get("directional_accuracy_pct"),
        },
        "authoritative_metrics": authoritative_metrics,
        "authoritative_gate": authoritative_gate,
        "top_experiments": [
            {
                "label": item.get("label"),
                "category": item.get("category"),
                "trades": item.get("trades"),
                "profit_factor": item.get("profit_factor"),
                "avg_pnl_pct": item.get("avg_pnl_pct"),
                "directional_accuracy_pct": item.get("directional_accuracy_pct"),
                "passes_quality_bar": item.get("passes_quality_bar"),
            }
            for item in top[:8]
        ],
        "passing_experiments": [
            {
                "label": item.get("label"),
                "category": item.get("category"),
                "trades": item.get("trades"),
                "profit_factor": item.get("profit_factor"),
                "avg_pnl_pct": item.get("avg_pnl_pct"),
                "directional_accuracy_pct": item.get("directional_accuracy_pct"),
            }
            for item in passing[:8]
        ],
        "recommendations": list(matrix.get("recommendations") or []),
    }


def _variant_verdict(*, summary: dict[str, Any], measurement_gate: dict[str, Any]) -> dict[str, Any]:
    gate = dict(summary.get("authoritative_gate") or {})
    metrics = dict(summary.get("authoritative_metrics") or {})
    tracked = dict((measurement_gate.get("checks") or {}).get("tracked_positions") or {})
    historical_pass = bool(gate.get("passed"))
    tracked_healthy = str(measurement_gate.get("state") or "").strip().lower() == "healthy"
    profit_factor = _safe_float(metrics.get("profit_factor") or metrics.get("net_profit_factor"))
    avg_pnl_pct = _safe_float(metrics.get("avg_pnl_pct") or metrics.get("avg_net_pnl_pct"))

    if historical_pass and tracked_healthy:
        status = "forward_watch_candidate"
        reason = "Historical gate passes and tracked measurement gate is healthy; keep as a candidate until new forward outcomes accrue."
    elif historical_pass:
        status = "historical_only_watch"
        reason = "Historical gate passes, but tracked/live measurement is not healthy enough for promotion."
    elif profit_factor is not None and profit_factor >= 1.0 and (avg_pnl_pct or 0.0) > 0:
        status = "research_watch"
        reason = "Replay is positive but below the promotion-quality bar."
    else:
        status = "block"
        reason = "Replay does not clear the minimum profitability quality bar."

    return {
        "status": status,
        "promotion_allowed": False,
        "reason": reason,
        "historical_pass": historical_pass,
        "tracked_gate_state": measurement_gate.get("state"),
        "tracked_closed_count": tracked.get("closed_position_count"),
    }


def run_profitability_lab_cycle(
    *,
    truth_lane: str = "historical_imported_daily",
    pricing_lane: str = "pessimistic",
    lookback_years: int = 1,
    n_picks: int = 3,
    iv_adj: float = 1.2,
    min_trades: int = 20,
    min_profit_factor: float = 1.05,
    min_directional_accuracy_pct: float = 50.0,
    run_backtests: bool = False,
    variant_ids: Optional[list[str]] = None,
    run_fingerprint: Optional[str] = None,
    fail_on_error: bool = False,
    backtest_func: Callable[..., dict[str, Any]] = run_historical_backtest,
    load_result_func: Callable[..., dict[str, Any] | None] = load_last_results_by_truth_lane,
    matrix_func: Callable[..., dict[str, Any]] = build_options_experiment_matrix,
    measurement_gate_func: Callable[..., dict[str, Any]] = evaluate_measurement_gate,
) -> dict[str, Any]:
    generated_at = utc_now_iso()
    variants = _load_variant_definitions(variant_ids)
    results: list[dict[str, Any]] = []

    for variant in variants:
        config = {
            "truth_lane": truth_lane,
            "pricing_lane": pricing_lane,
            "lookback_years": int(lookback_years),
            "n_picks": int(n_picks),
            "iv_adj": float(iv_adj),
            "playbook": variant.get("playbook"),
            "allowed_directions": list(variant.get("allowed_directions") or []),
        }
        if not run_backtests and variant.get("id") != "incumbent_broad":
            results.append(
                {
                    "id": variant["id"],
                    "label": variant["label"],
                    "description": variant["description"],
                    "config": config,
                    "status": "skipped",
                    "skip_reason": "Fresh backtests are required to evaluate challenger-specific playbook/direction variants.",
                    "verdict": {
                        "status": "not_evaluated",
                        "promotion_allowed": False,
                        "reason": "Run with --run-backtests to evaluate this challenger.",
                    },
                }
            )
            continue
        try:
            replay = (
                backtest_func(**config)
                if run_backtests
                else load_result_func(truth_lane)
            )
            if not replay:
                raise RuntimeError("No cached backtest result is available for this truth lane.")
            if replay.get("error"):
                raise RuntimeError(str(replay["error"]))
            matrix = matrix_func(
                result=replay,
                min_trades=int(min_trades),
                min_profit_factor=float(min_profit_factor),
                min_directional_accuracy_pct=float(min_directional_accuracy_pct),
            )
            if matrix.get("error"):
                raise RuntimeError(str(matrix["error"]))
            summary = _summarize_matrix(matrix)
            results.append(
                {
                    "id": variant["id"],
                    "label": variant["label"],
                    "description": variant["description"],
                    "config": config,
                    "status": "evaluated",
                    "summary": summary,
                }
            )
        except Exception as exc:
            if fail_on_error:
                raise
            results.append(
                {
                    "id": variant["id"],
                    "label": variant["label"],
                    "description": variant["description"],
                    "config": config,
                    "status": "error",
                    "error": str(exc),
                    "verdict": {
                        "status": "blocked_unavailable",
                        "promotion_allowed": False,
                        "reason": "Variant could not be evaluated in this cycle.",
                    },
                }
            )

    measurement_gate = measurement_gate_func()
    for result in results:
        if result.get("status") == "evaluated":
            result["verdict"] = _variant_verdict(
                summary=dict(result.get("summary") or {}),
                measurement_gate=measurement_gate,
            )

    next_actions = [
        "Keep challenger variants in candidate review until proof outcomes accrue.",
        "Prefer variants that pass historical gates and then earn fresh forward/proof outcomes.",
        "Do not promote from one lab cycle; require repeated cycles plus closed tracked proof.",
    ]
    if any(item.get("status") == "error" for item in results):
        next_actions.append("Resolve unavailable historical/truth data before trusting challenger ranking.")

    verdict = _lab_verdict(results)
    return {
        "generated_at": generated_at,
        "run_fingerprint": run_fingerprint,
        "status": verdict["status"],
        "verdict": verdict,
        "truth_lane": truth_lane,
        "pricing_lane": pricing_lane,
        "run_backtests": bool(run_backtests),
        "quality_bar": {
            "min_trades": int(min_trades),
            "min_profit_factor": float(min_profit_factor),
            "min_directional_accuracy_pct": float(min_directional_accuracy_pct),
        },
        "measurement_gate": measurement_gate,
        "variants": results,
        "next_actions": next_actions,
    }


def _lab_verdict(variants: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = [dict(item.get("verdict") or {}) for item in variants]
    statuses = {str(item.get("status") or "").strip() for item in verdicts}
    if "forward_watch_candidate" in statuses:
        return {
            "status": "watch",
            "next_action": "Review forward-watch candidates, then let them earn new proof outcomes before promotion.",
        }
    if any(item.get("status") == "error" for item in variants):
        return {
            "status": "degraded",
            "next_action": "Fix unavailable lab inputs before ranking challengers.",
        }
    if statuses and statuses <= {"block", "not_evaluated", "blocked_unavailable"}:
        return {
            "status": "blocked",
            "next_action": "Keep current live behavior conservative; no challenger has enough evidence.",
        }
    return {
        "status": "inconclusive",
        "next_action": "Collect more cycles and proof evidence before changing production policy.",
    }


def render_profitability_lab_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Options Profitability Lab",
        "",
        f"- Generated: {report.get('generated_at')}",
        f"- Verdict: `{(report.get('verdict') or {}).get('status') or report.get('status')}`",
        f"- Truth lane: `{report.get('truth_lane')}`",
        f"- Pricing lane: `{report.get('pricing_lane')}`",
        f"- Backtests run in this cycle: `{bool(report.get('run_backtests'))}`",
        f"- Measurement gate: `{(report.get('measurement_gate') or {}).get('state')}`",
        "",
        "## Variants",
        "",
        "| Variant | Status | Research PF | Research Avg P&L | Research Trades | Proof PF | Proof Avg P&L | Proof Trades | Verdict |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for variant in list(report.get("variants") or []):
        summary = dict(variant.get("summary") or {})
        research = dict(summary.get("overall") or {})
        proof = dict(summary.get("authoritative_metrics") or {})
        verdict = dict(variant.get("verdict") or {})
        lines.append(
            "| {label} | {status} | {research_pf} | {research_avg} | {research_trades} | {proof_pf} | {proof_avg} | {proof_trades} | {verdict} |".format(
                label=variant.get("label"),
                status=variant.get("status"),
                research_pf=research.get("profit_factor") or research.get("net_profit_factor") or "-",
                research_avg=research.get("avg_pnl_pct") or research.get("avg_net_pnl_pct") or "-",
                research_trades=research.get("trades") or research.get("trade_count") or "-",
                proof_pf=proof.get("profit_factor") or proof.get("net_profit_factor") or "-",
                proof_avg=proof.get("avg_pnl_pct") or proof.get("avg_net_pnl_pct") or "-",
                proof_trades=proof.get("trades") or proof.get("trade_count") or "-",
                verdict=verdict.get("status") or "-",
            )
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Research columns can include nearest-listed historical pricing and are useful for hypothesis discovery.",
            "- Proof columns are the promotion lens; exact-contract and forward evidence carry the decision.",
        ]
    )
    lines.extend(["", "## Next Actions", ""])
    for action in list(report.get("next_actions") or []):
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def write_profitability_lab_artifacts(report: dict[str, Any], *, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, str]:
    run_id = lab_run_id()
    run_dir = Path(output_root) / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "report.json"
    md_path = run_dir / "report.md"
    latest_path = Path(output_root) / "latest.json"
    latest_md_path = Path(output_root) / "latest.md"
    json_text = json.dumps(report, indent=2)
    md_text = render_profitability_lab_markdown(report)
    json_path.write_text(json_text, encoding="utf8")
    md_path.write_text(md_text, encoding="utf8")
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(json_text, encoding="utf8")
    latest_md_path.write_text(md_text, encoding="utf8")
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "json": str(json_path),
        "markdown": str(md_path),
        "latest_json": str(latest_path),
        "latest_markdown": str(latest_md_path),
    }


def run_profitability_lab_loop(
    *,
    cycles: int = 1,
    interval_seconds: float = 0.0,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    **cycle_kwargs: Any,
) -> dict[str, Any]:
    cycle_reports: list[dict[str, Any]] = []
    artifacts: list[dict[str, str]] = []
    total_cycles = max(int(cycles), 1)
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    started_at = utc_now_iso()
    active_path = output_root / "active_run.json"
    history_path = output_root / "profit_lab_loop_runs.jsonl"
    for index in range(total_cycles):
        active_path.write_text(
            json.dumps(
                {
                    "started_at": started_at,
                    "status": "running",
                    "cycle_index": index + 1,
                    "cycle_count": total_cycles,
                    "updated_at": utc_now_iso(),
                },
                indent=2,
            ),
            encoding="utf8",
        )
        report = run_profitability_lab_cycle(**cycle_kwargs)
        report["cycle_index"] = index + 1
        report["cycle_count"] = total_cycles
        artifact = write_profitability_lab_artifacts(report, output_root=output_root)
        cycle_reports.append(report)
        artifacts.append(artifact)
        with history_path.open("a", encoding="utf8") as handle:
            handle.write(json.dumps({"artifact": artifact, "report": report}) + "\n")
        if index < total_cycles - 1 and interval_seconds > 0:
            time.sleep(float(interval_seconds))
    completed_at = utc_now_iso()
    loop_result = {
        "started_at": started_at,
        "completed_at": completed_at,
        "status": "completed",
        "cycle_count": total_cycles,
        "artifacts": artifacts,
        "latest_report": cycle_reports[-1] if cycle_reports else None,
        "history_jsonl": str(history_path),
        "active_run": str(active_path),
    }
    active_path.write_text(json.dumps(loop_result, indent=2), encoding="utf8")
    return loop_result
