from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPORT_ID = "regular_options_dispersion_proxy_hybrid_candidate_rows"
CONCEPT_ID = "index_constituent_dispersion_proxy_defined_risk_hybrid_v1"

DEFAULT_READINESS = ROOT / "data" / "profitability-lab" / "regular-options-dispersion-proxy-hybrid-replay-readiness" / "latest.json"
DEFAULT_PROXY = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-dispersion-concentration-proxy" / "latest.json"
DEFAULT_SOURCE_ROWS = ROOT / "data" / "profitability-lab" / "regular-options-point-in-time-dispersion-concentration-proxy" / "source_rows.jsonl"
DEFAULT_OPTIONS_DB = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "profitability-lab" / "regular-options-dispersion-proxy-hybrid-bounded-replay"
DEFAULT_CANDIDATE_ROWS = DEFAULT_OUTPUT_DIR / "candidate_rows.jsonl"
DEFAULT_DOCS_REPORT = ROOT / "docs" / "regular-options-dispersion-proxy-hybrid-candidate-rows.md"

INDEX_UNDERLYINGS = {"SPY", "QQQ"}
CONSTITUENT_UNDERLYINGS = {"AAPL", "GOOGL", "LLY", "JNJ", "XOM", "CVX", "COP", "NEM"}
TRUSTED_EXECUTABLE_QUOTE_SOURCES = {
    "opra_nbbo",
    "trusted_opra_nbbo",
    "trusted_intraday_opra_nbbo",
    "thetadata_opra_nbbo_1m",
    "alpaca_opra",
}

ENTRY_MINUTE_ET = 600
EXIT_MINUTE_ET = 900
EXIT_TRADING_DAYS_AFTER_ENTRY = 5
CONTRACT_MULTIPLIER = 100.0
PER_CONTRACT_FEE_USD = 0.65
ROUND_TRIP_CONTRACT_SIDES = 8

READ_ONLY_FLAGS = {
    "read_only": True,
    "research_only": True,
    "accepted_profitability": False,
    "historical_rows_are_forward_proof": False,
    "live_validation_enabled": False,
    "auto_track_enabled": False,
    "broker_order_allowed": False,
    "quotes_imported": False,
    "evidence_stores_mutated": False,
    "protected_holdout_consumed": False,
    "production_scanner_changed": False,
    "scanner_policy_changed": False,
    "strategy_logic_changed": False,
    "stops_changed": False,
    "sizing_changed": False,
    "proof_bars_changed": False,
    "promotion_ready": False,
}

