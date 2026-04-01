from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import options_chatbot as oc
import wfo_optimizer as wfo
from forward_options_ledger import summarize_forward_holdout
from metric_truth_audit import build_metric_truth_report
from scripts.autoresearch_governance import (
    DEFAULT_PHASE_MANIFEST,
    FORWARD_HOLDOUT_TRUTH_SOURCE,
    build_baseline_compatibility,
    build_decision_packet,
    build_evidence_bundle,
    build_experiment_fingerprint,
    load_batch_manifest,
    load_phase_manifest,
    render_decision_md,
    write_operator_state,
)
from wfo_optimizer import (
    IMPORTED_DAILY_TRUTH_SOURCE,
    IMPORTED_TRUTH_SOURCE,
    MIN_IMPORTED_QUOTE_COVERAGE_PCT,
    SYNTHETIC_TRUTH_SOURCE,
    build_live_options_trade_policy,
    build_options_experiment_matrix,
    build_playbook_discovery_report,
    build_options_stability_report,
    build_truth_lane_comparison,
    run_historical_backtest,
)

DEFAULT_LOOKBACK_YEARS = (1, 2)
DEFAULT_PRICING_LANES = ("mid", "pessimistic")
DEFAULT_N_PICKS = 1
DEFAULT_IV_ADJ = 1.2
DEFAULT_PLAYBOOK = "broad"
DEFAULT_WINDOW_MODE = "full"
TRUTH_LANE_CHOICES = (
    SYNTHETIC_TRUTH_SOURCE,
    IMPORTED_TRUTH_SOURCE,
    IMPORTED_DAILY_TRUTH_SOURCE,
)
ROLLING_WINDOW_DAYS = 182
ROLLING_WINDOW_STEP_DAYS = 91
ROLLING_CATASTROPHIC_PF_FLOOR = 0.85


class ResearchCycleError(RuntimeError):
    """Raised when a research cycle cannot complete successfully."""


def _normalize_truth_lane(value: Optional[str]) -> str:
    normalized = str(value or SYNTHETIC_TRUTH_SOURCE).strip().lower() or SYNTHETIC_TRUTH_SOURCE
    if normalized == "synthetic":
        normalized = SYNTHETIC_TRUTH_SOURCE
    if normalized not in TRUTH_LANE_CHOICES:
        raise ResearchCycleError(f"Unsupported truth lane: {value}")
    return normalized


def _uses_imported_truth(truth_lane: str) -> bool:
    return str(truth_lane or "").strip().lower() in {
        IMPORTED_TRUTH_SOURCE,
        IMPORTED_DAILY_TRUTH_SOURCE,
    }


def _safe_slug(value: str) -> str:
    text = str(value or "").strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = cleaned.strip("-_")
    return cleaned or "research-cycle"


