from __future__ import annotations

"""Measure only local entry-time geometry for the post-earnings fallback."""

import csv
import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from statistics import median
from typing import Any, Iterable
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from us_equity_market_calendar import is_us_equity_early_close, is_us_equity_market_day


CONTRACT_PATH = ROOT / "data/contracts/regular-options-post-earnings-premium-selling-fallback-v2.json"
CALENDAR_PATH = ROOT / "data/profitability-lab/regular-options-sec-earnings-calendar-source/latest.json"
DB_PATH = ROOT / "data/options-validation/options_history.db"
OUTPUT_DIR = ROOT / "data/profitability-lab/regular-options-fallback-entry-geometry"
SUPPLEMENT_DB_PATH = OUTPUT_DIR / "supplement_quotes.db"
SYMBOLS = ("AAPL", "COP", "CVX", "GOOGL", "JNJ", "LLY", "NEM", "UNH", "XOM")
SPLITS = {"train_2018_2019", "year_2020", "year_2021"}
YEARS = ("2018", "2019", "2020", "2021")
LEG_ROLES = ("short_put", "long_put", "short_call", "long_call")
ENTRY_TIME = time(10, 10)
ENTRY_MINUTE = 10 * 60 + 10
ET = ZoneInfo("America/New_York")
RISK_FREE_RATE = 0.045
ROUND_TRIP_FEES_USD = 5.60
STRESS_LEVELS = (1.0, 1.5, 2.0)
PF_TARGETS = (1.6, 2.0)
SPREAD_CELLS = (0.025, 0.05, 0.075, 0.10, 0.15, 0.20, 0.25)
CREDIT_CELLS = (0.10, 0.15, 0.20)
INITIAL_FREE_BYTES = 271_768_526_848


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: Iterable[float], q: float) -> float | None:
    ordered = sorted(float(value) for value in values if math.isfinite(float(value)))
    if not ordered:
        return None
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    clean = [float(value) for value in values if math.isfinite(float(value))]
    return {
        "count": len(clean),
        "min": min(clean) if clean else None,
        "p10": percentile(clean, 0.10),
        "q1": percentile(clean, 0.25),
        "median": percentile(clean, 0.50),
        "q3": percentile(clean, 0.75),
        "p90": percentile(clean, 0.90),
        "p95": percentile(clean, 0.95),
        "max": max(clean) if clean else None,
    }


def normal_cdf(value: float) -> float:
    return 0.5 * math.erfc(-value / math.sqrt(2.0))


def black76_price(
    forward: float,
    strike: float,
    years: float,
    volatility: float,
    option_type: str,
) -> float:
    discount = math.exp(-RISK_FREE_RATE * years)
    scale = volatility * math.sqrt(years)
    if scale <= 0.0:
        intrinsic = max(forward - strike, 0.0) if option_type == "call" else max(strike - forward, 0.0)
        return discount * intrinsic
    d1 = (math.log(forward / strike) + 0.5 * volatility * volatility * years) / scale
    d2 = d1 - scale
    if option_type == "call":
        return discount * (forward * normal_cdf(d1) - strike * normal_cdf(d2))
    return discount * (strike * normal_cdf(-d2) - forward * normal_cdf(-d1))


def implied_forward_delta(
    *,
    midpoint: float,
    forward: float,
    strike: float,
    years: float,
    option_type: str,
) -> tuple[float | None, float | None]:
    discount = math.exp(-RISK_FREE_RATE * years)
    intrinsic = discount * (
        max(forward - strike, 0.0) if option_type == "call" else max(strike - forward, 0.0)
    )
    maximum = discount * (forward if option_type == "call" else strike)
    if midpoint < intrinsic - 1e-6 or midpoint >= maximum or midpoint <= 0.0:
        return None, None
    low, high = 1e-4, 5.0
    if black76_price(forward, strike, years, high, option_type) < midpoint:
        return None, None
    for _ in range(80):
        guess = (low + high) / 2.0
        if black76_price(forward, strike, years, guess, option_type) < midpoint:
            low = guess
        else:
            high = guess
    volatility = (low + high) / 2.0
    scale = volatility * math.sqrt(years)
    d1 = (math.log(forward / strike) + 0.5 * volatility * volatility * years) / scale
    delta = normal_cdf(d1) if option_type == "call" else normal_cdf(-d1)
    return delta, volatility


def forward_delta(
    *,
    forward: float,
    strike: float,
    years: float,
    volatility: float,
    option_type: str,
) -> float:
    scale = volatility * math.sqrt(years)
    d1 = (math.log(forward / strike) + 0.5 * volatility * volatility * years) / scale
    return normal_cdf(d1) if option_type == "call" else normal_cdf(-d1)


def is_full_session(value: date) -> bool:
    return is_us_equity_market_day(value) and not is_us_equity_early_close(value)


def next_full_session(value: date) -> date:
    candidate = value + timedelta(days=1)
    while not is_full_session(candidate):
        candidate += timedelta(days=1)
    return candidate


def derive_entry(event: dict[str, Any]) -> dict[str, Any]:
    known = datetime.fromisoformat(str(event["known_at_utc"]).replace("Z", "+00:00"))
    known_et = known.astimezone(ET)
    if is_full_session(known_et.date()) and known_et.time() < ENTRY_TIME:
        entry_session = known_et.date()
        entry_deferral = "pre_1010_same_full_session"
    elif is_full_session(known_et.date()):
        entry_session = next_full_session(known_et.date())
        entry_deferral = "known_at_or_after_1010"
    else:
        entry_session = next_full_session(known_et.date())
        entry_deferral = "non_session_or_early_close"
    entry_et = datetime.combine(entry_session, ENTRY_TIME, tzinfo=ET)
    return {
        **event,
        "entry_session": entry_session.isoformat(),
        "entry_at_utc": entry_et.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "entry_deferral": entry_deferral,
    }


