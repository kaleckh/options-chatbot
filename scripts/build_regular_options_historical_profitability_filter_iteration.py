from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_regular_options_historical_simulated_forward_audit import (  # noqa: E402
    DEFAULT_AUDIT_MONTHS,
    DEFAULT_TRAIN_MONTHS,
    _bootstrap_dict,
    _cluster_key,
    _dedupe_rows,
    _dedupe_summary,
    _profit_factor,
    _split_months,
    _trade_usd_value,
)
from scripts.evaluate_regular_options_autoresearch import (  # noqa: E402
    block_bootstrap_confidence_for_values,
    bootstrap_confidence_for_values,
)


REPORT_ID = "regular_options_historical_profitability_filter_iteration"
DEFAULT_BOOTSTRAP_DRAWS = 1_000
DEFAULT_ACCEPTED_RECHECK_DRAWS = 10_000
DEFAULT_SELECTED_CANDIDATES = (
    ROOT
    / "data"
    / "profitability-lab"
    / "regular-options-13-symbol-frozen-candidate-generation-engine"
    / "selected_candidates.jsonl"
)
DEFAULT_AUDIT_REPORT = ROOT / "data" / "profitability-lab" / "regular-options-historical-simulated-forward-audit" / "latest.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-historical-profitability-filter-iteration"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-historical-profitability-filter-iteration.md"
DEFAULT_CONSUMPTION_REGISTRY = ROOT / "data" / "contracts" / "regular-options-audit-window-consumption-registry.json"

MIN_TRAIN_EXACT_TRADES = 100
MIN_AUDIT_EXACT_TRADES = 30
MIN_PF_LB = 1.0