def _resolve_input_path(root_dir: Path, value: str) -> Path:
    raw = Path(value)
    return raw if raw.is_absolute() else root_dir / raw


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except FileNotFoundError as exc:
        raise ResearchCycleError(f"Required artifact is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ResearchCycleError(f"Artifact is not valid JSON: {path}") from exc


def _repo_git_sha(root_dir: Path) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root_dir,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def _command_display(command: Sequence[str]) -> str:
    parts: list[str] = []
    for item in command:
        parts.append("python" if item == sys.executable else str(item))
    return " ".join(parts)


def _mandatory_test_commands() -> list[list[str]]:
    return [["npm", "run", "verify"]]


def _resolved_command(command: Sequence[str]) -> list[str]:
    resolved = [str(item) for item in command]
    if not resolved:
        return resolved
    if os.name == "nt" and resolved[0].lower() == "npm":
        npm_cmd = shutil.which("npm.cmd")
        if npm_cmd:
            resolved[0] = npm_cmd
    return resolved


def run_mandatory_regressions(root_dir: Path) -> dict[str, Any]:
    commands = _mandatory_test_commands()
    command_results: list[dict[str, Any]] = []
    all_passed = True

    for command in commands:
        resolved_command = _resolved_command(command)
        proc = subprocess.run(
            resolved_command,
            cwd=root_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        passed = proc.returncode == 0
        all_passed = all_passed and passed
        command_results.append(
            {
                "command": _command_display(command),
                "returncode": int(proc.returncode),
                "passed": passed,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "commands": command_results,
        "all_passed": all_passed,
    }


def _render_test_report(report: dict[str, Any]) -> str:
    lines: list[str] = [
        f"Generated at: {report.get('generated_at')}",
        f"All passed: {report.get('all_passed')}",
    ]
    for item in report.get("commands") or []:
        lines.extend(
            [
                "",
                f"$ {item.get('command')}",
                f"returncode: {item.get('returncode')}",
                "",
                "stdout:",
                str(item.get("stdout") or "").rstrip() or "(empty)",
                "",
                "stderr:",
                str(item.get("stderr") or "").rstrip() or "(empty)",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


@contextmanager
def _temporary_results_file(temp_path: Path):
    previous = wfo.WFO_RESULTS_FILE
    wfo.WFO_RESULTS_FILE = str(temp_path)
    try:
        yield
    finally:
        wfo.WFO_RESULTS_FILE = previous


@contextmanager
def _temporary_validation_results_dir(root: Path):
    previous_dir = wfo.OPTIONS_VALIDATION_RESULTS_DIR
    previous_latest = wfo.OPTIONS_VALIDATION_LATEST_FILE
    previous_daily_latest = wfo.OPTIONS_VALIDATION_DAILY_LATEST_FILE
    root.mkdir(parents=True, exist_ok=True)
    wfo.OPTIONS_VALIDATION_RESULTS_DIR = str(root)
    wfo.OPTIONS_VALIDATION_LATEST_FILE = str(root / "latest.json")
    wfo.OPTIONS_VALIDATION_DAILY_LATEST_FILE = str(root / "latest_daily.json")
    try:
        yield
    finally:
        wfo.OPTIONS_VALIDATION_RESULTS_DIR = previous_dir
        wfo.OPTIONS_VALIDATION_LATEST_FILE = previous_latest
        wfo.OPTIONS_VALIDATION_DAILY_LATEST_FILE = previous_daily_latest


@contextmanager
def _temporary_replay_universe(symbols: Optional[Sequence[str]]):
    if not symbols:
        yield
        return
    normalized = [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()]
    previous_watchlist = list(wfo.DEFAULT_WATCHLIST)
    previous_imported_universe = tuple(wfo.IMPORTED_VALIDATION_UNIVERSE)
    wfo.DEFAULT_WATCHLIST = list(normalized)
    wfo.IMPORTED_VALIDATION_UNIVERSE = tuple(normalized)
    try:
        yield
    finally:
        wfo.DEFAULT_WATCHLIST = previous_watchlist
        wfo.IMPORTED_VALIDATION_UNIVERSE = previous_imported_universe


def _merge_profile_overrides(
    base_profiles: dict[str, dict[str, Any]],
    overrides: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    merged = copy.deepcopy(base_profiles)
    equity_overrides = dict(overrides or {})
    for section_name, section_value in equity_overrides.items():
        if isinstance(section_value, dict) and isinstance(merged["equity"].get(section_name), dict):
            merged["equity"][section_name].update(copy.deepcopy(section_value))
        else:
            merged["equity"][section_name] = copy.deepcopy(section_value)
    return merged


def _replace_profiles(target: Any, profiles: dict[str, dict[str, Any]]) -> None:
    target.STRATEGY_PROFILES.clear()
    target.STRATEGY_PROFILES.update(copy.deepcopy(profiles))
    target.STRATEGY_PROFILE = target.STRATEGY_PROFILES["equity"]


@contextmanager
def _temporary_profile_overrides(overrides: Optional[dict[str, Any]]):
    if not overrides:
        yield
        return
    previous_oc_profiles = copy.deepcopy(oc.STRATEGY_PROFILES)
    previous_wfo_profiles = copy.deepcopy(wfo.STRATEGY_PROFILES)
    try:
        merged_profiles = _merge_profile_overrides(previous_oc_profiles, dict(overrides or {}))
        _replace_profiles(oc, merged_profiles)
        _replace_profiles(wfo, merged_profiles)
        yield
    finally:
        _replace_profiles(oc, previous_oc_profiles)
        _replace_profiles(wfo, previous_wfo_profiles)


def _load_watchlist_manifest(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    symbols = payload.get("symbols") or payload.get("watchlist") or payload.get("watchlist_symbols")
    if not isinstance(symbols, list) or not symbols:
        raise ResearchCycleError(
            f"Watchlist manifest must define a non-empty symbol list in 'symbols': {path}"
        )
    normalized_symbols: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        normalized_symbols.append(symbol)
    if not normalized_symbols:
        raise ResearchCycleError(f"Watchlist manifest did not produce any valid symbols: {path}")
    return {
        "path": str(path),
        "label": payload.get("id") or payload.get("name") or path.stem,
        "symbols": normalized_symbols,
        "raw": payload,
    }


def _proposal_family_matches(slug: str, allowed_families: Sequence[str]) -> bool:
    if not allowed_families:
        return True
    normalized_slug = str(slug or "").strip().lower()
    return any(normalized_slug.startswith(str(item).strip().lower()) for item in allowed_families)


def _apply_phase_and_batch_rules(
    *,
    root_dir: Path,
    mode: str,
    slug: str,
    phase_manifest: Optional[dict[str, Any]],
    batch_manifest: Optional[dict[str, Any]],
    cohort_id: Optional[str],
    compare_to_path: Optional[Path],
    playbooks: list[str],
    truth_lane: str,
    window_mode: str,
    allow_phase_override: bool,
) -> dict[str, Any]:
    resolved_compare_to = compare_to_path
    resolved_playbooks = list(playbooks)
    resolved_truth_lane = str(truth_lane)
    resolved_window_mode = str(window_mode)
    resolved_watchlist_symbols: list[str] = []
    resolved_watchlist_manifest = None
    cohort = None
    required_baseline_id = None

    if phase_manifest is not None:
        required_baseline_id = phase_manifest.get("required_baseline_control")
        if mode == "search" and phase_manifest.get("freeze_search") and not allow_phase_override:
            raise ResearchCycleError(
                f"Phase {phase_manifest['phase_id']} is frozen for truth-first validation. Use --allow-phase-override only for an explicit manual bypass."
            )
        if resolved_truth_lane not in set(phase_manifest.get("allowed_truth_lanes") or []):
            raise ResearchCycleError(
                f"Truth lane {resolved_truth_lane} is not allowed by phase {phase_manifest['phase_id']}."
            )
        if mode == "validation":
            if not cohort_id:
                raise ResearchCycleError("Validation mode requires --cohort-id.")
            cohort = (phase_manifest.get("cohort_map") or {}).get(str(cohort_id))
            if not cohort:
                raise ResearchCycleError(
                    f"Cohort {cohort_id} is not defined in phase {phase_manifest['phase_id']}."
                )
            resolved_playbooks = list(cohort.get("playbooks") or resolved_playbooks)
            resolved_watchlist_symbols = list(phase_manifest.get("required_watchlist_symbols") or [])
            resolved_watchlist_manifest = {
                "path": phase_manifest.get("path"),
                "label": phase_manifest.get("phase_id"),
                "symbols": resolved_watchlist_symbols,
                "raw": phase_manifest.get("raw") or {},
            }
        elif not allow_phase_override and not _proposal_family_matches(slug, phase_manifest.get("allowed_proposal_families") or []):
            raise ResearchCycleError(
                f"Proposal slug {slug} is not allowed in phase {phase_manifest['phase_id']}."
            )

    if batch_manifest is not None:
        if mode != "search":
            raise ResearchCycleError("Batch manifests are only supported in search mode.")
        if slug not in set(batch_manifest.get("challenger_slugs") or []) and slug != batch_manifest.get("control_slug"):
            raise ResearchCycleError(
                f"Slug {slug} is not part of batch {batch_manifest['batch_id']}."
            )
        if batch_manifest.get("playbooks"):
            resolved_playbooks = list(batch_manifest.get("playbooks") or resolved_playbooks)
        if resolved_truth_lane not in set(batch_manifest.get("truth_lanes") or []):
            raise ResearchCycleError(
                f"Truth lane {resolved_truth_lane} is not part of batch {batch_manifest['batch_id']}."
            )
        resolved_window_mode = batch_manifest.get("window_mode") or resolved_window_mode
        required_baseline_id = batch_manifest.get("control_slug") or required_baseline_id
        if slug != batch_manifest.get("control_slug"):
            if resolved_compare_to is None:
                control_run = batch_manifest.get("control_run")
                if not control_run:
                    raise ResearchCycleError(
                        f"Batch {batch_manifest['batch_id']} requires a control run for challenger comparisons."
                    )
                resolved_compare_to = _resolve_input_path(root_dir, control_run)
        if resolved_compare_to is None and batch_manifest.get("required_baseline_compatibility"):
            raise ResearchCycleError(
                f"Batch {batch_manifest['batch_id']} requires a compatible baseline comparison."
            )

    return {
        "compare_to_path": resolved_compare_to,
        "playbooks": resolved_playbooks,
        "truth_lane": resolved_truth_lane,
        "window_mode": resolved_window_mode,
        "watchlist_symbols": resolved_watchlist_symbols,
        "watchlist_manifest": resolved_watchlist_manifest,
        "cohort": cohort,
        "required_baseline_id": required_baseline_id,
    }


def _effective_pricing_lanes(
    *,
    truth_lane: str,
    pricing_lanes: Sequence[str],
) -> list[str]:
    if _uses_imported_truth(truth_lane):
        return [truth_lane]
    return [str(item) for item in pricing_lanes]


def _primary_pricing_lane(truth_lane: str) -> str:
    return truth_lane if _uses_imported_truth(truth_lane) else "pessimistic"


def _scenario_key(cell: dict[str, Any]) -> str:
    return "|".join(
        [
            f"lookback={int(cell['lookback_years'])}",
            f"n_picks={int(cell['n_picks'])}",
            f"iv_adj={float(cell['iv_adj']):.2f}",
            f"lane={cell['pricing_lane']}",
            f"playbook={cell['playbook']}",
        ]
    )


def _result_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_at": result.get("run_at"),
        "truth_source": result.get("truth_source"),
        "total_days": result.get("total_days"),
        "total_trades": result.get("total_trades"),
        "priced_trade_count": result.get("priced_trade_count", result.get("total_trades")),
        "unpriced_trade_count": result.get("unpriced_trade_count", 0),
        "quote_coverage_pct": result.get("quote_coverage_pct", 100.0),
        "avg_picks_per_day": result.get("avg_picks_per_day"),
        "win_rate_pct": result.get("win_rate_pct"),
        "full_hit_rate_pct": result.get("full_hit_rate_pct"),
        "directional_accuracy_pct": result.get("directional_accuracy_pct"),
        "profit_factor": result.get("profit_factor"),
        "avg_pnl_pct": result.get("avg_pnl_pct"),
        "sharpe": result.get("sharpe"),
        "max_drawdown_pct": result.get("max_drawdown_pct"),
        "selection_source_counts": result.get("selection_source_counts") or {},
    }


def build_matrix(
    *,
    playbooks: list[str],
    lookback_years: Sequence[int] = DEFAULT_LOOKBACK_YEARS,
    pricing_lanes: Sequence[str] = DEFAULT_PRICING_LANES,
    n_picks: int = DEFAULT_N_PICKS,
    iv_adj: float = DEFAULT_IV_ADJ,
    truth_lane: str = SYNTHETIC_TRUTH_SOURCE,
    watchlist_symbols: Optional[Sequence[str]] = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized_truth_lane = _normalize_truth_lane(truth_lane)
    requested_playbooks = list(playbooks) if playbooks else [DEFAULT_PLAYBOOK]
    effective_pricing_lanes = _effective_pricing_lanes(
        truth_lane=normalized_truth_lane,
        pricing_lanes=pricing_lanes,
    )
    primary_scenario = {
        "lookback_years": 2,
        "n_picks": int(n_picks),
        "iv_adj": float(iv_adj),
        "pricing_lane": _primary_pricing_lane(normalized_truth_lane),
        "playbook": requested_playbooks[0],
        "truth_lane": normalized_truth_lane,
    }
    cells: list[dict[str, Any]] = []
    primary_result: Optional[dict[str, Any]] = None

    with tempfile.TemporaryDirectory() as tmp_dir:
        scratch_root = Path(tmp_dir)
        validation_root = scratch_root / "options_validation_runs"
        with _temporary_validation_results_dir(validation_root), _temporary_replay_universe(watchlist_symbols):
            for playbook in requested_playbooks:
                for years in lookback_years:
                    for pricing_lane in effective_pricing_lanes:
                        scenario = {
                            "lookback_years": int(years),
                            "n_picks": int(n_picks),
                            "iv_adj": float(iv_adj),
                            "pricing_lane": str(pricing_lane),
                            "playbook": str(playbook),
                            "truth_lane": normalized_truth_lane,
                        }
                        scratch_file = scratch_root / f"{_safe_slug(playbook)}_{years}_{_safe_slug(pricing_lane)}.json"
                        with _temporary_results_file(scratch_file):
                            result = run_historical_backtest(
                                lookback_years=int(years),
                                n_picks=int(n_picks),
                                iv_adj=float(iv_adj),
                                pricing_lane=str(pricing_lane),
                                playbook=str(playbook),
                                truth_lane=normalized_truth_lane,
                            )

                        cell = dict(scenario)
                        cell["matrix_key"] = _scenario_key(cell)
                        cell["error"] = result.get("error")
                        cell["summary"] = _result_summary(result) if not result.get("error") else None
                        cell["effective_pricing_lane"] = result.get("pricing_lane")
                        cells.append(cell)

                        if scenario == primary_scenario:
                            primary_result = result

    if primary_result is None:
        raise ResearchCycleError("Primary scenario did not execute.")

    matrix = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "defaults": {
            "lookback_years": [int(item) for item in lookback_years],
            "requested_pricing_lanes": [str(item) for item in pricing_lanes],
            "effective_pricing_lanes": effective_pricing_lanes,
            "n_picks": int(n_picks),
            "iv_adj": float(iv_adj),
            "playbooks": requested_playbooks,
            "truth_lane": normalized_truth_lane,
            "watchlist_symbols": [str(item) for item in watchlist_symbols or []],
        },
        "primary_scenario": primary_scenario,
        "cells": cells,
    }
    return matrix, primary_result


def _report_has_error(report: dict[str, Any]) -> bool:
    return bool(report.get("error"))


def _primary_report_bundle(result: dict[str, Any]) -> dict[str, Any]:
    experiments = build_options_experiment_matrix(result=result)
    stability = build_options_stability_report(result=result)
    policy = build_live_options_trade_policy(result=result)
    metric_truth = build_metric_truth_report(result=result)

    report_map = {
        "experiments": experiments,
        "stability": stability,
        "policy": policy,
        "metric_truth": metric_truth,
    }
    errors = {
        name: payload.get("error")
        for name, payload in report_map.items()
        if _report_has_error(payload)
    }
    if errors:
        joined = ", ".join(f"{name}: {message}" for name, message in sorted(errors.items()))
        raise ResearchCycleError(f"Primary report bundle failed: {joined}")
    return report_map


def _require_quote_coverage(result: dict[str, Any], threshold: Optional[float]) -> None:
    if threshold is None or not _uses_imported_truth(str(result.get("truth_source") or "")):
        return
    coverage = float(result.get("quote_coverage_pct") or 0.0)
    if coverage < float(threshold):
        raise ResearchCycleError(
            f"Imported quote coverage {coverage:.1f}% is below the required floor of {float(threshold):.1f}%."
        )


def _load_primary_report_result(compare_dir: Path) -> Optional[dict[str, Any]]:
    path = compare_dir / "primary_report.json"
    if not path.exists():
        return None
    payload = _read_json(path)
    result = payload.get("result")
    return result if isinstance(result, dict) else None


def _parse_trade_date(trade: dict[str, Any]) -> Optional[datetime]:
    raw = trade.get("date") or trade.get("entry_date") or trade.get("entry_date_utc")
    if raw in (None, ""):
        return None
    text = str(raw).strip()
    for candidate in (text, text[:10]):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def _window_trade_summary(trades: list[dict[str, Any]]) -> dict[str, Any]:
    pnls = [float(trade.get("pnl_pct", 0.0) or 0.0) for trade in trades]
    total = len(pnls)
    gross_profit = sum(value for value in pnls if value > 0)
    gross_loss = abs(sum(value for value in pnls if value < 0))
    directional = [
        1.0
        for trade in trades
        if trade.get("directional_correct") is True
    ]
    directional_total = [
        trade
        for trade in trades
        if trade.get("directional_correct") is not None
    ]
    profit_factor = None
    if total:
        if gross_loss > 0:
            profit_factor = round(gross_profit / gross_loss, 2)
        elif gross_profit > 0:
            profit_factor = round(gross_profit, 2)
        else:
            profit_factor = 0.0
    return {
        "total_trades": total,
        "profit_factor": profit_factor,
        "avg_pnl_pct": round(sum(pnls) / total, 2) if total else None,
        "directional_accuracy_pct": round(100.0 * len(directional) / len(directional_total), 1)
        if directional_total
        else None,
    }


def _iter_rolling_windows(
    *,
    start_at: datetime,
    end_at: datetime,
    window_days: int = ROLLING_WINDOW_DAYS,
    step_days: int = ROLLING_WINDOW_STEP_DAYS,
) -> Iterable[tuple[datetime, datetime]]:
    cursor = start_at
    delta_window = timedelta(days=int(window_days))
    delta_step = timedelta(days=int(step_days))
    while cursor <= end_at:
        yield cursor, cursor + delta_window
        cursor += delta_step


def build_rolling_window_report(
    *,
    current_result: dict[str, Any],
    baseline_result: Optional[dict[str, Any]] = None,
    window_days: int = ROLLING_WINDOW_DAYS,
    step_days: int = ROLLING_WINDOW_STEP_DAYS,
    catastrophic_pf_floor: float = ROLLING_CATASTROPHIC_PF_FLOOR,
) -> dict[str, Any]:
    current_trades = [trade for trade in list(current_result.get("trades") or []) if _parse_trade_date(trade) is not None]
    baseline_trades = [trade for trade in list((baseline_result or {}).get("trades") or []) if _parse_trade_date(trade) is not None]
    dated_trades = current_trades + baseline_trades
    if not dated_trades:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "available": False,
            "window_days": int(window_days),
            "step_days": int(step_days),
            "windows": [],
            "wins_vs_baseline": 0,
            "losses_vs_baseline": 0,
            "ties_vs_baseline": 0,
            "catastrophic_window_count": 0,
            "notes": ["No dated trades were available for rolling-window analysis."],
        }

    start_at = min(_parse_trade_date(trade) for trade in dated_trades if _parse_trade_date(trade) is not None)
    end_at = max(_parse_trade_date(trade) for trade in dated_trades if _parse_trade_date(trade) is not None)
    windows: list[dict[str, Any]] = []
    wins = 0
    losses = 0
    ties = 0
    catastrophic = 0
    for window_start, window_end in _iter_rolling_windows(
        start_at=start_at,
        end_at=end_at,
        window_days=window_days,
        step_days=step_days,
    ):
        current_window = [
            trade for trade in current_trades
            if window_start <= _parse_trade_date(trade) < window_end
        ]
        baseline_window = [
            trade for trade in baseline_trades
            if window_start <= _parse_trade_date(trade) < window_end
        ]
        current_summary = _window_trade_summary(current_window)
        baseline_summary = _window_trade_summary(baseline_window)
        outcome = "unavailable"
        if baseline_result is not None:
            current_pf = current_summary.get("profit_factor")
            baseline_pf = baseline_summary.get("profit_factor")
            current_avg = current_summary.get("avg_pnl_pct")
            baseline_avg = baseline_summary.get("avg_pnl_pct")
            if current_summary["total_trades"] and baseline_summary["total_trades"]:
                if (
                    current_pf is not None
                    and baseline_pf is not None
                    and current_pf > baseline_pf
                    and (current_avg is not None and baseline_avg is not None and current_avg >= baseline_avg)
                ):
                    outcome = "win"
                    wins += 1
                elif current_summary == baseline_summary:
                    outcome = "tie"
                    ties += 1
                else:
                    outcome = "loss"
                    losses += 1
        current_pf = current_summary.get("profit_factor")
        if current_summary["total_trades"] and current_pf is not None and current_pf < float(catastrophic_pf_floor):
            catastrophic += 1
        windows.append(
            {
                "start_date": window_start.date().isoformat(),
                "end_date": (window_end - timedelta(days=1)).date().isoformat(),
                "current": current_summary,
                "baseline": baseline_summary if baseline_result is not None else None,
                "outcome_vs_baseline": outcome if baseline_result is not None else None,
            }
        )
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "available": True,
        "window_days": int(window_days),
        "step_days": int(step_days),
        "windows": windows,
        "wins_vs_baseline": wins,
        "losses_vs_baseline": losses,
        "ties_vs_baseline": ties,
        "catastrophic_window_count": catastrophic,
    }


def build_concentration_summary(result: dict[str, Any]) -> dict[str, Any]:
    trades = list(result.get("trades") or [])
    summary: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_trades": len(trades),
        "dimensions": {},
    }
    for field in ("ticker", "sector", "market_regime"):
        counts: Counter[str] = Counter()
        for trade in trades:
            raw = trade.get(field) or "Unknown"
            value = str(raw).strip().upper() if field == "ticker" else str(raw).strip() or "Unknown"
            counts[value] += 1
        total = sum(counts.values())
        top = [
            {
                "value": name,
                "count": count,
                "share_pct": round(100.0 * count / total, 1) if total else 0.0,
            }
            for name, count in counts.most_common(5)
        ]
        summary["dimensions"][field] = {
            "unique_count": len(counts),
            "top_values": top,
            "top_share_pct": top[0]["share_pct"] if top else 0.0,
        }
    return summary


def build_quote_coverage_sensitivity(
    *,
    result: dict[str, Any],
    require_quote_coverage: Optional[float],
) -> dict[str, Any]:
    coverage = float(result.get("quote_coverage_pct") or 0.0)
    base_floor = float(require_quote_coverage if require_quote_coverage is not None else MIN_IMPORTED_QUOTE_COVERAGE_PCT)
    stricter_floor = base_floor + 10.0
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "quote_coverage_pct": round(coverage, 1),
        "base_floor_pct": round(base_floor, 1),
        "stricter_floor_pct": round(stricter_floor, 1),
        "base_floor_pass": coverage >= base_floor,
        "stricter_floor_pass": coverage >= stricter_floor,
    }


def _run_primary_scenario(
    *,
    playbook: str,
    truth_lane: str,
    n_picks: int,
    iv_adj: float,
    watchlist_symbols: Optional[Sequence[str]],
    profile_overrides: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    normalized_truth_lane = _normalize_truth_lane(truth_lane)
    with tempfile.TemporaryDirectory() as tmp_dir:
        scratch_root = Path(tmp_dir)
        validation_root = scratch_root / "options_validation_runs"
        with (
            _temporary_validation_results_dir(validation_root),
            _temporary_replay_universe(watchlist_symbols),
            _temporary_profile_overrides(profile_overrides),
        ):
            with _temporary_results_file(scratch_root / "primary.json"):
                return run_historical_backtest(
                    lookback_years=2,
                    n_picks=int(n_picks),
                    iv_adj=float(iv_adj),
                    pricing_lane=_primary_pricing_lane(normalized_truth_lane),
                    playbook=str(playbook),
                    truth_lane=normalized_truth_lane,
                )


def build_falsification_report(
    *,
    primary_result: dict[str, Any],
    baseline_primary_result: Optional[dict[str, Any]],
    rolling_report: Optional[dict[str, Any]],
    truth_lane_comparison_report: Optional[dict[str, Any]],
    concentration_summary: dict[str, Any],
    quote_coverage_sensitivity: Optional[dict[str, Any]],
) -> dict[str, Any]:
    primary_summary = _result_summary(primary_result)
    baseline_summary = _result_summary(baseline_primary_result or {}) if baseline_primary_result else None
    improves_main_lane = None
    if baseline_summary:
        current_pf = primary_summary.get("profit_factor")
        baseline_pf = baseline_summary.get("profit_factor")
        current_avg = primary_summary.get("avg_pnl_pct")
        baseline_avg = baseline_summary.get("avg_pnl_pct")
        improves_main_lane = bool(
            current_pf is not None
            and baseline_pf is not None
            and current_pf > baseline_pf
            and current_avg is not None
            and baseline_avg is not None
            and current_avg > baseline_avg
        )
    unsupported_rate = None
    if truth_lane_comparison_report:
        synthetic_total = int((truth_lane_comparison_report.get("synthetic") or {}).get("total_trades") or 0)
        unsupported = int(truth_lane_comparison_report.get("unsupported_by_import_count") or 0)
        unsupported_rate = round(100.0 * unsupported / synthetic_total, 1) if synthetic_total else None
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "acceptance_rule": {
            "improves_main_lane_vs_baseline": improves_main_lane,
            "catastrophic_window_count": (
                int(rolling_report.get("catastrophic_window_count") or 0)
                if rolling_report
                else None
            ),
            "unsupported_by_import_rate_pct": unsupported_rate,
            "quote_coverage_sensitivity": quote_coverage_sensitivity,
        },
        "main_lane": {
            "current": primary_summary,
            "baseline": baseline_summary,
        },
        "rolling_windows": rolling_report,
        "truth_lane_comparison": truth_lane_comparison_report,
        "concentration": concentration_summary,
    }


def _load_compare_artifacts(compare_dir: Path) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    matrix = _read_json(compare_dir / "matrix.json")
    stability = _read_json(compare_dir / "stability.json")
    policy = _read_json(compare_dir / "policy.json")
    return matrix, stability, policy


def _load_manifest_if_exists(run_dir: Path) -> Optional[dict[str, Any]]:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists() or not manifest_path.is_file():
        return None
    return _read_json(manifest_path)


def _normalized_manifest_symbols(manifest: Optional[dict[str, Any]]) -> list[str]:
    raw_symbols = ((manifest or {}).get("watchlist_manifest") or {}).get("symbols") or []
    normalized: list[str] = []
    for raw in raw_symbols:
        symbol = str(raw or "").strip().upper()
        if symbol:
            normalized.append(symbol)
    return normalized


def _assert_manifest_context_compatible(
    *,
    current_run_dir: Path,
    compare_to_dir: Path,
    current_manifest: Optional[dict[str, Any]],
    baseline_manifest: Optional[dict[str, Any]],
    current_git_sha: Optional[str],
) -> None:
    if current_manifest is None or baseline_manifest is None:
        return

    reasons: list[str] = []
    current_sha = str(
        current_manifest.get("git_sha")
        or current_git_sha
        or ""
    ).strip()
    baseline_sha = str(baseline_manifest.get("git_sha") or "").strip()
    if current_sha and baseline_sha and current_sha != baseline_sha:
        reasons.append(f"git_sha differs ({baseline_sha} vs {current_sha})")

    for field in ("truth_lane", "window_mode"):
        current_value = str(current_manifest.get(field) or "").strip()
        baseline_value = str(baseline_manifest.get(field) or "").strip()
        if current_value and baseline_value and current_value != baseline_value:
            reasons.append(f"{field} differs ({baseline_value} vs {current_value})")

    current_symbols = _normalized_manifest_symbols(current_manifest)
    baseline_symbols = _normalized_manifest_symbols(baseline_manifest)
    if current_symbols != baseline_symbols:
        reasons.append(
            "watchlist symbols differ "
            f"({','.join(baseline_symbols) or '<none>'} vs {','.join(current_symbols) or '<none>'})"
        )

    if reasons:
        raise ResearchCycleError(
            "Compare run is incompatible: "
            + "; ".join(reasons)
            + f" (baseline={compare_to_dir}, current={current_run_dir})"
        )


def _delta(current: Any, baseline: Any) -> Optional[float]:
    if current is None or baseline is None:
        return None
    try:
        return round(float(current) - float(baseline), 2)
    except (TypeError, ValueError):
        return None


def build_comparison(
    *,
    current_run_dir: Path,
    current_matrix: dict[str, Any],
    current_stability: dict[str, Any],
    current_policy: dict[str, Any],
    compare_to_dir: Path,
    current_manifest: Optional[dict[str, Any]] = None,
    current_git_sha: Optional[str] = None,
) -> dict[str, Any]:
    if not compare_to_dir.exists():
        raise ResearchCycleError(f"Compare run does not exist: {compare_to_dir}")
    if not compare_to_dir.is_dir():
        raise ResearchCycleError(f"Compare path is not a directory: {compare_to_dir}")

    baseline_matrix, baseline_stability, baseline_policy = _load_compare_artifacts(compare_to_dir)
    baseline_manifest = _load_manifest_if_exists(compare_to_dir)
    _assert_manifest_context_compatible(
        current_run_dir=current_run_dir,
        compare_to_dir=compare_to_dir,
        current_manifest=current_manifest,
        baseline_manifest=baseline_manifest,
        current_git_sha=current_git_sha,
    )

    current_primary = dict(current_matrix.get("primary_scenario") or {})
    baseline_primary = dict(baseline_matrix.get("primary_scenario") or {})
    current_primary.setdefault("truth_lane", SYNTHETIC_TRUTH_SOURCE)
    baseline_primary.setdefault("truth_lane", SYNTHETIC_TRUTH_SOURCE)
    if current_primary != baseline_primary:
        raise ResearchCycleError(
            "Compare run is incompatible: primary scenario does not match the current run."
        )

    current_cells = {
        str(item.get("matrix_key") or _scenario_key(item)): item
        for item in current_matrix.get("cells") or []
    }
    baseline_cells = {
        str(item.get("matrix_key") or _scenario_key(item)): item
        for item in baseline_matrix.get("cells") or []
    }

    if set(current_cells) != set(baseline_cells):
        missing_in_baseline = sorted(set(current_cells) - set(baseline_cells))
        missing_in_current = sorted(set(baseline_cells) - set(current_cells))
        details: list[str] = []
        if missing_in_baseline:
            details.append(f"missing in baseline: {', '.join(missing_in_baseline)}")
        if missing_in_current:
            details.append(f"missing in current: {', '.join(missing_in_current)}")
        raise ResearchCycleError(
            "Compare run is incompatible: matrix cells differ"
            + (f" ({'; '.join(details)})" if details else ".")
        )

    total_day_mismatches: list[str] = []
    for matrix_key in sorted(current_cells):
        current_summary = current_cells[matrix_key].get("summary") or {}
        baseline_summary = baseline_cells[matrix_key].get("summary") or {}
        current_total_days = current_summary.get("total_days")
        baseline_total_days = baseline_summary.get("total_days")
        if current_total_days is None or baseline_total_days is None:
            continue
        if current_total_days != baseline_total_days:
            total_day_mismatches.append(
                f"{matrix_key} ({baseline_total_days} vs {current_total_days})"
            )
    if total_day_mismatches:
        sample = "; ".join(total_day_mismatches[:4])
        if len(total_day_mismatches) > 4:
            sample += f"; +{len(total_day_mismatches) - 4} more"
        raise ResearchCycleError(
            "Compare run is incompatible: total_days differ between runs "
            f"({sample})"
        )

    cell_comparisons: list[dict[str, Any]] = []
    for matrix_key in sorted(current_cells):
        current_cell = current_cells[matrix_key]
        baseline_cell = baseline_cells[matrix_key]
        current_summary = current_cell.get("summary") or {}
        baseline_summary = baseline_cell.get("summary") or {}
        cell_comparisons.append(
            {
                "matrix_key": matrix_key,
                "scenario": {
                    "lookback_years": current_cell.get("lookback_years"),
                    "n_picks": current_cell.get("n_picks"),
                    "iv_adj": current_cell.get("iv_adj"),
                    "pricing_lane": current_cell.get("pricing_lane"),
                    "playbook": current_cell.get("playbook"),
                    "truth_lane": current_cell.get("truth_lane", SYNTHETIC_TRUTH_SOURCE),
                },
                "baseline": baseline_summary,
                "current": current_summary,
                "deltas": {
                    "total_trades": _delta(current_summary.get("total_trades"), baseline_summary.get("total_trades")),
                    "profit_factor": _delta(current_summary.get("profit_factor"), baseline_summary.get("profit_factor")),
                    "avg_pnl_pct": _delta(current_summary.get("avg_pnl_pct"), baseline_summary.get("avg_pnl_pct")),
                    "directional_accuracy_pct": _delta(
                        current_summary.get("directional_accuracy_pct"),
                        baseline_summary.get("directional_accuracy_pct"),
                    ),
                    "max_drawdown_pct": _delta(
                        current_summary.get("max_drawdown_pct"),
                        baseline_summary.get("max_drawdown_pct"),
                    ),
                },
            }
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "current_run_dir": str(current_run_dir),
        "baseline_run_dir": str(compare_to_dir),
        "current_primary_scenario": current_primary,
        "baseline_primary_scenario": baseline_primary,
        "cells": cell_comparisons,
        "primary_status": {
            "stability_overall_status": {
                "baseline": baseline_stability.get("overall_status"),
                "current": current_stability.get("overall_status"),
                "changed": baseline_stability.get("overall_status") != current_stability.get("overall_status"),
            },
            "promotion_status": {
                "baseline": (baseline_policy.get("scan_policy") or {}).get("promotion_status"),
                "current": (current_policy.get("scan_policy") or {}).get("promotion_status"),
                "changed": (baseline_policy.get("scan_policy") or {}).get("promotion_status")
                != (current_policy.get("scan_policy") or {}).get("promotion_status"),
            },
        },
    }


def _decision_stub(slug: str) -> str:
    return "\n".join(
        [
            f"# Decision Stub: {slug}",
            "",
            "## Recommendation",
            "",
            "- `promote`",
            "- `hold`",
            "- `reject`",
            "",
            "## Summary",
            "",
            "Fill in the final human decision after reviewing the artifacts in this run directory.",
            "",
            "## Evidence Reviewed",
            "",
            "- `tests.txt`",
            "- `matrix.json`",
            "- `primary_report.json`",
            "- `experiments.json`",
            "- `stability.json`",
            "- `policy.json`",
            "- `metric_truth.json`",
            "- `comparison.json` when present",
            "- `rolling_windows.json` when present",
            "- `discovery.json`",
            "- `truth_lane_comparison.json` when present",
            "- `falsification.json`",
            "",
        ]
    )


def _build_manifest(
    *,
    slug: str,
    proposal_path: Path,
    compare_to: Optional[Path],
    playbooks: list[str],
    truth_lane: str,
    watchlist_manifest: Optional[dict[str, Any]],
    window_mode: str,
    require_quote_coverage: Optional[float],
    mode: str,
    phase_id: Optional[str],
    cohort_id: Optional[str],
    batch_id: Optional[str],
    baseline_compatibility: Optional[dict[str, Any]],
    effective_override_diff: Optional[dict[str, Any]],
) -> dict[str, Any]:
    requested_playbooks = list(playbooks) if playbooks else [DEFAULT_PLAYBOOK]
    normalized_truth_lane = _normalize_truth_lane(truth_lane)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "running",
        "slug": slug,
        "mode": str(mode),
        "phase_id": phase_id,
        "cohort_id": cohort_id,
        "batch_id": batch_id,
        "proposal_path": str(proposal_path),
        "compare_to": str(compare_to) if compare_to is not None else None,
        "playbooks": requested_playbooks,
        "truth_lane": normalized_truth_lane,
        "window_mode": str(window_mode),
        "watchlist_manifest": {
            "path": watchlist_manifest.get("path"),
            "label": watchlist_manifest.get("label"),
            "symbols": list(watchlist_manifest.get("symbols") or []),
        }
        if watchlist_manifest is not None
        else None,
        "require_quote_coverage": float(require_quote_coverage) if require_quote_coverage is not None else None,
        "effective_override_diff": effective_override_diff or {},
        "baseline_compatibility": baseline_compatibility or {},
        "experiment_fingerprint": {},
        "defaults": {
            "lookback_years": list(DEFAULT_LOOKBACK_YEARS),
            "requested_pricing_lanes": list(DEFAULT_PRICING_LANES),
            "effective_pricing_lanes": _effective_pricing_lanes(
                truth_lane=normalized_truth_lane,
                pricing_lanes=DEFAULT_PRICING_LANES,
            ),
            "n_picks": DEFAULT_N_PICKS,
            "iv_adj": DEFAULT_IV_ADJ,
            "primary_scenario": {
                "lookback_years": 2,
                "n_picks": DEFAULT_N_PICKS,
                "iv_adj": DEFAULT_IV_ADJ,
                "pricing_lane": _primary_pricing_lane(normalized_truth_lane),
                "playbook": requested_playbooks[0],
                "truth_lane": normalized_truth_lane,
            },
        },
        "mandatory_tests": [_command_display(command) for command in _mandatory_test_commands()],
        "git_sha": None,
        "errors": [],
    }


def _finalize_manifest(
    manifest: dict[str, Any],
    *,
    status: str,
    git_sha: Optional[str],
    error: Optional[str] = None,
) -> dict[str, Any]:
    output = dict(manifest)
    output["status"] = status
    output["git_sha"] = git_sha
    output["completed_at"] = datetime.now().isoformat(timespec="seconds")
    errors = list(output.get("errors") or [])
    if error:
        errors.append(error)
    output["errors"] = errors
    return output


def main(argv: Optional[Sequence[str]] = None, *, root_dir: Optional[Path] = None) -> int:
    parser = argparse.ArgumentParser(description="Run one append-only options autoresearch cycle.")
    parser.add_argument("--slug", required=True, help="Short name for the research run.")
    parser.add_argument("--proposal", required=True, help="Path to the proposal markdown file.")
    parser.add_argument(
        "--mode",
        choices=("search", "validation"),
        help="Whether this run is a search experiment or a frozen validation pass.",
    )
    parser.add_argument(
        "--phase-manifest",
        help=f"Optional phase manifest. Defaults to {DEFAULT_PHASE_MANIFEST} when present.",
    )
    parser.add_argument("--cohort-id", help="Validation cohort id from the phase manifest.")
    parser.add_argument("--batch-manifest", help="Optional batch manifest for grouped search runs.")
    parser.add_argument(
        "--allow-phase-override",
        action="store_true",
        help="Explicitly bypass a frozen phase for local diagnostics.",
    )
    parser.add_argument(
        "--playbook",
        action="append",
        dest="playbooks",
        default=[],
        help="Replay playbook to include. Repeat for multiple playbooks. Defaults to broad.",
    )
    parser.add_argument("--compare-to", help="Optional prior research run directory for baseline comparison.")
    parser.add_argument(
        "--truth-lane",
        default=SYNTHETIC_TRUTH_SOURCE,
        choices=TRUTH_LANE_CHOICES,
        help="Truth source for the matrix. Defaults to synthetic_research.",
    )
    parser.add_argument(
        "--watchlist-set",
        help="Optional JSON manifest that defines the fixed replay watchlist symbols.",
    )
    parser.add_argument(
        "--window-mode",
        default=DEFAULT_WINDOW_MODE,
        choices=("full", "rolling_6m"),
        help="Whether to emit only the full matrix or also a rolling 6-month stress report.",
    )
    parser.add_argument(
        "--require-quote-coverage",
        type=float,
        help="Fail imported-truth runs if quote coverage falls below this percent floor.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    root = Path(root_dir) if root_dir is not None else ROOT
    slug = _safe_slug(args.slug)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = root / "research_runs" / f"{timestamp}_{slug}"
    run_dir.mkdir(parents=True, exist_ok=True)

    proposal_path = _resolve_input_path(root, args.proposal)
    compare_to_path = _resolve_input_path(root, args.compare_to) if args.compare_to else None
    playbooks = list(args.playbooks) if args.playbooks else [DEFAULT_PLAYBOOK]
    truth_lane = _normalize_truth_lane(args.truth_lane)
    watchlist_manifest_path = _resolve_input_path(root, args.watchlist_set) if args.watchlist_set else None
    watchlist_manifest = None
    phase_manifest_path = _resolve_input_path(root, args.phase_manifest) if args.phase_manifest else None
    if phase_manifest_path is None and root.resolve() == ROOT.resolve() and DEFAULT_PHASE_MANIFEST.exists():
        phase_manifest_path = DEFAULT_PHASE_MANIFEST
    try:
        phase_manifest = load_phase_manifest(phase_manifest_path) if phase_manifest_path and phase_manifest_path.exists() else None
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise ResearchCycleError(f"Phase manifest could not be loaded: {exc}") from exc
    batch_manifest_path = _resolve_input_path(root, args.batch_manifest) if args.batch_manifest else None
    try:
        batch_manifest = load_batch_manifest(batch_manifest_path) if batch_manifest_path else None
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        raise ResearchCycleError(f"Batch manifest could not be loaded: {exc}") from exc
    mode = str(args.mode or (phase_manifest.get("mode") if phase_manifest else "search")).strip().lower() or "search"
    if mode not in {"search", "validation"}:
        raise ResearchCycleError(f"Unsupported mode: {mode}")

    try:
        phase_resolution = _apply_phase_and_batch_rules(
            root_dir=root,
            mode=mode,
            slug=slug,
            phase_manifest=phase_manifest,
            batch_manifest=batch_manifest,
            cohort_id=args.cohort_id,
            compare_to_path=compare_to_path,
            playbooks=playbooks,
            truth_lane=truth_lane,
            window_mode=args.window_mode,
            allow_phase_override=bool(args.allow_phase_override),
        )
    except ResearchCycleError as exc:
        manifest = _build_manifest(
            slug=slug,
            proposal_path=proposal_path,
            compare_to=compare_to_path,
            playbooks=playbooks,
            truth_lane=truth_lane,
            watchlist_manifest=watchlist_manifest,
            window_mode=args.window_mode,
            require_quote_coverage=args.require_quote_coverage,
            mode=mode,
            phase_id=phase_manifest.get("phase_id") if phase_manifest else None,
            cohort_id=args.cohort_id,
            batch_id=batch_manifest.get("batch_id") if batch_manifest else None,
            baseline_compatibility={},
            effective_override_diff={},
        )
        _write_json(run_dir / "manifest.json", _finalize_manifest(manifest, status="failed", git_sha=None, error=str(exc)))
        return 1
    compare_to_path = phase_resolution["compare_to_path"]
    playbooks = list(phase_resolution["playbooks"] or playbooks)
    truth_lane = str(phase_resolution["truth_lane"] or truth_lane)
    resolved_window_mode = str(phase_resolution["window_mode"] or args.window_mode)
    cohort = phase_resolution.get("cohort")
    effective_override_diff = dict((cohort or {}).get("overrides") or {})
    required_baseline_id = phase_resolution.get("required_baseline_id")
    phase_watchlist_manifest = phase_resolution.get("watchlist_manifest")

    if watchlist_manifest_path is None and phase_watchlist_manifest is not None:
        watchlist_manifest = phase_watchlist_manifest

    baseline_compatibility = build_baseline_compatibility(
        compare_to=compare_to_path,
        required_baseline_id=required_baseline_id,
        cohort_id=(cohort or {}).get("id"),
        batch_id=batch_manifest.get("batch_id") if batch_manifest else None,
        comparison_generated=False,
    )

    manifest = _build_manifest(
        slug=slug,
        proposal_path=proposal_path,
        compare_to=compare_to_path,
        playbooks=playbooks,
        truth_lane=truth_lane,
        watchlist_manifest=watchlist_manifest,
        window_mode=resolved_window_mode,
        require_quote_coverage=args.require_quote_coverage,
        mode=mode,
        phase_id=phase_manifest.get("phase_id") if phase_manifest else None,
        cohort_id=(cohort or {}).get("id"),
        batch_id=batch_manifest.get("batch_id") if batch_manifest else None,
        baseline_compatibility=baseline_compatibility,
        effective_override_diff=effective_override_diff,
    )
    _write_json(run_dir / "manifest.json", manifest)
    _write_text(run_dir / "decision.md", _decision_stub(slug))

    git_sha = _repo_git_sha(root)

    if not proposal_path.exists():
        manifest = _finalize_manifest(
            manifest,
            status="failed",
            git_sha=git_sha,
            error=f"Proposal file does not exist: {proposal_path}",
        )
        _write_json(run_dir / "manifest.json", manifest)
        return 1
    if not proposal_path.is_file():
        manifest = _finalize_manifest(
            manifest,
            status="failed",
            git_sha=git_sha,
            error=f"Proposal path is not a file: {proposal_path}",
        )
        _write_json(run_dir / "manifest.json", manifest)
        return 1

    _write_text(run_dir / "proposal.md", proposal_path.read_text(encoding="utf8"))
    if watchlist_manifest_path is not None:
        if not watchlist_manifest_path.exists():
            manifest = _finalize_manifest(
                manifest,
                status="failed",
                git_sha=git_sha,
                error=f"Watchlist manifest does not exist: {watchlist_manifest_path}",
            )
            _write_json(run_dir / "manifest.json", manifest)
            return 1
        if not watchlist_manifest_path.is_file():
            manifest = _finalize_manifest(
                manifest,
                status="failed",
                git_sha=git_sha,
                error=f"Watchlist manifest path is not a file: {watchlist_manifest_path}",
            )
            _write_json(run_dir / "manifest.json", manifest)
            return 1
        try:
            watchlist_manifest = _load_watchlist_manifest(watchlist_manifest_path)
        except ResearchCycleError as exc:
            manifest = _finalize_manifest(
                manifest,
                status="failed",
                git_sha=git_sha,
                error=str(exc),
            )
            _write_json(run_dir / "manifest.json", manifest)
            return 1
        if (
            phase_watchlist_manifest is not None
            and not args.allow_phase_override
            and list(watchlist_manifest.get("symbols") or []) != list(phase_watchlist_manifest.get("symbols") or [])
        ):
            manifest = _finalize_manifest(
                manifest,
                status="failed",
                git_sha=git_sha,
                error="Manual watchlist manifest conflicts with the active phase manifest.",
            )
            _write_json(run_dir / "manifest.json", manifest)
            return 1
        manifest["watchlist_manifest"] = {
            "path": watchlist_manifest.get("path"),
            "label": watchlist_manifest.get("label"),
            "symbols": list(watchlist_manifest.get("symbols") or []),
        }
        _write_json(run_dir / "manifest.json", manifest)
        _write_json(run_dir / "watchlist_set.json", watchlist_manifest.get("raw") or {})
    elif watchlist_manifest is not None:
        _write_json(run_dir / "watchlist_set.json", watchlist_manifest.get("raw") or {})

    manifest["experiment_fingerprint"] = build_experiment_fingerprint(
        phase_id=phase_manifest.get("phase_id") if phase_manifest else None,
        mode=mode,
        cohort_id=(cohort or {}).get("id"),
        batch_id=batch_manifest.get("batch_id") if batch_manifest else None,
        playbooks=playbooks,
        truth_lane=truth_lane,
        window_mode=resolved_window_mode,
        watchlist_symbols=list((watchlist_manifest or {}).get("symbols") or []),
        baseline_id=required_baseline_id,
        compare_to=str(compare_to_path) if compare_to_path is not None else None,
        effective_override_diff=effective_override_diff,
        imported_store_metadata=None,
    )
    _write_json(run_dir / "manifest.json", manifest)

    test_report = run_mandatory_regressions(root)
    _write_text(run_dir / "tests.txt", _render_test_report(test_report))
    if not bool(test_report.get("all_passed")):
        manifest = _finalize_manifest(
            manifest,
            status="failed",
            git_sha=git_sha,
            error="Mandatory regression suite failed.",
        )
        _write_json(run_dir / "manifest.json", manifest)
        return 1

    try:
        with _temporary_profile_overrides(effective_override_diff):
            matrix, primary_result = build_matrix(
                playbooks=playbooks,
                truth_lane=truth_lane,
                watchlist_symbols=(watchlist_manifest or {}).get("symbols"),
            )
            _require_quote_coverage(primary_result, args.require_quote_coverage)
        _write_json(run_dir / "matrix.json", matrix)

        manifest["experiment_fingerprint"] = build_experiment_fingerprint(
            phase_id=phase_manifest.get("phase_id") if phase_manifest else None,
            mode=mode,
            cohort_id=(cohort or {}).get("id"),
            batch_id=batch_manifest.get("batch_id") if batch_manifest else None,
            playbooks=playbooks,
            truth_lane=truth_lane,
            window_mode=resolved_window_mode,
            watchlist_symbols=list((watchlist_manifest or {}).get("symbols") or []),
            baseline_id=required_baseline_id,
            compare_to=str(compare_to_path) if compare_to_path is not None else None,
            effective_override_diff=effective_override_diff,
            imported_store_metadata=dict(primary_result.get("truth_store") or {}),
        )
        _write_json(run_dir / "manifest.json", manifest)

        primary_report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "scenario": matrix.get("primary_scenario"),
            "result": primary_result,
        }
        _write_json(run_dir / "primary_report.json", primary_report)

        errors = [
            cell["matrix_key"]
            for cell in matrix.get("cells") or []
            if cell.get("error")
        ]
        if errors:
            raise ResearchCycleError(
                "Backtest matrix failed for one or more scenarios: " + ", ".join(errors)
            )

        bundle = _primary_report_bundle(primary_result)
        _write_json(run_dir / "experiments.json", bundle["experiments"])
        _write_json(run_dir / "stability.json", bundle["stability"])
        _write_json(run_dir / "policy.json", bundle["policy"])
        _write_json(run_dir / "metric_truth.json", bundle["metric_truth"])

        discovery = build_playbook_discovery_report(
            result=primary_result,
            rolling_window_days=ROLLING_WINDOW_DAYS,
            rolling_step_days=ROLLING_WINDOW_STEP_DAYS,
        )
        if discovery.get("error"):
            raise ResearchCycleError(f"Discovery report failed: {discovery['error']}")
        _write_json(run_dir / "discovery.json", discovery)

        baseline_primary_result = (
            _load_primary_report_result(compare_to_path) if compare_to_path is not None else None
        )
        rolling_report = None
        if str(resolved_window_mode) == "rolling_6m":
            rolling_report = build_rolling_window_report(
                current_result=primary_result,
                baseline_result=baseline_primary_result,
                window_days=ROLLING_WINDOW_DAYS,
                step_days=ROLLING_WINDOW_STEP_DAYS,
                catastrophic_pf_floor=ROLLING_CATASTROPHIC_PF_FLOOR,
            )
            _write_json(run_dir / "rolling_windows.json", rolling_report)

        truth_lane_comparison_report = None
        quote_coverage_sensitivity = None
        paired_synthetic_primary = None
        if _uses_imported_truth(truth_lane):
            paired_synthetic_primary = _run_primary_scenario(
                playbook=playbooks[0],
                truth_lane=SYNTHETIC_TRUTH_SOURCE,
                n_picks=DEFAULT_N_PICKS,
                iv_adj=DEFAULT_IV_ADJ,
                watchlist_symbols=(watchlist_manifest or {}).get("symbols"),
                profile_overrides=effective_override_diff,
            )
            _write_json(
                run_dir / "paired_synthetic_primary_report.json",
                {
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "scenario": {
                        "lookback_years": 2,
                        "n_picks": DEFAULT_N_PICKS,
                        "iv_adj": DEFAULT_IV_ADJ,
                        "pricing_lane": "pessimistic",
                        "playbook": playbooks[0],
                        "truth_lane": SYNTHETIC_TRUTH_SOURCE,
                    },
                    "result": paired_synthetic_primary,
                },
            )
            truth_lane_comparison_report = build_truth_lane_comparison(
                synthetic_result=paired_synthetic_primary,
                imported_result=primary_result,
                truth_lane=truth_lane,
            )
            if truth_lane_comparison_report.get("error"):
                raise ResearchCycleError(
                    f"Truth-lane comparison failed: {truth_lane_comparison_report['error']}"
                )
            synthetic_total = int((truth_lane_comparison_report.get("synthetic") or {}).get("total_trades") or 0)
            unsupported = int(truth_lane_comparison_report.get("unsupported_by_import_count") or 0)
            truth_lane_comparison_report["unsupported_by_import_rate_pct"] = (
                round(100.0 * unsupported / synthetic_total, 1) if synthetic_total else None
            )
            quote_coverage_sensitivity = build_quote_coverage_sensitivity(
                result=primary_result,
                require_quote_coverage=args.require_quote_coverage,
            )
            truth_lane_comparison_report["quote_coverage_sensitivity"] = quote_coverage_sensitivity
            _write_json(run_dir / "truth_lane_comparison.json", truth_lane_comparison_report)
            _write_json(run_dir / "quote_coverage_sensitivity.json", quote_coverage_sensitivity)

        falsification = build_falsification_report(
            primary_result=primary_result,
            baseline_primary_result=baseline_primary_result,
            rolling_report=rolling_report,
            truth_lane_comparison_report=truth_lane_comparison_report,
            concentration_summary=build_concentration_summary(primary_result),
            quote_coverage_sensitivity=quote_coverage_sensitivity,
        )
        _write_json(run_dir / "falsification.json", falsification)

        comparison_generated = False
        comparison_error = None
        if compare_to_path is not None:
            comparison = build_comparison(
                current_run_dir=run_dir,
                current_matrix=matrix,
                current_stability=bundle["stability"],
                current_policy=bundle["policy"],
                compare_to_dir=compare_to_path,
                current_manifest=manifest,
                current_git_sha=git_sha,
            )
            _write_json(run_dir / "comparison.json", comparison)
            comparison_generated = True

        synthetic_primary_for_bundle = primary_result if truth_lane == SYNTHETIC_TRUTH_SOURCE else paired_synthetic_primary
        imported_daily_primary = primary_result if truth_lane == IMPORTED_DAILY_TRUTH_SOURCE else None
        imported_intraday_primary = primary_result if truth_lane == IMPORTED_TRUTH_SOURCE else None
        imported_daily_comparison = truth_lane_comparison_report if truth_lane == IMPORTED_DAILY_TRUTH_SOURCE else None
        imported_intraday_comparison = truth_lane_comparison_report if truth_lane == IMPORTED_TRUTH_SOURCE else None

        if mode == "validation":
            if synthetic_primary_for_bundle is None:
                synthetic_primary_for_bundle = _run_primary_scenario(
                    playbook=playbooks[0],
                    truth_lane=SYNTHETIC_TRUTH_SOURCE,
                    n_picks=DEFAULT_N_PICKS,
                    iv_adj=DEFAULT_IV_ADJ,
                    watchlist_symbols=(watchlist_manifest or {}).get("symbols"),
                    profile_overrides=effective_override_diff,
                )
            if imported_daily_primary is None:
                imported_daily_primary = _run_primary_scenario(
                    playbook=playbooks[0],
                    truth_lane=IMPORTED_DAILY_TRUTH_SOURCE,
                    n_picks=DEFAULT_N_PICKS,
                    iv_adj=DEFAULT_IV_ADJ,
                    watchlist_symbols=(watchlist_manifest or {}).get("symbols"),
                    profile_overrides=effective_override_diff,
                )
            if imported_intraday_primary is None:
                imported_intraday_primary = _run_primary_scenario(
                    playbook=playbooks[0],
                    truth_lane=IMPORTED_TRUTH_SOURCE,
                    n_picks=DEFAULT_N_PICKS,
                    iv_adj=DEFAULT_IV_ADJ,
                    watchlist_symbols=(watchlist_manifest or {}).get("symbols"),
                    profile_overrides=effective_override_diff,
                )
            if synthetic_primary_for_bundle is not None and imported_daily_primary is not None:
                imported_daily_comparison = build_truth_lane_comparison(
                    synthetic_result=synthetic_primary_for_bundle,
                    imported_result=imported_daily_primary,
                    truth_lane=IMPORTED_DAILY_TRUTH_SOURCE,
                )
            if synthetic_primary_for_bundle is not None and imported_intraday_primary is not None:
                imported_intraday_comparison = build_truth_lane_comparison(
                    synthetic_result=synthetic_primary_for_bundle,
                    imported_result=imported_intraday_primary,
                    truth_lane=IMPORTED_TRUTH_SOURCE,
                )

        forward_summary = summarize_forward_holdout(
            cohort_id=(cohort or {}).get("id")
        ) if cohort else {"available": False, "cohort_id": None}
        evidence_bundle = build_evidence_bundle(
            cohort_id=(cohort or {}).get("id"),
            phase_id=phase_manifest.get("phase_id") if phase_manifest else None,
            synthetic_result=synthetic_primary_for_bundle,
            imported_daily_result=imported_daily_primary,
            imported_intraday_result=imported_intraday_primary,
            forward_summary=forward_summary,
            imported_daily_comparison=imported_daily_comparison,
            imported_intraday_comparison=imported_intraday_comparison,
        )
        _write_json(run_dir / "evidence_bundle.json", evidence_bundle)

        baseline_compatibility = build_baseline_compatibility(
            compare_to=compare_to_path,
            required_baseline_id=required_baseline_id,
            cohort_id=(cohort or {}).get("id"),
            batch_id=batch_manifest.get("batch_id") if batch_manifest else None,
            comparison_generated=comparison_generated,
            comparison_error=comparison_error,
        )
        manifest["baseline_compatibility"] = baseline_compatibility
        _write_json(run_dir / "manifest.json", manifest)

        decision_packet = build_decision_packet(
            slug=slug,
            evidence_bundle=evidence_bundle,
            primary_result=primary_result,
            stability_report=bundle["stability"],
            policy_report=bundle["policy"],
            falsification_report=falsification,
            baseline_compatibility=baseline_compatibility,
        )
        _write_json(run_dir / "decision_packet.json", decision_packet)
        _write_text(run_dir / "decision.md", render_decision_md(decision_packet, slug=slug))

    except ResearchCycleError as exc:
        manifest = _finalize_manifest(
            manifest,
            status="failed",
            git_sha=git_sha,
            error=str(exc),
        )
        _write_json(run_dir / "manifest.json", manifest)
        return 1

    manifest = _finalize_manifest(manifest, status="completed", git_sha=git_sha)
    _write_json(run_dir / "manifest.json", manifest)
    if phase_manifest_path is not None or root.resolve() == ROOT.resolve():
        write_operator_state(
            root_dir=root,
            phase_manifest_path=phase_manifest_path or DEFAULT_PHASE_MANIFEST,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