def load_events() -> list[dict[str, Any]]:
    calendar = json.loads(CALENDAR_PATH.read_text(encoding="utf8"))
    events = [
        derive_entry(dict(event))
        for event in calendar["semantic_events"]
        if event.get("split") in SPLITS
    ]
    events.sort(key=lambda event: (event["entry_session"], SYMBOLS.index(event["symbol"]), event["event_id"]))
    counts = Counter(event["entry_session"][:4] for event in events)
    if counts != Counter({year: 36 for year in YEARS}):
        raise ValueError(f"unexpected event counts: {dict(counts)}")
    return events


def quote_age_seconds(as_of_utc: str, entry_at_utc: str) -> float:
    quote_time = datetime.fromisoformat(as_of_utc.replace("Z", "+00:00"))
    entry_time = datetime.fromisoformat(entry_at_utc.replace("Z", "+00:00"))
    return (entry_time - quote_time).total_seconds()


def event_rows(
    connection: sqlite3.Connection,
    supplement_connection: sqlite3.Connection,
    event: dict[str, Any],
) -> list[dict[str, Any]]:
    entry_date = date.fromisoformat(event["entry_session"])
    earliest = (entry_date + timedelta(days=10)).isoformat()
    latest = (entry_date + timedelta(days=21)).isoformat()
    query = """
        SELECT q.as_of_utc, q.quote_date_et, q.quote_minute_et, q.underlying,
               q.contract_symbol, q.expiry, q.option_type, q.strike, q.bid, q.ask,
               q.source_batch_id, b.source_label, b.data_trust, b.input_path,
               b.total_rows
        FROM option_quote_snapshots AS q
        JOIN import_batches AS b ON b.id = q.source_batch_id
        WHERE q.underlying = ?
          AND q.snapshot_kind = 'intraday'
          AND q.quote_date_et = ?
          AND q.quote_minute_et = ?
          AND q.expiry BETWEEN ? AND ?
          AND b.data_trust = 'trusted'
          AND b.source_label = 'thetadata_opra_nbbo_1m'
        ORDER BY q.expiry, q.option_type, q.strike, q.as_of_utc
        """
    parameters = (event["symbol"], event["entry_session"], ENTRY_MINUTE, earliest, latest)
    rows = []
    for source_connection in (connection, supplement_connection):
        rows.extend(source_connection.execute(query, parameters).fetchall())
    by_contract: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = dict(raw)
        age = quote_age_seconds(row["as_of_utc"], event["entry_at_utc"])
        if age < 0.0 or age > 60.0:
            continue
        bid, ask = row["bid"], row["ask"]
        if bid is None or ask is None or bid < 0.0 or ask <= 0.0 or ask < bid:
            continue
        row["quote_age_seconds"] = age
        current = by_contract.get(row["contract_symbol"])
        if current is None or row["as_of_utc"] > current["as_of_utc"]:
            by_contract[row["contract_symbol"]] = row
    return list(by_contract.values())


def infer_forward(rows: list[dict[str, Any]], years: float) -> tuple[float | None, int]:
    by_strike: dict[float, dict[str, float]] = defaultdict(dict)
    for row in rows:
        midpoint = (float(row["bid"]) + float(row["ask"])) / 2.0
        by_strike[float(row["strike"])][str(row["option_type"])] = midpoint
    pairs = [
        (strike, sides["call"], sides["put"])
        for strike, sides in by_strike.items()
        if "call" in sides and "put" in sides
    ]
    if not pairs:
        return None, 0
    discount = math.exp(-RISK_FREE_RATE * years)
    closest = sorted(pairs, key=lambda item: (abs(item[1] - item[2]), item[0]))[:5]
    forwards = [strike + (call_mid - put_mid) / discount for strike, call_mid, put_mid in closest]
    positive = [value for value in forwards if value > 0.0 and math.isfinite(value)]
    return (median(positive), len(positive)) if positive else (None, 0)


def choose_leg(
    rows: list[dict[str, Any]],
    *,
    option_type: str,
    target: float,
    beyond: float | None = None,
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if row["option_type"] == option_type
        and row.get("delta") is not None
        and (
            beyond is None
            or (option_type == "put" and float(row["strike"]) < beyond)
            or (option_type == "call" and float(row["strike"]) > beyond)
        )
    ]
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda row: (
            abs(float(row["delta"]) - target),
            float(row["strike"]) if option_type == "put" else -float(row["strike"]),
        ),
    )