FORBIDDEN_ACTIONS = (
    "do_not_import_quotes",
    "do_not_mutate_options_history_db",
    "do_not_append_forward_cohort_rows",
    "do_not_enable_live_validation",
    "do_not_enable_auto_track",
    "do_not_submit_broker_orders",
    "do_not_change_scanner_policy",
    "do_not_change_strategy_logic",
    "do_not_change_stops",
    "do_not_change_sizing",
    "do_not_lower_proof_bars",
    "do_not_consume_protected_holdout",
    "do_not_promote_any_lane",
    "do_not_count_historical_rows_as_forward_proof",
    "do_not_use_midpoint_last_eod_manual_synthetic_or_lookahead_prices",
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
    try:
        if value in (None, "") or isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_json(path: Path, *, required: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = {"path": _rel(path), "required": required, "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return {}, meta
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        meta["status"] = "malformed"
        meta["error"] = f"JSONDecodeError:{exc.lineno}:{exc.colno}"
        return {}, meta
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return {}, meta
    if not isinstance(payload, dict):
        meta["status"] = "invalid"
        meta["error"] = "expected_object"
        return {}, meta
    meta["status"] = "loaded"
    meta["generated_at_utc"] = payload.get("generated_at_utc")
    meta["report_id"] = payload.get("report_id")
    meta["status_value"] = payload.get("status")
    return payload, meta


def _load_jsonl(path: Path, *, required: bool) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    meta = {
        "path": _rel(path),
        "required": required,
        "exists": path.exists(),
        "status": "missing",
        "row_count": 0,
        "malformed_rows": 0,
        "error": None,
    }
    if not path.exists():
        return [], meta
    rows: list[dict[str, Any]] = []
    malformed = 0
    try:
        lines = path.read_text(encoding="utf8").splitlines()
    except OSError as exc:
        meta["status"] = "unreadable"
        meta["error"] = type(exc).__name__
        return [], meta
    for raw in lines:
        if not raw.strip():
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            malformed += 1
    meta["status"] = "loaded"
    meta["row_count"] = len(rows)
    meta["malformed_rows"] = malformed
    return rows, meta


def _connect_options_db(path: Path) -> tuple[sqlite3.Connection | None, dict[str, Any]]:
    meta = {"path": _rel(path), "exists": path.exists(), "status": "missing", "error": None}
    if not path.exists():
        return None, meta
    try:
        conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        meta["status"] = "loaded_read_only"
        return conn, meta
    except sqlite3.Error as exc:
        meta["status"] = "unreadable"
        meta["error"] = str(exc)
        return None, meta


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _build_source_rows_by_date(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        proxy_date = str(row.get("proxy_date_et") or "")
        if proxy_date:
            grouped[proxy_date].append(row)
    return grouped


def _rank_constituent(proxy_row: dict[str, Any], source_rows: list[dict[str, Any]]) -> tuple[str | None, dict[str, Any]]:
    index_return = None
    index_carrier = str(proxy_row.get("index_carrier") or "SPY")
    candidates: list[tuple[float, str, dict[str, Any]]] = []
    for row in source_rows:
        symbol = str(row.get("symbol") or "")
        ret = _safe_float(row.get("return_pct"))
        if symbol == index_carrier:
            index_return = ret
        if symbol not in CONSTITUENT_UNDERLYINGS or ret is None:
            continue
        candidates.append((ret, symbol, row))
    if not candidates:
        return None, {"status": "missing_constituent_source_rows", "index_return_pct": index_return}
    candidates.sort(key=lambda item: (-item[0], item[1]))
    ret, symbol, row = candidates[0]
    return symbol, {
        "status": "selected_highest_prior_20d_return_constituent",
        "constituent_return_pct": ret,
        "index_return_pct": index_return,
        "source_row_hash": row.get("upstream_source_row_hash"),
        "source_timestamp_utc": row.get("source_timestamp_utc"),
        "source_family": row.get("source_family"),
    }


def _quote_chain(
    conn: sqlite3.Connection | None,
    *,
    underlying: str,
    quote_date: str,
    max_minute: int,
    option_type: str,
) -> list[dict[str, Any]]:
    if conn is None:
        return []
    source_placeholders = ", ".join("?" for _ in TRUSTED_EXECUTABLE_QUOTE_SOURCES)
    query = f"""
        select q.contract_symbol, q.expiry, q.option_type, q.strike, q.bid, q.ask,
               q.underlying_price, q.volume, q.open_interest, q.quote_minute_et,
               q.source_batch_id, b.source_label
        from option_quote_snapshots q
        join import_batches b on b.id = q.source_batch_id
        where q.snapshot_kind = 'intraday'
          and q.underlying = ?
          and q.quote_date_et = ?
          and q.quote_minute_et <= ?
          and lower(q.option_type) = ?
          and q.bid is not null
          and q.ask is not null
          and q.bid > 0
          and q.ask > 0
          and b.data_trust = 'trusted'
          and lower(b.source_label) in ({source_placeholders})
        order by q.expiry, q.strike, q.quote_minute_et desc
    """
    params: list[Any] = [underlying, quote_date, max_minute, option_type, *sorted(TRUSTED_EXECUTABLE_QUOTE_SOURCES)]
    try:
        rows = conn.execute(query, params).fetchall()
    except sqlite3.Error:
        return []
    latest: dict[tuple[str, str, float], dict[str, Any]] = {}
    for row in rows:
        key = (str(row["contract_symbol"]), str(row["expiry"]), float(row["strike"]))
        if key in latest:
            continue
        latest[key] = {
            "contract_symbol": str(row["contract_symbol"]),
            "expiry": str(row["expiry"]),
            "option_type": str(row["option_type"]).lower(),
            "strike": float(row["strike"]),
            "bid": float(row["bid"]),
            "ask": float(row["ask"]),
            "underlying_price": _safe_float(row["underlying_price"]),
            "volume": int(row["volume"]) if row["volume"] is not None else None,
            "open_interest": int(row["open_interest"]) if row["open_interest"] is not None else None,
            "quote_minute_et": int(row["quote_minute_et"]),
            "source_batch_id": int(row["source_batch_id"]),
            "source_label": str(row["source_label"]),
        }
    return list(latest.values())


def _dte(entry_date: str, expiry: str) -> int | None:
    start = _parse_date(entry_date)
    end = _parse_date(expiry)
    if start is None or end is None:
        return None
    return (end - start).days


def _eligible_expiry(chain: list[dict[str, Any]], *, entry_date: str) -> str | None:
    expiries = sorted({str(row["expiry"]) for row in chain})
    eligible = [expiry for expiry in expiries if (dte := _dte(entry_date, expiry)) is not None and 21 <= dte <= 45]
    if eligible:
        return eligible[0]
    fallback = [expiry for expiry in expiries if (dte := _dte(entry_date, expiry)) is not None and dte > 7]
    return fallback[0] if fallback else None


def _select_call_debit_spread(chain: list[dict[str, Any]], *, entry_date: str) -> tuple[dict[str, Any] | None, str | None]:
    expiry = _eligible_expiry(chain, entry_date=entry_date)
    if expiry is None:
        return None, "missing_eligible_index_expiry"
    rows = sorted([row for row in chain if row["expiry"] == expiry], key=lambda row: row["strike"])
    if len(rows) < 2:
        return None, "missing_index_call_spread_strikes"
    underlying = next((row["underlying_price"] for row in rows if row.get("underlying_price")), None)
    if underlying is None:
        return None, "missing_index_underlying_price"
    long_candidates = [row for row in rows if row["strike"] >= underlying * 0.98]
    if not long_candidates:
        return None, "missing_index_long_call_near_underlying"
    long_leg = min(long_candidates, key=lambda row: (abs(row["strike"] - underlying), row["strike"]))
    short_candidates = [row for row in rows if row["strike"] > long_leg["strike"]]
    if not short_candidates:
        return None, "missing_index_short_call_above_long"
    short_leg = min(short_candidates, key=lambda row: row["strike"])
    return {
        "long": long_leg,
        "short": short_leg,
        "spread_width": round(short_leg["strike"] - long_leg["strike"], 4),
        "entry_debit": round(long_leg["ask"] - short_leg["bid"], 4),
    }, None


def _select_call_credit_spread(chain: list[dict[str, Any]], *, entry_date: str) -> tuple[dict[str, Any] | None, str | None]:
    expiry = _eligible_expiry(chain, entry_date=entry_date)
    if expiry is None:
        return None, "missing_constituent_eligible_expiry"
    rows = sorted([row for row in chain if row["expiry"] == expiry], key=lambda row: row["strike"])
    if len(rows) < 2:
        return None, "missing_constituent_call_spread_strikes"
    underlying = next((row["underlying_price"] for row in rows if row.get("underlying_price")), None)
    if underlying is None:
        return None, "missing_constituent_underlying_price"
    short_candidates = [row for row in rows if row["strike"] >= underlying * 1.01]
    if not short_candidates:
        return None, "missing_constituent_short_call_above_underlying"
    short_leg = min(short_candidates, key=lambda row: (abs(row["strike"] - underlying * 1.03), row["strike"]))
    long_candidates = [row for row in rows if row["strike"] > short_leg["strike"]]
    if not long_candidates:
        return None, "missing_constituent_long_call_above_short"
    long_leg = min(long_candidates, key=lambda row: row["strike"])
    return {
        "short": short_leg,
        "long": long_leg,
        "spread_width": round(long_leg["strike"] - short_leg["strike"], 4),
        "entry_credit": round(short_leg["bid"] - long_leg["ask"], 4),
    }, None


def _max_loss_usd(index_spread: dict[str, Any], credit_spread: dict[str, Any]) -> float:
    debit = max(float(index_spread["entry_debit"]), 0.0)
    credit = float(credit_spread["entry_credit"])
    debit_width = float(index_spread["spread_width"])
    credit_width = float(credit_spread["spread_width"])
    debit_risk = debit
    credit_risk = max(credit_width - credit, 0.0)
    return round((debit_risk + credit_risk) * CONTRACT_MULTIPLIER + ROUND_TRIP_CONTRACT_SIDES * PER_CONTRACT_FEE_USD, 2)


def _candidate_row(
    *,
    proxy_row: dict[str, Any],
    source_rows: list[dict[str, Any]],
    entry_date: str | None,
    exit_date: str | None,
    conn: sqlite3.Connection | None,
    chain_cache: dict[tuple[str, str, int, str], list[dict[str, Any]]],
) -> dict[str, Any]:
    proxy_date = str(proxy_row.get("proxy_date_et") or "")
    index_underlying = str(proxy_row.get("index_carrier") or "")
    pair_id = f"{CONCEPT_ID}:{proxy_date}:{index_underlying}"
    base = {
        "report_id": REPORT_ID,
        "concept_id": CONCEPT_ID,
        "pair_id": pair_id,
        "proxy_date_et": proxy_date,
        "entry_date_et": entry_date,
        "entry_minute_et": ENTRY_MINUTE_ET if entry_date else None,
        "exit_date_et": exit_date,
        "exit_minute_et": EXIT_MINUTE_ET if exit_date else None,
        "index_underlying": index_underlying,
        "variant_id": "long_index_call_debit_short_constituent_call_credit_concentrated_leadership_v1",
        "candidate_selected": False,
        "denominator_status": "no_candidate",
        "blockers": [],
        "proof_qualified": False,
        "historical_rows_are_forward_proof": False,
        "accepted_profitability": False,
        "read_only": True,
        "research_only": True,
        "undefined_or_uncapped_pair_risk_allowed": False,
        "protected_holdout_overlap": False,
    }
    blockers: list[str] = []
    if _as_list(proxy_row.get("blockers")):
        blockers.extend(str(item) for item in _as_list(proxy_row.get("blockers")))
    if index_underlying not in INDEX_UNDERLYINGS:
        blockers.append("rejected_pair_universe_mismatch:index_carrier_not_allowed")
    if proxy_row.get("broadening_or_narrowing_state") != "concentrated_leadership":
        blockers.append("rejected_not_concentrated_leadership")
    if not entry_date:
        blockers.append("missing_entry_date_after_proxy")
    if not exit_date:
        blockers.append("missing_policy_exit_date")
    constituent, constituent_selection = _rank_constituent(proxy_row, source_rows)
    base["constituent_underlying"] = constituent
    base["constituent_selection"] = constituent_selection
    if constituent is None:
        blockers.append("missing_constituent_source_rows")
    if conn is None:
        blockers.append("options_history_db_unavailable_for_read_only_quote_lookup")
    if blockers:
        base["denominator_status"] = "rejected_pair_candidate"
        base["blockers"] = sorted(set(blockers))
        return base

    assert entry_date is not None and exit_date is not None and constituent is not None
    index_key = (index_underlying, entry_date, ENTRY_MINUTE_ET, "call")
    constituent_key = (constituent, entry_date, ENTRY_MINUTE_ET, "call")
    if index_key not in chain_cache:
        chain_cache[index_key] = _quote_chain(
            conn,
            underlying=index_underlying,
            quote_date=entry_date,
            max_minute=ENTRY_MINUTE_ET,
            option_type="call",
        )
    if constituent_key not in chain_cache:
        chain_cache[constituent_key] = _quote_chain(
            conn,
            underlying=constituent,
            quote_date=entry_date,
            max_minute=ENTRY_MINUTE_ET,
            option_type="call",
        )
    index_chain = chain_cache[index_key]
    constituent_chain = chain_cache[constituent_key]
    index_spread, index_blocker = _select_call_debit_spread(index_chain, entry_date=entry_date)
    credit_spread, credit_blocker = _select_call_credit_spread(constituent_chain, entry_date=entry_date)
    if index_blocker:
        blockers.append(index_blocker)
    if credit_blocker:
        blockers.append(credit_blocker)
    if blockers or index_spread is None or credit_spread is None:
        base["denominator_status"] = "blocked_pair_contract_selection"
        base["blockers"] = sorted(set(blockers or ["missing_pair_contract_selection_surface"]))
        return base

    pair_max_loss = _max_loss_usd(index_spread, credit_spread)
    base.update(
        {
            "candidate_selected": True,
            "denominator_status": "pair_candidate_constructed_waiting_bounded_replay_pricing",
            "blockers": [],
            "index_debit_long_contract": index_spread["long"]["contract_symbol"],
            "index_debit_short_contract": index_spread["short"]["contract_symbol"],
            "constituent_credit_short_contract": credit_spread["short"]["contract_symbol"],
            "constituent_credit_long_contract": credit_spread["long"]["contract_symbol"],
            "index_debit_expiry": index_spread["long"]["expiry"],
            "constituent_credit_expiry": credit_spread["short"]["expiry"],
            "index_debit_width": index_spread["spread_width"],
            "constituent_credit_width": credit_spread["spread_width"],
            "index_debit_entry_debit": index_spread["entry_debit"],
            "constituent_credit_entry_credit": credit_spread["entry_credit"],
            "pair_max_loss_usd": pair_max_loss,
            "required_collateral_usd": pair_max_loss,
            "contract_multiplier": CONTRACT_MULTIPLIER,
            "fees_usd": ROUND_TRIP_CONTRACT_SIDES * PER_CONTRACT_FEE_USD,
            "entry_quote_source_labels": sorted(
                {
                    index_spread["long"]["source_label"],
                    index_spread["short"]["source_label"],
                    credit_spread["short"]["source_label"],
                    credit_spread["long"]["source_label"],
                }
            ),
            "strict_new_identity": ":".join(
                [
                    proxy_date,
                    index_underlying,
                    constituent,
                    index_spread["long"]["contract_symbol"],
                    index_spread["short"]["contract_symbol"],
                    credit_spread["short"]["contract_symbol"],
                    credit_spread["long"]["contract_symbol"],
                ]
            ),
            "source_provenance": {
                "proxy_source": "regular_options_point_in_time_dispersion_concentration_proxy",
                "proxy_known_at_policy": "proxy rows use prior daily source rows known before candidate entry",
                "candidate_selection_uses_future_outcomes": False,
                "contract_selection_basis": "existing trusted intraday OPRA/NBBO entry quote rows only",
            },
        }
    )
    return base


def _build_candidate_rows(
    *,
    proxy: dict[str, Any],
    source_rows: list[dict[str, Any]],
    conn: sqlite3.Connection | None,
) -> list[dict[str, Any]]:
    proxy_rows = [row for row in _as_list(proxy.get("proxy_rows")) if isinstance(row, dict)]
    proxy_rows.sort(key=lambda row: str(row.get("proxy_date_et") or ""))
    dates = [str(row.get("proxy_date_et")) for row in proxy_rows if row.get("proxy_date_et")]
    source_by_date = _build_source_rows_by_date(source_rows)
    chain_cache: dict[tuple[str, str, int, str], list[dict[str, Any]]] = {}
    rows: list[dict[str, Any]] = []
    for index, proxy_row in enumerate(proxy_rows):
        entry_date = dates[index + 1] if index + 1 < len(dates) else None
        exit_index = index + 1 + EXIT_TRADING_DAYS_AFTER_ENTRY
        exit_date = dates[exit_index] if exit_index < len(dates) else None
        proxy_date = str(proxy_row.get("proxy_date_et") or "")
        rows.append(
            _candidate_row(
                proxy_row=proxy_row,
                source_rows=source_by_date.get(proxy_date, []),
                entry_date=entry_date,
                exit_date=exit_date,
                conn=conn,
                chain_cache=chain_cache,
            )
        )
    return rows


def _status(blockers: list[str], selected_count: int) -> str:
    if blockers:
        return "blocked_dispersion_proxy_hybrid_candidate_rows"
    if selected_count <= 0:
        return "dispersion_proxy_hybrid_candidate_rows_classified_no_pairs"
    return "dispersion_proxy_hybrid_candidate_rows_ready_for_bounded_replay"


def build_report(
    *,
    readiness_path: Path = DEFAULT_READINESS,
    proxy_path: Path = DEFAULT_PROXY,
    source_rows_path: Path = DEFAULT_SOURCE_ROWS,
    options_db_path: Path = DEFAULT_OPTIONS_DB,
    generated_at_utc: str | None = None,
    candidate_rows_override: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    readiness, readiness_meta = _load_json(readiness_path, required=True)
    proxy, proxy_meta = _load_json(proxy_path, required=True)
    source_rows, source_rows_meta = _load_jsonl(source_rows_path, required=True)
    if candidate_rows_override is None:
        conn, options_db_meta = _connect_options_db(options_db_path)
        try:
            rows = _build_candidate_rows(proxy=proxy, source_rows=source_rows, conn=conn)
        finally:
            if conn is not None:
                conn.close()
    else:
        rows = candidate_rows_override
        _, options_db_meta = _connect_options_db(options_db_path)
        if options_db_meta.get("status") == "loaded_read_only":
            conn, _ = _connect_options_db(options_db_path)
            if conn is not None:
                conn.close()
    blockers: list[str] = []
    if readiness.get("status") != "dispersion_proxy_hybrid_replay_readiness_ready" or readiness.get("blockers"):
        blockers.append("dispersion_proxy_hybrid_readiness_not_ready")
    if proxy_meta.get("status") != "loaded":
        blockers.append("point_in_time_dispersion_proxy_artifact_missing")
    if source_rows_meta.get("status") != "loaded":
        blockers.append("point_in_time_dispersion_source_rows_missing")
    if options_db_meta.get("status") != "loaded_read_only":
        blockers.append("options_history_db_unavailable_for_read_only_quote_lookup")
    selected_count = sum(1 for row in rows if row.get("candidate_selected") is True)
    status_counts = Counter(str(row.get("denominator_status") or "unknown") for row in rows)
    blocker_counts: Counter[str] = Counter()
    for row in rows:
        for blocker in _as_list(row.get("blockers")):
            blocker_counts[str(blocker)] += 1
    report = {
        "report_id": REPORT_ID,
        "generated_at_utc": generated_at_utc or _utc_now_iso(),
        **READ_ONLY_FLAGS,
        "concept_id": CONCEPT_ID,
        "scope": "read_only_dispersion_proxy_hybrid_candidate_row_trial_ledger",
        "status": _status(blockers, selected_count),
        "source_artifacts": {
            "readiness": readiness_meta,
            "point_in_time_dispersion_proxy": proxy_meta,
            "point_in_time_dispersion_source_rows": source_rows_meta,
            "options_history_db": options_db_meta,
        },
        "denominator_row_count": len(rows),
        "candidate_selected_count": selected_count,
        "candidate_rejected_or_blocked_count": len(rows) - selected_count,
        "denominator_status_counts": {key: status_counts[key] for key in sorted(status_counts)},
        "blocker_counts": {key: blocker_counts[key] for key in sorted(blocker_counts)},
        "blockers": blockers,
        "candidate_rows_path": _rel(DEFAULT_CANDIDATE_ROWS),
        "trial_ledger_rows": rows[:200],
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }
    _validate_report(report)
    return report


def _validate_report(report: dict[str, Any]) -> None:
    for key, expected in READ_ONLY_FLAGS.items():
        if report.get(key) is not expected:
            raise ValueError(f"read-only flag mismatch for {key}")
    for row in _as_list(report.get("trial_ledger_rows")):
        item = _as_dict(row)
        if item.get("accepted_profitability") is not False:
            raise ValueError("candidate rows cannot accept profitability")
        if item.get("historical_rows_are_forward_proof") is not False:
            raise ValueError("candidate rows cannot be forward proof")
        if item.get("protected_holdout_overlap") is not False:
            raise ValueError("candidate rows cannot overlap protected holdout")
        if item.get("undefined_or_uncapped_pair_risk_allowed") is not False:
            raise ValueError("candidate rows cannot allow undefined risk")


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Regular Options Dispersion-Proxy Hybrid Candidate Rows",
        "",
        "This report is generated from `scripts/build_regular_options_dispersion_proxy_hybrid_candidate_rows.py`. It is a read-only trial ledger for the preregistered dispersion-proxy hybrid branch. It writes derived research candidate rows only; it does not import quotes, mutate the options database, append cohorts, change scanner or strategy logic, enable live validation or auto-track, submit broker orders, consume protected holdout, lower proof bars, or promote a lane.",
        "",
        "## Summary",
        "",
        f"- Status: `{report.get('status')}`.",
        f"- Denominator rows: `{report.get('denominator_row_count')}`.",
        f"- Candidate rows selected: `{report.get('candidate_selected_count')}`.",
        f"- Rejected or blocked rows: `{report.get('candidate_rejected_or_blocked_count')}`.",
        f"- Candidate rows path: `{report.get('candidate_rows_path')}`.",
        "",
        "## Denominator Status Counts",
        "",
    ]
    counts = _as_dict(report.get("denominator_status_counts"))
    lines.extend(f"- `{key}`: `{value}`." for key, value in sorted(counts.items())) if counts else lines.append("- None.")
    lines.extend(["", "## Blocker Counts", ""])
    blocker_counts = _as_dict(report.get("blocker_counts"))
    lines.extend(f"- `{key}`: `{value}`." for key, value in sorted(blocker_counts.items())) if blocker_counts else lines.append("- None.")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Selected rows are research candidates for bounded replay only.",
            "- They are not dashboard trades, paper-shadow trades, live trades, broker orders, accepted profitability, promotion evidence, or forward proof.",
            "- Pricing and profitability remain blocked until the separate bounded replay consumes these rows and passes its own strict gates.",
            "",
            "## Forbidden Actions",
            "",
        ]
    )
    lines.extend(f"- `{item}`" for item in _as_list(report.get("forbidden_actions")))
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    report: dict[str, Any],
    *,
    candidate_rows: list[dict[str, Any]],
    candidate_rows_path: Path = DEFAULT_CANDIDATE_ROWS,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    docs_report: Path = DEFAULT_DOCS_REPORT,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_rows_path.parent.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    stamp = _utc_stamp()
    json_path = output_dir / f"candidate_row_trial_ledger_{stamp}.json"
    md_path = output_dir / f"candidate_row_trial_ledger_{stamp}.md"
    latest_json = output_dir / "candidate_row_trial_ledger_latest.json"
    latest_md = output_dir / "candidate_row_trial_ledger_latest.md"
    artifacts = {
        "json": _rel(json_path),
        "markdown": _rel(md_path),
        "latest_json": _rel(latest_json),
        "latest_markdown": _rel(latest_md),
        "candidate_rows_jsonl": _rel(candidate_rows_path),
        "docs_report": _rel(docs_report),
    }
    report_with_artifacts = dict(report)
    report_with_artifacts["artifacts"] = artifacts
    markdown = render_markdown(report_with_artifacts)
    candidate_rows_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in candidate_rows),
        encoding="utf8",
    )
    for path in (json_path, latest_json):
        path.write_text(json.dumps(report_with_artifacts, indent=2, sort_keys=True) + "\n", encoding="utf8")
    for path in (md_path, latest_md, docs_report):
        path.write_text(markdown, encoding="utf8")
    report["artifacts"] = artifacts
    return artifacts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build read-only dispersion-proxy hybrid candidate rows.")
    parser.add_argument("--readiness", type=Path, default=DEFAULT_READINESS)
    parser.add_argument("--point-in-time-dispersion-proxy", type=Path, default=DEFAULT_PROXY)
    parser.add_argument("--source-rows", type=Path, default=DEFAULT_SOURCE_ROWS)
    parser.add_argument("--options-db", type=Path, default=DEFAULT_OPTIONS_DB)
    parser.add_argument("--candidate-rows", type=Path, default=DEFAULT_CANDIDATE_ROWS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOCS_REPORT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)

    readiness, _ = _load_json(args.readiness, required=True)
    proxy, _ = _load_json(args.point_in_time_dispersion_proxy, required=True)
    source_rows, _ = _load_jsonl(args.source_rows, required=True)
    conn, _ = _connect_options_db(args.options_db)
    try:
        candidate_rows = _build_candidate_rows(proxy=proxy, source_rows=source_rows, conn=conn)
    finally:
        if conn is not None:
            conn.close()
    report = build_report(
        readiness_path=args.readiness,
        proxy_path=args.point_in_time_dispersion_proxy,
        source_rows_path=args.source_rows,
        options_db_path=args.options_db,
        candidate_rows_override=candidate_rows,
    )
    if not args.no_write:
        if readiness.get("status") != "dispersion_proxy_hybrid_replay_readiness_ready":
            raise SystemExit("refusing to write candidate rows when readiness is not ready")
        report["artifacts"] = write_outputs(
            report,
            candidate_rows=candidate_rows,
            candidate_rows_path=args.candidate_rows,
            output_dir=args.output_dir,
            docs_report=args.docs_report,
        )
    if args.json_output:
        print(json.dumps(report, indent=2, sort_keys=True))
    elif args.no_write:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