PROHIBITED_ACTIONS = (
    "do_not_change_scanner_policy_from_historical_filter_iteration",
    "do_not_promote_lanes_from_historical_filter_iteration",
    "do_not_enable_live_validation_or_auto_track_from_historical_filter_iteration",
    "do_not_submit_broker_orders_from_historical_filter_iteration",
    "do_not_import_quotes_from_historical_filter_iteration",
    "do_not_mutate_evidence_stores_from_historical_filter_iteration",
    "do_not_lower_proof_bars_from_historical_filter_iteration",
    "do_not_consume_protected_holdout_from_historical_filter_iteration",
    "do_not_treat_historical_rows_as_forward_profitability_proof",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_float(value: Any) -> float | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _safe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    return None


def _load_json(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {}, {"path": _rel(path), "exists": False, "status": "missing"}
    return json.loads(path.read_text(encoding="utf8")), {"path": _rel(path), "exists": True, "status": "loaded"}


def _load_consumption_registry(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    if not path.exists():
        return {"entries": []}, {"path": _rel(path), "exists": False, "status": "missing"}
    payload = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(payload, dict):
        payload = {"entries": []}
    return payload, {"path": _rel(path), "exists": True, "status": "loaded"}


def _consumed_window_overlaps(registry: dict[str, Any], audit_months: Sequence[Any]) -> list[dict[str, Any]]:
    audit_set = {str(month) for month in audit_months}
    overlaps: list[dict[str, Any]] = []
    for entry in _as_list(registry.get("entries")):
        entry = _as_dict(entry)
        months = {str(month) for month in _as_list(entry.get("window_months") or entry.get("audit_months"))}
        if audit_set & months:
            overlaps.append(entry)
    return overlaps


def record_consumption_if_needed(report: dict[str, Any], registry_path: Path = DEFAULT_CONSUMPTION_REGISTRY) -> bool:
    if not bool(report.get("selection_permitted")):
        return False
    if int(report.get("accepted_filter_count") or 0) <= 0:
        return False
    registry, _meta = _load_consumption_registry(registry_path)
    audit_months = _as_list(_as_dict(report.get("split")).get("audit_months"))
    if _consumed_window_overlaps(registry, audit_months):
        return False
    accepted_filter = _as_dict(_as_list(report.get("accepted_filters"))[0] if _as_list(report.get("accepted_filters")) else {})
    entry = {
        "window_months": audit_months,
        "consumed_by": REPORT_ID,
        "consumed_at_utc": report.get("generated_at_utc"),
        "candidate_filter_count": report.get("candidate_filter_count"),
        "accepted_filter_id": accepted_filter.get("filter_id"),
        "selection_permitted": True,
    }
    entries = _as_list(registry.get("entries"))
    registry["entries"] = entries + [entry]
    registry.setdefault("report_id", "regular_options_audit_window_consumption_registry")
    registry.setdefault("schema_version", 1)
    registry["updated_at_utc"] = _utc_now_iso()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, indent=2, sort_keys=True) + "\n", encoding="utf8")
    return True


def _load_jsonl(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        return [], {"path": _rel(path), "exists": False, "status": "missing", "row_count": 0}
    rows: list[dict[str, Any]] = []
    bad = 0
    for raw in path.read_text(encoding="utf8").splitlines():
        if not raw.strip():
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
        else:
            bad += 1
    return rows, {"path": _rel(path), "exists": True, "status": "loaded", "row_count": len(rows), "bad_row_count": bad}


def _month_key(row: dict[str, Any]) -> str:
    return str(row.get("entry_date") or row.get("candidate_generation_date") or row.get("date") or "")[:7]


def _pnl_value(row: dict[str, Any]) -> float | None:
    return _safe_float(row.get("net_pnl_pct", row.get("pnl_pct")))


def _field_value(row: dict[str, Any], field: str) -> Any:
    if "." not in field:
        return row.get(field)
    current: Any = row
    for part in field.split("."):
        current = _as_dict(current).get(part)
    return current


def _quantiles(values: Sequence[float], fractions: Sequence[float]) -> list[float]:
    ordered = sorted({round(float(value), 6) for value in values if math.isfinite(float(value))})
    if not ordered:
        return []
    result: list[float] = []
    for fraction in fractions:
        index = max(0, min(len(ordered) - 1, int(math.floor((len(ordered) - 1) * float(fraction)))))
        result.append(ordered[index])
    return sorted(set(result))


def _accepted_rows(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    accepted = []
    for row in rows:
        if not bool(row.get("exact_priced")):
            continue
        if str(row.get("proof_grade") or "") != "trusted_intraday_opra_nbbo":
            continue
        if str(row.get("fill_basis") or "") != "imported_spread_mark":
            continue
        if _pnl_value(row) is None:
            continue
        accepted.append(dict(row))
    return accepted


def _metrics(rows: Sequence[dict[str, Any]], *, branch_id: str, bootstrap_draws: int) -> dict[str, Any]:
    values = [value for row in rows if (value := _pnl_value(row)) is not None]
    clustered_values = [(_cluster_key(row), value) for row in rows if (value := _pnl_value(row)) is not None]
    usd_values = [value for row in rows if (value := _trade_usd_value(row)) is not None]
    clustered_usd_values = [(_cluster_key(row), value) for row in rows if (value := _trade_usd_value(row)) is not None]
    wins = [value for value in values if value > 0.0]
    losses = [value for value in values if value < 0.0]
    usd_wins = [value for value in usd_values if value > 0.0]
    usd_losses = [value for value in usd_values if value < 0.0]
    gross_loss = abs(sum(losses))
    bootstrap_iid = bootstrap_confidence_for_values(values, branch_id=branch_id, draws=bootstrap_draws)
    bootstrap_cluster = block_bootstrap_confidence_for_values(
        clustered_values,
        branch_id=branch_id,
        draws=bootstrap_draws,
    )
    bootstrap_usd_cluster = block_bootstrap_confidence_for_values(
        clustered_usd_values,
        branch_id=f"{branch_id}:usd",
        draws=bootstrap_draws,
    )
    return {
        "exact_trade_count": len(values),
        "net_pnl_usd_trade_count": len(usd_values),
        "entry_month_count": len({_month_key(row) for row in rows if _month_key(row)}),
        "ticker_week_cluster_count": bootstrap_cluster.get("cluster_count"),
        "avg_pnl_pct": round(sum(values) / len(values), 2) if values else None,
        "profit_factor": round(sum(wins) / gross_loss, 4) if gross_loss > 0 else None,
        "total_net_pnl_usd": round(sum(usd_values), 2) if usd_values else None,
        "usd_profit_factor": round(sum(usd_wins) / abs(sum(usd_losses)), 4) if usd_losses and abs(sum(usd_losses)) > 0 else None,
        "gross_win_usd": round(sum(usd_wins), 2),
        "gross_loss_usd": round(abs(sum(usd_losses)), 2),
        "win_rate_pct": round((len(wins) / len(values)) * 100.0, 2) if values else 0.0,
        "win_trade_count": len(wins),
        "loss_trade_count": len(losses),
        "bootstrap_iid": bootstrap_iid,
        "bootstrap_cluster": bootstrap_cluster,
        "bootstrap_usd_cluster": bootstrap_usd_cluster,
    }


def _filter_passes(row: dict[str, Any], spec: dict[str, Any]) -> bool:
    for condition in _as_list(spec.get("conditions")):
        condition = _as_dict(condition)
        field = str(condition.get("field") or "")
        op = str(condition.get("op") or "")
        expected = condition.get("value")
        value = _field_value(row, field)
        if op == "in":
            if str(value) not in {str(item) for item in _as_list(expected)}:
                return False
        elif op == "eq":
            if value != expected:
                return False
        elif op in {"gte", "lte"}:
            parsed = _safe_float(value)
            threshold = _safe_float(expected)
            if parsed is None or threshold is None:
                return False
            if op == "gte" and parsed < threshold:
                return False
            if op == "lte" and parsed > threshold:
                return False
        else:
            return False
    return True


def _filter_rows(rows: Sequence[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if _filter_passes(row, spec)]


def _ticker_ranks(train_rows: Sequence[dict[str, Any]]) -> list[str]:
    by_ticker: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in train_rows:
        ticker = str(row.get("ticker") or row.get("symbol") or row.get("underlying") or "")
        if ticker:
            by_ticker[ticker].append(row)
    ranked = []
    for ticker, rows in by_ticker.items():
        values = [value for row in rows if (value := _pnl_value(row)) is not None]
        pf = _profit_factor(values) or 0.0
        avg = sum(values) / len(values) if values else -999.0
        ranked.append((pf, avg, len(values), ticker))
    return [ticker for *_unused, ticker in sorted(ranked, reverse=True)]


def _candidate_specs(train_rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = [
        {"filter_id": "baseline_all_exact", "description": "All exact priced selected candidates.", "conditions": []}
    ]
    lanes = sorted({str(row.get("lane_id") or row.get("lane") or "") for row in train_rows if str(row.get("lane_id") or row.get("lane") or "")})
    for lane in lanes:
        specs.append(
            {
                "filter_id": f"lane_{lane}",
                "description": f"Lane-only filter for {lane}.",
                "conditions": [{"field": "lane_id", "op": "eq", "value": lane}],
            }
        )
    ranked_tickers = _ticker_ranks(train_rows)
    top_specs = []
    for n in (5, 6, 7, 8, 9, 10, 11):
        if len(ranked_tickers) >= n:
            top = ranked_tickers[:n]
            top_specs.append(
                {
                    "filter_id": f"train_ranked_top_{n}_tickers",
                    "description": f"Top {n} tickers ranked by train PF then average return.",
                    "conditions": [{"field": "ticker", "op": "in", "value": top}],
                    "train_ranked_tickers": top,
                }
            )
    specs.extend(top_specs)

    numeric_fields = (
        ("dte", "gte", (0.35, 0.5, 0.65)),
        ("debit_pct_of_width", "gte", (0.35, 0.5, 0.65)),
        ("debit_pct_of_width", "lte", (0.35, 0.5, 0.65)),
        ("signal_evidence.prior_20_trading_day_return_pct", "gte", (0.35, 0.5, 0.65, 0.75, 0.85)),
        ("signal_evidence.prior_20_trading_day_return_pct", "lte", (0.15, 0.25, 0.35)),
        ("spread_width", "lte", (0.5, 0.75)),
    )
    numeric_specs: list[dict[str, Any]] = []
    for field, op, fractions in numeric_fields:
        values = [value for row in train_rows if (value := _safe_float(_field_value(row, field))) is not None]
        for threshold in _quantiles(values, fractions):
            clean = field.replace(".", "_")
            numeric_specs.append(
                {
                    "filter_id": f"{clean}_{op}_{threshold:g}",
                    "description": f"{field} {op} {threshold:g}, threshold chosen from train quantiles only.",
                    "conditions": [{"field": field, "op": op, "value": threshold}],
                }
            )
    specs.extend(numeric_specs)

    for top in top_specs:
        for numeric in numeric_specs:
            specs.append(
                {
                    "filter_id": f"{top['filter_id']}__{numeric['filter_id']}",
                    "description": f"{top['description']} plus {numeric['description']}",
                    "conditions": _as_list(top.get("conditions")) + _as_list(numeric.get("conditions")),
                    "train_ranked_tickers": top.get("train_ranked_tickers"),
                }
            )

    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for spec in specs:
        key = json.dumps(spec.get("conditions"), sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(spec)
    return unique


def _score_filter(
    spec: dict[str, Any],
    *,
    train_rows: Sequence[dict[str, Any]],
    audit_rows: Sequence[dict[str, Any]],
    bootstrap_draws: int,
) -> dict[str, Any]:
    train_filtered = _filter_rows(train_rows, spec)
    audit_filtered = _filter_rows(audit_rows, spec)
    filter_id = str(spec.get("filter_id"))
    train_metrics = _metrics(train_filtered, branch_id=f"{REPORT_ID}:{filter_id}:train", bootstrap_draws=bootstrap_draws)
    audit_metrics = _metrics(audit_filtered, branch_id=f"{REPORT_ID}:{filter_id}:audit", bootstrap_draws=bootstrap_draws)
    train_lb = _safe_float(_bootstrap_dict(train_metrics, "bootstrap_cluster").get("pf_lb_5pct"))
    audit_lb = _safe_float(_bootstrap_dict(audit_metrics, "bootstrap_cluster").get("pf_lb_5pct"))
    train_usd_lb = _safe_float(_bootstrap_dict(train_metrics, "bootstrap_usd_cluster").get("pf_lb_5pct"))
    audit_usd_lb = _safe_float(_bootstrap_dict(audit_metrics, "bootstrap_usd_cluster").get("pf_lb_5pct"))
    blockers: list[str] = []
    if int(train_metrics.get("exact_trade_count") or 0) < MIN_TRAIN_EXACT_TRADES:
        blockers.append(f"train_exact_trades_below_{MIN_TRAIN_EXACT_TRADES}")
    if int(audit_metrics.get("exact_trade_count") or 0) < MIN_AUDIT_EXACT_TRADES:
        blockers.append(f"audit_exact_trades_below_{MIN_AUDIT_EXACT_TRADES}")
    if int(train_metrics.get("net_pnl_usd_trade_count") or 0) != int(train_metrics.get("exact_trade_count") or 0):
        blockers.append("train_net_pnl_usd_missing")
    if int(audit_metrics.get("net_pnl_usd_trade_count") or 0) != int(audit_metrics.get("exact_trade_count") or 0):
        blockers.append("audit_net_pnl_usd_missing")
    if train_lb is None or train_lb <= MIN_PF_LB:
        blockers.append("train_bootstrap_pf_lb_not_above_1")
    if audit_lb is None or audit_lb <= MIN_PF_LB:
        blockers.append("audit_bootstrap_pf_lb_not_above_1")
    if train_usd_lb is None or train_usd_lb <= MIN_PF_LB:
        blockers.append("train_usd_bootstrap_pf_lb_not_above_1")
    if audit_usd_lb is None or audit_usd_lb <= MIN_PF_LB:
        blockers.append("audit_usd_bootstrap_pf_lb_not_above_1")
    if (_safe_float(train_metrics.get("avg_pnl_pct")) or 0.0) <= 0.0:
        blockers.append("train_avg_pnl_not_positive")
    if (_safe_float(audit_metrics.get("avg_pnl_pct")) or 0.0) <= 0.0:
        blockers.append("audit_avg_pnl_not_positive")
    if (_safe_float(train_metrics.get("total_net_pnl_usd")) or 0.0) <= 0.0:
        blockers.append("train_total_net_pnl_usd_not_positive")
    if (_safe_float(audit_metrics.get("total_net_pnl_usd")) or 0.0) <= 0.0:
        blockers.append("audit_total_net_pnl_usd_not_positive")
    return {
        "filter_id": filter_id,
        "description": spec.get("description"),
        "conditions": _as_list(spec.get("conditions")),
        "train_ranked_tickers": spec.get("train_ranked_tickers"),
        "train": train_metrics,
        "simulated_forward_audit": audit_metrics,
        "accepted_by_historical_iteration_gate": not blockers,
        "blockers": blockers,
    }


def _sort_key(row: dict[str, Any], window: str) -> tuple[float, float, float, int]:
    metrics = _as_dict(row.get(window))
    bootstrap = _bootstrap_dict(metrics, "bootstrap_cluster")
    return (
        _safe_float(bootstrap.get("pf_lb_5pct")) or -999.0,
        _safe_float(metrics.get("profit_factor")) or -999.0,
        _safe_float(metrics.get("avg_pnl_pct")) or -999.0,
        int(metrics.get("exact_trade_count") or 0),
    )


def build_report(
    *,
    selected_candidates_path: Path = DEFAULT_SELECTED_CANDIDATES,
    audit_report_path: Path = DEFAULT_AUDIT_REPORT,
    consumption_registry_path: Path = DEFAULT_CONSUMPTION_REGISTRY,
    train_months: int = DEFAULT_TRAIN_MONTHS,
    audit_months: int = DEFAULT_AUDIT_MONTHS,
    bootstrap_draws: int = DEFAULT_BOOTSTRAP_DRAWS,
    accepted_recheck_draws: int = DEFAULT_ACCEPTED_RECHECK_DRAWS,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    raw_rows, selected_meta = _load_jsonl(selected_candidates_path)
    audit_report, audit_meta = _load_json(audit_report_path)
    consumption_registry, consumption_registry_meta = _load_consumption_registry(consumption_registry_path)
    rows_before_dedupe = _accepted_rows(raw_rows)
    rows = _dedupe_rows(rows_before_dedupe)
    months = sorted({_month_key(row) for row in rows if _month_key(row)})
    split = _split_months(months, train_months=int(train_months), audit_months=int(audit_months))
    train_set = set(_as_list(split.get("train_months")))
    audit_set = set(_as_list(split.get("audit_months")))
    consumed_overlaps = _consumed_window_overlaps(consumption_registry, _as_list(split.get("audit_months")))
    selection_permitted = not consumed_overlaps
    train_rows = [row for row in rows if _month_key(row) in train_set]
    audit_rows = [row for row in rows if _month_key(row) in audit_set]
    specs = _candidate_specs(train_rows)
    scored = [
        _score_filter(spec, train_rows=train_rows, audit_rows=audit_rows, bootstrap_draws=bootstrap_draws)
        for spec in specs
    ]
    preliminary_accepted = [row for row in scored if row.get("accepted_by_historical_iteration_gate")]
    accepted_rechecked = [
        {
            **_score_filter(
                row,
                train_rows=train_rows,
                audit_rows=audit_rows,
                bootstrap_draws=max(int(accepted_recheck_draws), int(bootstrap_draws)),
            ),
            "preliminary_bootstrap_draws": int(bootstrap_draws),
            "accepted_recheck_bootstrap_draws": max(int(accepted_recheck_draws), int(bootstrap_draws)),
        }
        for row in preliminary_accepted
    ]
    accepted = [row for row in accepted_rechecked if row.get("accepted_by_historical_iteration_gate")]
    accepted_sorted_candidates = sorted(accepted, key=lambda row: (_sort_key(row, "simulated_forward_audit"), _sort_key(row, "train")), reverse=True)
    accepted_sorted = accepted_sorted_candidates if selection_permitted else []
    top_train = sorted(scored, key=lambda row: (_sort_key(row, "train"), _sort_key(row, "simulated_forward_audit")), reverse=True)[:12]
    top_audit = sorted(scored, key=lambda row: (_sort_key(row, "simulated_forward_audit"), _sort_key(row, "train")), reverse=True)[:12]
    baseline = next((row for row in scored if row.get("filter_id") == "baseline_all_exact"), None)

    blockers: list[str] = []
    if selected_meta.get("status") != "loaded":
        blockers.append("selected_candidates_jsonl_not_loaded")
    if audit_meta.get("status") != "loaded":
        blockers.append("historical_simulated_forward_audit_not_loaded")
    if not split.get("sufficient_months_for_requested_split"):
        blockers.append("insufficient_months_for_requested_split")
    if not selection_permitted:
        blockers.append("audit_window_already_consumed_for_selection")
    if not accepted_sorted:
        blockers.append("no_preregistered_train_selected_filter_passes_train_and_audit")
    status = (
        "blocked_audit_window_already_consumed_for_selection"
        if not selection_permitted
        else "historical_profitability_filter_iteration_candidate_found"
        if not blockers
        else "blocked_historical_profitability_filter_iteration"
    )
    by_month = Counter(_month_key(row) for row in rows)
    by_ticker = Counter(str(row.get("ticker") or row.get("symbol") or row.get("underlying") or "") for row in rows)
    return {
        "report_id": REPORT_ID,
        "status": status,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        "schema_version": 1,
        "read_only": True,
        "research_only": True,
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
        "scanner_policy_changed": False,
        "production_scanner_changed": False,
        "live_validation_enabled": False,
        "auto_track_enabled": False,
        "broker_order_allowed": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "inputs": {
            "selected_candidates_jsonl": selected_meta,
            "historical_simulated_forward_audit": audit_meta,
            "audit_window_consumption_registry": consumption_registry_meta,
        },
        "requested_split": {
            "train_months": int(train_months),
            "audit_months": int(audit_months),
            "bootstrap_draws": int(bootstrap_draws),
            "accepted_recheck_bootstrap_draws": max(int(accepted_recheck_draws), int(bootstrap_draws)),
            "split_rule": "candidate filters and thresholds are generated from train rows only; latest audit rows are scored after selection",
        },
        "split": split,
        "selection_permitted": selection_permitted,
        "consumed_audit_window_overlaps": consumed_overlaps,
        "source_summary": {
            "raw_selected_candidate_rows": len(raw_rows),
            "accepted_exact_candidate_rows": len(rows),
            **_dedupe_summary(len(rows_before_dedupe), len(rows)),
            "available_months": months,
            "by_month": dict(sorted(by_month.items())),
            "by_ticker": dict(sorted(by_ticker.items())),
            "audit_artifact_status": audit_report.get("status"),
            "audit_artifact_blockers": _as_list(audit_report.get("blockers")),
        },
        "gate": {
            "min_train_exact_trades": MIN_TRAIN_EXACT_TRADES,
            "min_audit_exact_trades": MIN_AUDIT_EXACT_TRADES,
            "min_train_pf_lb_exclusive": MIN_PF_LB,
            "min_audit_pf_lb_exclusive": MIN_PF_LB,
            "train_avg_pnl_must_be_positive": True,
            "audit_avg_pnl_must_be_positive": True,
        },
        "selection_bias_disclosure": _selection_bias_disclosure(
            candidate_filter_count=len(scored),
            top_train=top_train,
        ),
        "baseline": baseline,
        "candidate_filter_count": len(scored),
        "preliminary_accepted_filter_count": len(preliminary_accepted),
        "selection_permitted_accepted_filter_count": len(accepted_sorted_candidates),
        "accepted_filter_count": len(accepted_sorted),
        "accepted_filters": accepted_sorted[:20],
        "top_train_filters": top_train,
        "top_audit_filters": top_audit,
        "blockers": sorted(dict.fromkeys(blockers)),
        "proof_policy": {
            "readback_is": "read-only train-selected historical filter iteration over deterministic local PIT selected candidates",
            "readback_is_not": "scanner policy, accepted profitability, fresh forward proof, live validation, broker permission, quote import, proof-bar change, protected-holdout use, or promotion",
            "post_hoc_audit_warning": "filters that look good only when ranked by audit metrics are diagnostic and are not accepted unless they also clear train gates",
        },
        "prohibited_actions": list(PROHIBITED_ACTIONS),
    }


def _conditions_text(conditions: Sequence[Any]) -> str:
    rendered = []
    for condition in conditions:
        condition = _as_dict(condition)
        value = condition.get("value")
        if isinstance(value, list):
            value = ",".join(str(item) for item in value)
        rendered.append(f"{condition.get('field')} {condition.get('op')} {value}")
    return "; ".join(rendered) if rendered else "none"


def _selection_bias_disclosure(*, candidate_filter_count: int, top_train: Sequence[dict[str, Any]]) -> dict[str, Any]:
    train_best_failed_audit = any(
        any(str(blocker).startswith("audit_") for blocker in _as_list(_as_dict(row).get("blockers")))
        for row in top_train[:10]
    )
    return {
        "candidate_filter_count_searched": int(candidate_filter_count),
        "acceptance_gate_includes_audit_window_success": True,
        "ranking_basis": "accepted filters are sorted audit-first after train-and-audit gates; top-audit diagnostics are post-hoc",
        "audit_metrics_interpretation": "accepted-filter audit metrics are selection-conditioned upward-biased maxima, not unbiased out-of-sample estimates",
        "empirical_inversion_note": (
            "At least one train-best diagnostic filter failed an audit-window gate."
            if train_best_failed_audit
            else "No train-best inversion was observed in the latest diagnostic top-train slice."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    split = _as_dict(report.get("split"))
    source = _as_dict(report.get("source_summary"))
    baseline = _as_dict(report.get("baseline"))
    disclosure = _as_dict(report.get("selection_bias_disclosure"))
    lines = [
        "# Regular Options Historical Profitability Filter Iteration",
        "",
        "This generated artifact evaluates deterministic pre-entry filter families against the frozen 13-symbol historical selected candidates. Filters and thresholds are generated from train rows only, then scored on the latest simulated-forward audit months. It is read-only and cannot change scanner policy.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Accepted filters: `{report.get('accepted_filter_count')}` / `{report.get('candidate_filter_count')}`.",
        f"- Selection permitted: `{report.get('selection_permitted')}`.",
        f"- Accepted exact rows: `{source.get('accepted_exact_candidate_rows')}`.",
        f"- Dedupe: `{source.get('accepted_exact_candidate_rows_before_dedupe')}` rows before dedupe, `{source.get('deduped_row_count')}` rows after dedupe, `{source.get('duplicate_rows_removed')}` duplicates removed.",
        f"- Train months: `{', '.join(str(item) for item in _as_list(split.get('train_months')))}`.",
        f"- Audit months: `{', '.join(str(item) for item in _as_list(split.get('audit_months')))}`.",
        f"- Source audit status: `{source.get('audit_artifact_status')}`.",
        f"- Accepted profitability: `{report.get('accepted_profitability')}`.",
        f"- Selection bias: `{disclosure.get('audit_metrics_interpretation')}`.",
        "",
        "## Selection Bias Disclosure",
        "",
        f"- Candidate filters searched: `{disclosure.get('candidate_filter_count_searched')}`.",
        f"- Acceptance gate includes audit-window success: `{disclosure.get('acceptance_gate_includes_audit_window_success')}`.",
        f"- Ranking basis: {disclosure.get('ranking_basis')}.",
        f"- Empirical inversion note: {disclosure.get('empirical_inversion_note')}",
        "",
        "## Baseline",
        "",
        "| Window | Rows | Clusters | Avg % | PF | IID PF LB 5% | Cluster PF LB 5% | Net USD | USD PF | USD Cluster PF LB 5% |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, key in (("Train", "train"), ("Simulated forward audit", "simulated_forward_audit")):
        metrics = _as_dict(baseline.get(key))
        bootstrap_iid = _bootstrap_dict(metrics, "bootstrap_iid")
        bootstrap = _bootstrap_dict(metrics, "bootstrap_cluster")
        lines.append(
            f"| {label} | {metrics.get('exact_trade_count')} | {metrics.get('ticker_week_cluster_count')} | {metrics.get('avg_pnl_pct')} | {metrics.get('profit_factor')} | {bootstrap_iid.get('pf_lb_5pct')} | {bootstrap.get('pf_lb_5pct')} | {metrics.get('total_net_pnl_usd')} | {metrics.get('usd_profit_factor')} | {_bootstrap_dict(metrics, 'bootstrap_usd_cluster').get('pf_lb_5pct')} |"
        )
    lines.extend(
        [
            "",
            "## Accepted Filters",
            "",
            "| Filter | Conditions | Train rows/cluster PF LB/USD LB | Audit rows/cluster PF LB/USD LB |",
            "|---|---|---:|---:|",
        ]
    )
    accepted = _as_list(report.get("accepted_filters"))
    if accepted:
        for row in accepted[:10]:
            row = _as_dict(row)
            train = _as_dict(row.get("train"))
            audit = _as_dict(row.get("simulated_forward_audit"))
            lines.append(
                "| "
                + " | ".join(
                    [
                        f"`{row.get('filter_id')}`",
                        _conditions_text(_as_list(row.get("conditions"))),
                        f"{train.get('exact_trade_count')} / {_bootstrap_dict(train, 'bootstrap_cluster').get('pf_lb_5pct')} / {_bootstrap_dict(train, 'bootstrap_usd_cluster').get('pf_lb_5pct')}",
                        f"{audit.get('exact_trade_count')} / {_bootstrap_dict(audit, 'bootstrap_cluster').get('pf_lb_5pct')} / {_bootstrap_dict(audit, 'bootstrap_usd_cluster').get('pf_lb_5pct')}",
                    ]
                )
                + " |"
            )
    else:
        lines.append("| None | none | 0 / n/a | 0 / n/a |")
    lines.extend(
        [
            "",
            "## Top Audit Diagnostics",
            "",
            "| Filter | Conditions | Train IID/Cluster/USD PF LB | Audit IID/Cluster/USD PF LB | Blockers |",
            "|---|---|---:|---:|---|",
        ]
    )
    for row in _as_list(report.get("top_audit_filters"))[:10]:
        row = _as_dict(row)
        train = _as_dict(row.get("train"))
        audit = _as_dict(row.get("simulated_forward_audit"))
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row.get('filter_id')}`",
                    _conditions_text(_as_list(row.get("conditions"))),
                    f"{_bootstrap_dict(train, 'bootstrap_iid').get('pf_lb_5pct')} / {_bootstrap_dict(train, 'bootstrap_cluster').get('pf_lb_5pct')} / {_bootstrap_dict(train, 'bootstrap_usd_cluster').get('pf_lb_5pct')}",
                    f"{_bootstrap_dict(audit, 'bootstrap_iid').get('pf_lb_5pct')} / {_bootstrap_dict(audit, 'bootstrap_cluster').get('pf_lb_5pct')} / {_bootstrap_dict(audit, 'bootstrap_usd_cluster').get('pf_lb_5pct')}",
                    ", ".join(str(item) for item in _as_list(row.get("blockers"))) or "none",
                ]
            )
            + " |"
        )
    blockers = _as_list(report.get("blockers"))
    if blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- `{blocker}`" for blocker in blockers)
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This report can nominate or reject historical pre-entry filters for the next research pass. It does not change scanners, authorize paper/live trading, import quotes, mutate evidence stores, lower proof bars, promote lanes, or make historical rows fresh forward proof.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"{REPORT_ID}_{stamp}.json"
    md_path = output_dir / f"{REPORT_ID}_{stamp}.md"
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    artifacts = {
        "json": _rel(json_path),
        "latest_json": _rel(latest_json),
        "markdown": _rel(md_path),
        "latest_markdown": _rel(latest_md),
        "docs_report": _rel(docs_report),
    }
    report["artifacts"] = artifacts
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(report) + "\n"
    json_path.write_text(payload, encoding="utf8")
    latest_json.write_text(payload, encoding="utf8")
    md_path.write_text(markdown, encoding="utf8")
    latest_md.write_text(markdown, encoding="utf8")
    docs_report.write_text(markdown, encoding="utf8")
    return artifacts


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the read-only historical profitability filter iteration report.")
    parser.add_argument("--selected-candidates", type=Path, default=DEFAULT_SELECTED_CANDIDATES)
    parser.add_argument("--audit-report", type=Path, default=DEFAULT_AUDIT_REPORT)
    parser.add_argument("--consumption-registry", type=Path, default=DEFAULT_CONSUMPTION_REGISTRY)
    parser.add_argument("--train-months", type=int, default=DEFAULT_TRAIN_MONTHS)
    parser.add_argument("--audit-months", type=int, default=DEFAULT_AUDIT_MONTHS)
    parser.add_argument("--bootstrap-draws", type=int, default=DEFAULT_BOOTSTRAP_DRAWS)
    parser.add_argument("--accepted-recheck-draws", type=int, default=DEFAULT_ACCEPTED_RECHECK_DRAWS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--record-consumption", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    report = build_report(
        selected_candidates_path=args.selected_candidates,
        audit_report_path=args.audit_report,
        consumption_registry_path=args.consumption_registry,
        train_months=max(int(args.train_months), 1),
        audit_months=max(int(args.audit_months), 1),
        bootstrap_draws=max(int(args.bootstrap_draws), 1),
        accepted_recheck_draws=max(int(args.accepted_recheck_draws), 1),
    )
    if args.record_consumption:
        report["consumption_registry_recorded"] = record_consumption_if_needed(report, args.consumption_registry)
    if not args.no_write:
        write_outputs(report, output_dir=args.output_dir, docs_report=args.docs_report)
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