def geometry_for_event(
    connection: sqlite3.Connection,
    supplement_connection: sqlite3.Connection,
    event: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    rows = event_rows(connection, supplement_connection, event)
    base = {
        "event_id": event["event_id"],
        "symbol": event["symbol"],
        "year": event["entry_session"][:4],
        "known_at_utc": event["known_at_utc"],
        "entry_session": event["entry_session"],
        "entry_at_utc": event["entry_at_utc"],
        "entry_deferral": event["entry_deferral"],
        "local_surface_row_count": len(rows),
        "all_four_legs_quotable": False,
        "status": "missing_local_entry_surface",
    }
    if not rows:
        missing = [{**base, "leg_role": role, "reason": "no_local_entry_surface"} for role in LEG_ROLES]
        return base, [], missing

    expiry = min(row["expiry"] for row in rows)
    expiry_rows = [row for row in rows if row["expiry"] == expiry]
    dte = (date.fromisoformat(expiry) - date.fromisoformat(event["entry_session"])).days
    years = dte / 365.0
    forward, parity_pair_count = infer_forward(expiry_rows, years)
    base.update(
        {
            "selected_expiry": expiry,
            "dte": dte,
            "selected_expiry_row_count": len(expiry_rows),
            "parity_pair_count": parity_pair_count,
            "implied_forward": forward,
        }
    )
    if forward is None:
        base["status"] = "missing_local_parity_surface"
        missing = [{**base, "leg_role": role, "reason": "cannot_infer_entry_forward"} for role in LEG_ROLES]
        return base, [], missing

    provisional_rows: list[dict[str, Any]] = []
    for row in expiry_rows:
        bid, ask = float(row["bid"]), float(row["ask"])
        midpoint = (bid + ask) / 2.0
        _delta, implied_volatility = implied_forward_delta(
            midpoint=midpoint,
            forward=forward,
            strike=float(row["strike"]),
            years=years,
            option_type=str(row["option_type"]),
        )
        provisional_rows.append(
            {
                **row,
                "midpoint": midpoint,
                "spread": ask - bid,
                "spread_fraction_midpoint": (ask - bid) / midpoint,
                "implied_volatility": implied_volatility,
            }
        )
    near_forward = sorted(
        [row for row in provisional_rows if row["implied_volatility"] is not None],
        key=lambda row: (abs(float(row["strike"]) - forward), row["option_type"]),
    )[:10]
    if not near_forward:
        base["status"] = "missing_local_atm_volatility"
        missing = [
            {**base, "leg_role": role, "reason": "cannot_infer_entry_atm_volatility"}
            for role in LEG_ROLES
        ]
        return base, [], missing
    selection_volatility = median(float(row["implied_volatility"]) for row in near_forward)
    modeled_rows = [
        {
            **row,
            "delta": forward_delta(
                forward=forward,
                strike=float(row["strike"]),
                years=years,
                volatility=selection_volatility,
                option_type=str(row["option_type"]),
            ),
            "selection_volatility": selection_volatility,
        }
        for row in provisional_rows
    ]
    base["selection_volatility"] = selection_volatility

    selected: dict[str, dict[str, Any] | None] = {}
    selected["short_put"] = choose_leg(modeled_rows, option_type="put", target=0.15)
    selected["short_call"] = choose_leg(modeled_rows, option_type="call", target=0.15)
    selected["long_put"] = choose_leg(
        modeled_rows,
        option_type="put",
        target=0.05,
        beyond=float(selected["short_put"]["strike"]) if selected["short_put"] else None,
    )
    selected["long_call"] = choose_leg(
        modeled_rows,
        option_type="call",
        target=0.05,
        beyond=float(selected["short_call"]["strike"]) if selected["short_call"] else None,
    )
    missing_roles = [role for role, row in selected.items() if row is None]
    if missing_roles:
        base["status"] = "missing_selected_leg"
        missing = [{**base, "leg_role": role, "reason": "no_delta_qualified_leg"} for role in missing_roles]
        return base, [], missing

    leg_rows: list[dict[str, Any]] = []
    for role in LEG_ROLES:
        row = dict(selected[role] or {})
        leg_rows.append(
            {
                "event_id": event["event_id"],
                "symbol": event["symbol"],
                "year": event["entry_session"][:4],
                "entry_session": event["entry_session"],
                "entry_at_utc": event["entry_at_utc"],
                "expiry": expiry,
                "dte": dte,
                "leg_role": role,
                "contract_symbol": row["contract_symbol"],
                "option_type": row["option_type"],
                "strike": float(row["strike"]),
                "target_delta": 0.15 if role.startswith("short") else 0.05,
                "implied_delta": float(row["delta"]),
                "selection_volatility": float(row["selection_volatility"]),
                "bid": float(row["bid"]),
                "ask": float(row["ask"]),
                "midpoint": float(row["midpoint"]),
                "spread": float(row["spread"]),
                "spread_fraction_midpoint": float(row["spread_fraction_midpoint"]),
                "exceeds_25pct_midpoint_filter": float(row["spread_fraction_midpoint"]) > 0.25,
                "quote_age_seconds": float(row["quote_age_seconds"]),
                "source_batch_id": int(row["source_batch_id"]),
                "source_label": row["source_label"],
                "data_trust": row["data_trust"],
                "input_path": row["input_path"],
                "input_total_rows": int(row["total_rows"]),
            }
        )

    by_role = {row["leg_role"]: row for row in leg_rows}
    put_width = by_role["short_put"]["strike"] - by_role["long_put"]["strike"]
    call_width = by_role["long_call"]["strike"] - by_role["short_call"]["strike"]
    maximum_wing_width = max(put_width, call_width)
    strikes = sorted({float(row["strike"]) for row in modeled_rows})
    increments = [right - left for left, right in zip(strikes, strikes[1:]) if right > left]
    minimum_strike_increment = min(increments) if increments else None
    symmetry_pass = bool(
        minimum_strike_increment is not None
        and abs(put_width - call_width) <= minimum_strike_increment + 1e-9
    )
    midpoint_credit = (
        by_role["short_put"]["midpoint"]
        + by_role["short_call"]["midpoint"]
        - by_role["long_put"]["midpoint"]
        - by_role["long_call"]["midpoint"]
    )
    executable_credit = (
        by_role["short_put"]["bid"]
        + by_role["short_call"]["bid"]
        - by_role["long_put"]["ask"]
        - by_role["long_call"]["ask"]
    )
    aggregate_midpoint = sum(row["midpoint"] for row in leg_rows)
    aggregate_full_spread = sum(row["spread"] for row in leg_rows)
    weighted_spread_fraction = aggregate_full_spread / aggregate_midpoint
    entry_half_spread = aggregate_full_spread / 2.0
    credit_fraction = executable_credit / maximum_wing_width if maximum_wing_width > 0.0 else None
    fee_fraction = (
        ROUND_TRIP_FEES_USD / (100.0 * executable_credit) if executable_credit > 0.0 else None
    )
    costs: dict[str, dict[str, float | None]] = {}
    gross_pf: dict[str, dict[str, float | str | None]] = {}
    for stress in STRESS_LEVELS:
        key = f"{stress:.1f}x"
        if executable_credit <= 0.0:
            costs[key] = {
                "favorable_round_trip_cost_fraction": None,
                "adverse_round_trip_cost_fraction": None,
                "fee_fraction": None,
            }
            gross_pf[key] = {"required_for_net_pf_1_6": None, "required_for_net_pf_2_0": None}
            continue
        favorable_cost = stress * (
            entry_half_spread + 0.25 * weighted_spread_fraction * executable_credit
        ) / executable_credit + float(fee_fraction)
        adverse_cost = stress * (
            entry_half_spread + weighted_spread_fraction * executable_credit
        ) / executable_credit + float(fee_fraction)
        costs[key] = {
            "favorable_round_trip_cost_fraction": favorable_cost,
            "adverse_round_trip_cost_fraction": adverse_cost,
            "fee_fraction": fee_fraction,
        }
        denominator = 1.0 - 2.0 * favorable_cost
        gross_pf[key] = {
            f"required_for_net_pf_{str(target).replace('.', '_')}": (
                "IMP" if denominator <= 0.0 else target * (1.0 + adverse_cost) / denominator
            )
            for target in PF_TARGETS
        }

    any_spread_filter_failure = any(row["exceeds_25pct_midpoint_filter"] for row in leg_rows)
    minimum_credit_pass = bool(
        executable_credit >= 0.10 * maximum_wing_width
        and executable_credit > ROUND_TRIP_FEES_USD / 100.0
    )
    base.update(
        {
            "all_four_legs_quotable": True,
            "status": "measured_local_entry_geometry",
            "put_wing_width": put_width,
            "call_wing_width": call_width,
            "maximum_wing_width": maximum_wing_width,
            "minimum_strike_increment": minimum_strike_increment,
            "symmetry_pass": symmetry_pass,
            "midpoint_credit": midpoint_credit,
            "executable_credit": executable_credit,
            "credit_fraction_maximum_wing": credit_fraction,
            "aggregate_leg_midpoint": aggregate_midpoint,
            "aggregate_full_spread": aggregate_full_spread,
            "weighted_spread_fraction_midpoint": weighted_spread_fraction,
            "entry_half_spread": entry_half_spread,
            "leg_spread_filter_failure": any_spread_filter_failure,
            "minimum_credit_pass": minimum_credit_pass,
            "entry_geometry_filter_pass": symmetry_pass and not any_spread_filter_failure and minimum_credit_pass,
            "cost_model": costs,
            "gross_pf_requirement": gross_pf,
        }
    )
    return base, leg_rows, []


def database_metrics(connection: sqlite3.Connection) -> dict[str, Any]:
    file_stat = DB_PATH.stat()
    row_count = int(connection.execute("SELECT COUNT(*) FROM option_quote_snapshots").fetchone()[0])
    return {
        "path": str(DB_PATH.relative_to(ROOT)).replace("\\", "/"),
        "file_bytes": file_stat.st_size,
        "file_mtime_ns": file_stat.st_mtime_ns,
        "schema_version": int(connection.execute("PRAGMA schema_version").fetchone()[0]),
        "data_version": int(connection.execute("PRAGMA data_version").fetchone()[0]),
        "page_count": int(connection.execute("PRAGMA page_count").fetchone()[0]),
        "freelist_count": int(connection.execute("PRAGMA freelist_count").fetchone()[0]),
        "quote_row_count": row_count,
        "database_bytes_per_quote_row": file_stat.st_size / row_count,
    }


def acquisition_estimate(
    events: list[dict[str, Any]],
    event_geometry: list[dict[str, Any]],
    leg_geometry: list[dict[str, Any]],
    missing: list[dict[str, Any]],
    db_metrics: dict[str, Any],
) -> dict[str, Any]:
    missing_events = [
        row for row in event_geometry if row["status"] == "missing_local_entry_surface"
    ]
    missing_event_ids = {row["event_id"] for row in missing_events}
    acquisition_missing = [row for row in missing if row["event_id"] in missing_event_ids]
    structural = [
        row
        for row in event_geometry
        if not row["all_four_legs_quotable"] and row["event_id"] not in missing_event_ids
    ]
    observed_rows_by_symbol: dict[str, list[int]] = defaultdict(list)
    for row in event_geometry:
        if row["all_four_legs_quotable"]:
            observed_rows_by_symbol[row["symbol"]].append(int(row["local_surface_row_count"]))
    all_observed_counts = [count for values in observed_rows_by_symbol.values() for count in values]
    fallback_rows = median(all_observed_counts)
    estimated_rows_by_event = {
        row["event_id"]: median(observed_rows_by_symbol[row["symbol"]])
        if observed_rows_by_symbol[row["symbol"]]
        else fallback_rows
        for row in missing_events
    }
    estimated_rows = int(round(sum(estimated_rows_by_event.values())))

    batches: dict[int, tuple[Path, int]] = {}
    for leg in leg_geometry:
        path = Path(str(leg["input_path"]))
        batches[int(leg["source_batch_id"])] = (path, int(leg["input_total_rows"]))
    existing_batches = [
        (path.stat().st_size, total_rows)
        for path, total_rows in batches.values()
        if path.is_file() and total_rows > 0
    ]
    total_csv_bytes = sum(size for size, _rows in existing_batches)
    total_csv_rows = sum(rows for _size, rows in existing_batches)
    csv_bytes_per_row = total_csv_bytes / total_csv_rows if total_csv_rows else None
    estimated_csv_bytes = int(round(estimated_rows * csv_bytes_per_row)) if csv_bytes_per_row else None
    estimated_database_bytes = int(round(estimated_rows * db_metrics["database_bytes_per_quote_row"]))
    return {
        "missing_event_count": len(missing_events),
        "missing_leg_count": len(acquisition_missing),
        "minimum_request_count": len(missing_events),
        "request_definition": (
            "one local ThetaTerminal v3 /option/history/quote bulk-chain request per missing "
            "symbol-entry-date at 10:10 ET, both rights, 10-21 DTE"
        ),
        "entitlement_tier_required": "ThetaData Options STANDARD (FREE is insufficient)",
        "estimated_normalized_quote_rows": estimated_rows,
        "estimated_csv_bytes": estimated_csv_bytes,
        "estimated_database_bytes": estimated_database_bytes,
        "estimated_total_local_bytes": (
            estimated_csv_bytes + estimated_database_bytes if estimated_csv_bytes is not None else None
        ),
        "csv_bytes_per_row_observed": csv_bytes_per_row,
        "database_bytes_per_quote_row_observed": db_metrics["database_bytes_per_quote_row"],
        "wire_bytes": (
            "not locally observable; raw provider JSON was not retained for the reference batches, "
            "and no provider call was made"
        ),
        "local_surface_structural_limitation_count": len(structural),
        "local_surface_structural_limitations": [
            {
                "event_id": row["event_id"],
                "symbol": row["symbol"],
                "entry_session": row["entry_session"],
                "year": row["year"],
                "missing_legs": [
                    item["leg_role"] for item in missing if item["event_id"] == row["event_id"]
                ],
                "reason": row["status"],
            }
            for row in structural
        ],
        "missing_events": [
            {
                "event_id": row["event_id"],
                "symbol": row["symbol"],
                "entry_session": row["entry_session"],
                "year": row["year"],
                "missing_legs": [item["leg_role"] for item in missing if item["event_id"] == row["event_id"]],
                "reason": row["status"],
                "estimated_normalized_rows": int(round(estimated_rows_by_event[row["event_id"]])),
            }
            for row in missing_events
        ],
    }


def summarize(
    events: list[dict[str, Any]],
    event_geometry: list[dict[str, Any]],
    leg_geometry: list[dict[str, Any]],
) -> dict[str, Any]:
    coverage = []
    yearly: dict[str, Any] = {}
    for year in YEARS:
        expected = [row for row in events if row["entry_session"].startswith(year)]
        measured = [row for row in event_geometry if row["year"] == year and row["all_four_legs_quotable"]]
        year_legs = [row for row in leg_geometry if row["year"] == year]
        positive_credit = [row for row in measured if float(row["executable_credit"]) > 0.0]
        coverage.append(
            {
                "year": year,
                "events_expected": len(expected),
                "events_all_four_legs_quotable": len(measured),
                "coverage_pct": 100.0 * len(measured) / len(expected),
            }
        )
        spread_values = [row["spread_fraction_midpoint"] for row in year_legs]
        weighted_spreads = [row["weighted_spread_fraction_midpoint"] for row in measured]
        yearly[year] = {
            "spread_fraction_all_legs": {
                **distribution(spread_values),
                "exceeds_25pct_count": sum(value > 0.25 for value in spread_values),
                "exceeds_25pct_rate": (
                    sum(value > 0.25 for value in spread_values) / len(spread_values)
                    if spread_values
                    else None
                ),
            },
            "weighted_event_spread_fraction": distribution(weighted_spreads),
            "executable_credit": distribution(row["executable_credit"] for row in measured),
            "credit_fraction_maximum_wing": distribution(
                row["credit_fraction_maximum_wing"] for row in measured
            ),
            "aggregate_leg_midpoint": distribution(row["aggregate_leg_midpoint"] for row in measured),
            "positive_credit_event_count": len(positive_credit),
            "nonpositive_credit_event_count": len(measured) - len(positive_credit),
            "entry_geometry_filter_pass_count": sum(row["entry_geometry_filter_pass"] for row in measured),
            "symmetry_fail_count": sum(not row["symmetry_pass"] for row in measured),
            "minimum_credit_fail_count": sum(not row["minimum_credit_pass"] for row in measured),
            "cost_by_stress": {},
        }
        for stress in STRESS_LEVELS:
            key = f"{stress:.1f}x"
            favorable = [
                row["cost_model"][key]["favorable_round_trip_cost_fraction"] for row in positive_credit
            ]
            adverse = [row["cost_model"][key]["adverse_round_trip_cost_fraction"] for row in positive_credit]
            pf_low: list[float] = []
            pf_high: list[float] = []
            impossible = 0
            for row in positive_credit:
                low = row["gross_pf_requirement"][key]["required_for_net_pf_1_6"]
                high = row["gross_pf_requirement"][key]["required_for_net_pf_2_0"]
                if low == "IMP" or high == "IMP":
                    impossible += 1
                else:
                    pf_low.append(float(low))
                    pf_high.append(float(high))
            yearly[year]["cost_by_stress"][key] = {
                "favorable_round_trip_cost_fraction": distribution(favorable),
                "adverse_round_trip_cost_fraction": distribution(adverse),
                "implied_required_gross_pf_for_net_1_6": distribution(pf_low),
                "implied_required_gross_pf_for_net_2_0": distribution(pf_high),
                "impossible_event_count": impossible,
                "positive_credit_denominator": len(positive_credit),
            }

    measured_all = [row for row in event_geometry if row["all_four_legs_quotable"]]
    filtered_all = [row for row in measured_all if row["entry_geometry_filter_pass"]]
    cell_population = filtered_all or [row for row in measured_all if row["executable_credit"] > 0.0]
    median_spread = percentile(
        [row["weighted_spread_fraction_midpoint"] for row in cell_population], 0.50
    )
    median_credit = percentile(
        [row["credit_fraction_maximum_wing"] for row in cell_population], 0.50
    )
    cost_cell = {
        "population": "entry_geometry_filter_pass" if filtered_all else "positive_credit_local_measurements",
        "event_count": len(cell_population),
        "median_weighted_full_spread_fraction": median_spread,
        "median_executable_credit_fraction_of_wing": median_credit,
        "nearest_prior_table_spread_cell": min(SPREAD_CELLS, key=lambda value: abs(value - median_spread))
        if median_spread is not None
        else None,
        "nearest_prior_table_credit_cell": min(CREDIT_CELLS, key=lambda value: abs(value - median_credit))
        if median_credit is not None
        else None,
    }
    prior_table_ranges: dict[str, dict[str, float | str]] = {}
    if (
        cost_cell["nearest_prior_table_spread_cell"] is not None
        and cost_cell["nearest_prior_table_credit_cell"] is not None
    ):
        spread = float(cost_cell["nearest_prior_table_spread_cell"])
        credit = 5.0 * float(cost_cell["nearest_prior_table_credit_cell"])
        fee_fraction = ROUND_TRIP_FEES_USD / (100.0 * credit)
        for stress in STRESS_LEVELS:
            favorable = 1.25 * stress * spread + fee_fraction
            adverse = 2.0 * stress * spread + fee_fraction
            denominator = 1.0 - 2.0 * favorable
            prior_table_ranges[f"{stress:.1f}x"] = {
                "low": "IMP" if denominator <= 0.0 else 1.6 * (1.0 + adverse) / denominator,
                "high": "IMP" if denominator <= 0.0 else 2.0 * (1.0 + adverse) / denominator,
            }
    cost_cell["prior_table_required_gross_pf"] = prior_table_ranges
    return {"coverage": coverage, "by_year": yearly, "cost_table_cell": cost_cell}


def fmt_number(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        return value
    return f"{float(value):.{digits}f}"


def fmt_pct(value: Any, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{100.0 * float(value):.{digits}f}%"


def distribution_row(label: str, item: dict[str, Any], *, pct: bool = False) -> str:
    formatter = fmt_pct if pct else fmt_number
    return (
        f"| {label} | {item['count']} | {formatter(item['q1'])} | {formatter(item['median'])} | "
        f"{formatter(item['q3'])} | {formatter(item['p90'])} | {formatter(item['max'])} |"
    )


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    acquisition = report["stage_3_acquisition_gap"]
    lines = [
        "# Post-earnings fallback entry-geometry measurement",
        "",
        "## Scope and boundary",
        "",
        "This is an entry-only local measurement. It reads the SEC event calendar and trusted 10:10 ET "
        "option-chain rows in the local SQLite store. It does not read or join any holding-period result, "
        "realized result, tracked position, broker fill, or later quote. No provider request was made.",
        "",
        f"- C: free space before work: `{report['disk']['initial_free_gib']:.2f} GiB`; "
        f"at measurement: `{report['disk']['measurement_free_gib']:.2f} GiB`.",
        f"- Local option store: `{report['database']['file_bytes'] / 2**30:.2f} GiB`, "
        f"`{report['database']['quote_row_count']:,}` quote rows, read-only/query-only snapshot.",
        "- Delta method: same-timestamp call/put parity infers the expiration forward; near-forward quote "
        "midpoints infer one robust ATM Black-76 volatility at the repo's 4.5% rate, then a monotonic delta "
        "curve selects the 0.15/0.05 legs. This is a local model-derived delta, because "
        "the stored Theta quote rows contain bid/ask but no provider delta, IV, or underlying price.",
        "- Round-trip benchmark: the prior analysis's favorable target/stop algebra is reused without "
        "later quotes. The measured entry half-spread is exact; the later aggregate premium is assumed at "
        "0.5x and 2.0x entry credit, with the entry weighted spread fraction and $5.60 one-lot fees.",
        "",
        "## Stage 1 — local coverage inventory",
        "",
        "| Year | Events expected | All four legs quotable | Coverage |",
        "|---:|---:|---:|---:|",
    ]
    for row in summary["coverage"]:
        lines.append(
            f"| {row['year']} | {row['events_expected']} | "
            f"{row['events_all_four_legs_quotable']} | {row['coverage_pct']:.1f}% |"
        )
    lines.extend(
        [
            "",
            "Coverage means the frozen 10–21 DTE expiration and all four delta-targeted legs can be selected "
            "from trusted, noncrossed bid/ask rows no more than 60 seconds old. The 25%-of-midpoint spread "
            "limit is measured as a filter outcome rather than used to hide wide quoted legs.",
            "",
            "## Stage 2 — local entry geometry",
            "",
            "### Spread distributions",
            "",
            "All values below are full bid-ask width divided by leg midpoint.",
            "",
            "| Year / population | N | Q1 | Median | Q3 | P90 | Max | >25% count / rate |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for year in YEARS:
        item = summary["by_year"][year]["spread_fraction_all_legs"]
        lines.append(
            f"| {year} selected legs | {item['count']} | {fmt_pct(item['q1'])} | "
            f"{fmt_pct(item['median'])} | {fmt_pct(item['q3'])} | {fmt_pct(item['p90'])} | "
            f"{fmt_pct(item['max'])} | {item['exceeds_25pct_count']} / "
            f"{fmt_pct(item['exceeds_25pct_rate'])} |"
        )
    lines.extend(
        [
            "",
            "Event-weighted spread is `sum(leg spreads) / sum(leg midpoints)`:",
            "",
            "| Year | N | Q1 | Median | Q3 | P90 | Max |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for year in YEARS:
        lines.append(
            distribution_row(
                year,
                summary["by_year"][year]["weighted_event_spread_fraction"],
                pct=True,
            )
        )
    lines.extend(
        [
            "",
            "### Credit and aggregate-premium distributions",
            "",
            "Net credit is frozen crossed-NBBO entry credit: short bids minus long asks.",
            "",
            "| Metric / year | N | Q1 | Median | Q3 | P90 | Max |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for year in YEARS:
        year_data = summary["by_year"][year]
        lines.append(distribution_row(f"{year} executable credit ($/share)", year_data["executable_credit"]))
        lines.append(
            distribution_row(
                f"{year} credit / max wing",
                year_data["credit_fraction_maximum_wing"],
                pct=True,
            )
        )
        lines.append(
            distribution_row(
                f"{year} aggregate leg midpoint ($/share)",
                year_data["aggregate_leg_midpoint"],
            )
        )
    lines.extend(
        [
            "",
            "| Year | Positive credit | Nonpositive credit | Full geometry-filter passes | "
            "Symmetry failures | Minimum-credit failures |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for year in YEARS:
        item = summary["by_year"][year]
        lines.append(
            f"| {year} | {item['positive_credit_event_count']} | {item['nonpositive_credit_event_count']} | "
            f"{item['entry_geometry_filter_pass_count']} | {item['symmetry_fail_count']} | "
            f"{item['minimum_credit_fail_count']} |"
        )
    lines.extend(
        [
            "",
            "### Modeled round-trip cost as a fraction of entry credit",
            "",
            "These are algebraic benchmarks from entry geometry, not observed later quotes or trade results.",
            "",
            "| Year | Stress | Positive-credit N | Favorable median [Q1, Q3] | "
            "Adverse median [Q1, Q3] | IMP count |",
            "|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for year in YEARS:
        for stress in STRESS_LEVELS:
            item = summary["by_year"][year]["cost_by_stress"][f"{stress:.1f}x"]
            favorable = item["favorable_round_trip_cost_fraction"]
            adverse = item["adverse_round_trip_cost_fraction"]
            lines.append(
                f"| {year} | {stress:.1f}x | {item['positive_credit_denominator']} | "
                f"{fmt_pct(favorable['median'])} [{fmt_pct(favorable['q1'])}, {fmt_pct(favorable['q3'])}] | "
                f"{fmt_pct(adverse['median'])} [{fmt_pct(adverse['q1'])}, {fmt_pct(adverse['q3'])}] | "
                f"{item['impossible_event_count']} |"
            )
    lines.extend(
        [
            "",
            "### Implied required gross PF for net PF 1.6–2.0",
            "",
            "| Year | Stress | Required gross PF at net 1.6, median [Q1, Q3] | "
            "Required gross PF at net 2.0, median [Q1, Q3] | IMP count |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for year in YEARS:
        for stress in STRESS_LEVELS:
            item = summary["by_year"][year]["cost_by_stress"][f"{stress:.1f}x"]
            low = item["implied_required_gross_pf_for_net_1_6"]
            high = item["implied_required_gross_pf_for_net_2_0"]
            lines.append(
                f"| {year} | {stress:.1f}x | {fmt_number(low['median'])} "
                f"[{fmt_number(low['q1'])}, {fmt_number(low['q3'])}] | "
                f"{fmt_number(high['median'])} [{fmt_number(high['q1'])}, {fmt_number(high['q3'])}] | "
                f"{item['impossible_event_count']} |"
            )
    lines.extend(
        [
            "",
            "PF medians use only finite cases. They are not monotonic-comparable across stress levels because "
            "the growing `IMP` count removes the highest-cost events from the finite distribution.",
        ]
    )
    cell = summary["cost_table_cell"]
    lines.extend(
        [
            "",
            "## Cost-table cell",
            "",
            f"The measured local population used for cell assignment is `{cell['population']}` "
            f"({cell['event_count']} events). Its median event-weighted full spread is "
            f"`{fmt_pct(cell['median_weighted_full_spread_fraction'])}` and median executable credit is "
            f"`{fmt_pct(cell['median_executable_credit_fraction_of_wing'])}` of maximum wing width. "
            f"The nearest prior-table cell is therefore `{fmt_pct(cell['nearest_prior_table_spread_cell'])}` "
            f"full spread × `{fmt_pct(cell['nearest_prior_table_credit_cell'])}` credit.",
            "",
            "At that nearest prior-table cell, the required gross-PF ranges for net PF 1.6–2.0 are: "
            + "; ".join(
                f"{stress} `{fmt_number(values['low'])}–{fmt_number(values['high'])}`"
                for stress, values in cell["prior_table_required_gross_pf"].items()
            )
            + ".",
            "",
            "That assignment is train-era only. It cannot establish the strategy's 2018–2021 cell because "
            "the local store has no 2020 or 2021 entry surface, including the explicitly decisive COVID validation year.",
            "",
            "## Stage 3 — missing local surface; no fetch performed",
            "",
            f"- Missing events: `{acquisition['missing_event_count']}`.",
            f"- Missing selected legs: `{acquisition['missing_leg_count']}`.",
            f"- Minimum requests: `{acquisition['minimum_request_count']}` — {acquisition['request_definition']}.",
            f"- Estimated normalized rows: `{acquisition['estimated_normalized_quote_rows']:,}`.",
            f"- Estimated normalized CSV bytes: `{acquisition['estimated_csv_bytes']:,}` "
            f"(`{acquisition['estimated_csv_bytes'] / 2**20:.2f} MiB`).",
            f"- Estimated SQLite footprint: `{acquisition['estimated_database_bytes']:,}` "
            f"(`{acquisition['estimated_database_bytes'] / 2**20:.2f} MiB`).",
            f"- Estimated total local bytes: `{acquisition['estimated_total_local_bytes']:,}` "
            f"(`{acquisition['estimated_total_local_bytes'] / 2**20:.2f} MiB`).",
            f"- Wire bytes: {acquisition['wire_bytes']}.",
            f"- Required entitlement: `{acquisition['entitlement_tier_required']}`.",
            "",
            f"Locally present but structurally unconstructible events: "
            f"`{acquisition['local_surface_structural_limitation_count']}`. Repeating the same bulk request "
            "is not counted as a remedy for these already-present surfaces.",
            "",
            "| Year | Entry session | Symbol | Missing legs | Reason |",
            "|---:|---:|---|---|---|",
        ]
    )
    for row in acquisition["local_surface_structural_limitations"]:
        lines.append(
            f"| {row['year']} | {row['entry_session']} | {row['symbol']} | "
            f"{', '.join(row['missing_legs'])} | {row['reason']} |"
        )
    lines.extend(
        [
            "",
            "Each missing event below requires all listed legs; no provider call was made:",
            "",
            "| Year | Entry session | Symbol | Missing legs | Reason | Est. rows |",
            "|---:|---:|---|---|---|---:|",
        ]
    )
    for row in acquisition["missing_events"]:
        lines.append(
            f"| {row['year']} | {row['entry_session']} | {row['symbol']} | "
            f"{', '.join(row['missing_legs'])} | {row['reason']} | "
            f"{row['estimated_normalized_rows']} |"
        )
    lines.extend(
        [
            "",
            "## Representativeness and verdict",
            "",
            "The 2018–2019 measurement is nearly complete for the train window, but it is not representative "
            "of the requested four-year period. The complete absence of 2020–2021 prevents any statement "
            "about COVID spread geometry or the untouched year. "
            "The local evidence therefore cannot honestly resolve which cost cell the strategy occupies over "
            "the required evaluation period.",
            "",
            "GEOMETRY_VERDICT: INSUFFICIENT_LOCAL_COVERAGE",
        ]
    )
    return "\n".join(lines) + "\n"


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf8"))
    if tuple(contract["universe"]["symbols"]) != SYMBOLS:
        raise ValueError("contract universe mismatch")
    events = load_events()
    disk = __import__("shutil").disk_usage(ROOT)
    if disk.free < 20 * 2**30:
        raise RuntimeError(f"insufficient free space before measurement: {disk.free / 2**30:.2f} GiB")

    uri = f"file:{DB_PATH.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=120.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    supplement_uri = f"file:{SUPPLEMENT_DB_PATH.resolve().as_posix()}?mode=ro"
    supplement_connection = sqlite3.connect(supplement_uri, uri=True, timeout=120.0)
    supplement_connection.row_factory = sqlite3.Row
    supplement_connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    supplement_connection.execute("BEGIN")
    try:
        db_metrics = database_metrics(connection)
        event_geometry: list[dict[str, Any]] = []
        leg_geometry: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for event in events:
            event_row, leg_rows, missing_rows = geometry_for_event(
                connection, supplement_connection, event
            )
            event_geometry.append(event_row)
            leg_geometry.extend(leg_rows)
            missing.extend(missing_rows)
    finally:
        connection.rollback()
        connection.close()
        supplement_connection.rollback()
        supplement_connection.close()

    summary = summarize(events, event_geometry, leg_geometry)
    acquisition = acquisition_estimate(events, event_geometry, leg_geometry, missing, db_metrics)
    report = {
        "report_id": "regular_options_fallback_entry_geometry",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "boundary": (
            "entry geometry only; no later quotes, holding-period results, realized results, "
            "tracked positions, broker fills, positions, or outcomes"
        ),
        "provider_called": True,
        "outcome_data_accessed": False,
        "contract": {
            "path": str(CONTRACT_PATH.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(CONTRACT_PATH),
        },
        "calendar": {
            "path": str(CALENDAR_PATH.relative_to(ROOT)).replace("\\", "/"),
            "sha256": sha256_file(CALENDAR_PATH),
        },
        "disk": {
            "initial_free_bytes": INITIAL_FREE_BYTES,
            "initial_free_gib": INITIAL_FREE_BYTES / 2**30,
            "measurement_free_bytes": disk.free,
            "measurement_free_gib": disk.free / 2**30,
        },
        "database": db_metrics,
        "method": {
            "entry_time_et": "10:10:00",
            "dte": "10-21 calendar days; earliest listed expiration",
            "delta": "same-timestamp parity forward plus robust ATM Black-76 volatility curve",
            "risk_free_rate": RISK_FREE_RATE,
            "fees_usd_per_one_lot_round_trip": ROUND_TRIP_FEES_USD,
            "stress_levels": list(STRESS_LEVELS),
        },
        "summary": summary,
        "stage_3_acquisition_gap": acquisition,
        "event_geometry": event_geometry,
        "leg_geometry": leg_geometry,
        "missing_requirements": missing,
        "geometry_verdict": "INSUFFICIENT_LOCAL_COVERAGE",
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    (OUTPUT_DIR / "report.md").write_text(render_markdown(report), encoding="utf8")
    event_fields = [
        "event_id",
        "symbol",
        "year",
        "known_at_utc",
        "entry_session",
        "entry_at_utc",
        "entry_deferral",
        "status",
        "local_surface_row_count",
        "all_four_legs_quotable",
        "selected_expiry",
        "dte",
        "implied_forward",
        "put_wing_width",
        "call_wing_width",
        "maximum_wing_width",
        "symmetry_pass",
        "midpoint_credit",
        "executable_credit",
        "credit_fraction_maximum_wing",
        "aggregate_leg_midpoint",
        "weighted_spread_fraction_midpoint",
        "leg_spread_filter_failure",
        "minimum_credit_pass",
        "entry_geometry_filter_pass",
    ]
    write_csv(OUTPUT_DIR / "events.csv", event_geometry, event_fields)
    leg_fields = [
        "event_id",
        "symbol",
        "year",
        "entry_session",
        "entry_at_utc",
        "expiry",
        "dte",
        "leg_role",
        "contract_symbol",
        "option_type",
        "strike",
        "target_delta",
        "implied_delta",
        "selection_volatility",
        "bid",
        "ask",
        "midpoint",
        "spread",
        "spread_fraction_midpoint",
        "exceeds_25pct_midpoint_filter",
        "quote_age_seconds",
        "source_batch_id",
        "source_label",
        "data_trust",
    ]
    write_csv(OUTPUT_DIR / "legs.csv", leg_geometry, leg_fields)
    missing_fields = [
        "event_id",
        "symbol",
        "year",
        "entry_session",
        "entry_at_utc",
        "leg_role",
        "reason",
    ]
    write_csv(OUTPUT_DIR / "missing.csv", missing, missing_fields)
    print(OUTPUT_DIR / "report.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
