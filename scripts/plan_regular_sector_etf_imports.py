from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from historical_options_store import INTRADAY_SNAPSHOT_KIND  # noqa: E402
from scripts.audit_paid_data_readiness import build_paid_data_readiness_audit  # noqa: E402


DEFAULT_DB_PATH = ROOT / "data" / "options-validation" / "options_history.db"
DEFAULT_THETA_URL = "http://127.0.0.1:25503"
DEFAULT_SOURCE_LABEL = "thetadata_opra_nbbo_1m"
DEFAULT_SECTOR_ETF_SYMBOLS = ("GLD", "TLT", "XLE", "XLF", "SMH", "KRE")
DEFAULT_CONTROL_SYMBOLS = ("IWM",)
DEFAULT_DATE_FROM = "2025-05-22"
DEFAULT_DATE_TO = "2026-05-22"
DEFAULT_PROBE_DATE = "2026-05-22"
DEFAULT_INTRADAY_INTERVAL = "1h"


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_symbol_list(value: str | Sequence[str] | None, default: Sequence[str]) -> list[str]:
    raw_items = default if value is None else (str(value).replace(";", ",").split(",") if isinstance(value, str) else value)
    symbols: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        symbol = str(item).strip().upper()
        if symbol and symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols


def check_theta_terminal(theta_url: str = DEFAULT_THETA_URL, *, timeout: float = 5.0) -> dict[str, Any]:
    status_url = f"{str(theta_url).rstrip('/')}/v2/system/status"
    request = Request(status_url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=float(timeout)) as response:  # noqa: S310 - local operator health probe.
            body = response.read(2000).decode("utf8", errors="replace")
            status_code = int(getattr(response, "status", response.getcode()) or 0)
    except HTTPError as exc:
        status_code = int(exc.code or 0)
        body = exc.read(2000).decode("utf8", errors="replace") if exc.fp else ""
        if status_code == 410:
            return {
                "available": True,
                "status": "available_status_endpoint_gone",
                "url": status_url,
                "http_status": status_code,
                "body_preview": body[:500],
            }
        return {
            "available": False,
            "status": "http_error",
            "url": status_url,
            "http_status": status_code,
            "body_preview": body[:500],
            "error": str(exc),
        }
    except (OSError, URLError) as exc:
        return {
            "available": False,
            "status": "unavailable",
            "url": status_url,
            "error": str(exc),
        }
    return {
        "available": 200 <= status_code < 300,
        "status": "available" if 200 <= status_code < 300 else "http_error",
        "url": status_url,
        "http_status": status_code,
        "body_preview": body[:500],
    }


def _import_command(
    symbol: str,
    *,
    date_from: str,
    date_to: str,
    theta_url: str,
    timeout: float,
    dry_run: bool,
) -> str:
    parts = [
        "python",
        "scripts/import_thetadata_options_nbbo.py",
        "--symbols",
        symbol,
        "--date-from",
        date_from,
        "--date-to",
        date_to,
        "--snapshot-kind",
        INTRADAY_SNAPSHOT_KIND,
        "--start-time",
        "09:45",
        "--end-time",
        "15:55",
        "--interval",
        DEFAULT_INTRADAY_INTERVAL,
        "--min-dte",
        "21",
        "--max-dte",
        "45",
        "--strike-range",
        "20",
        "--right",
        "both",
        "--theta-url",
        theta_url,
        "--timeout",
        str(int(timeout) if float(timeout).is_integer() else timeout),
    ]
    if dry_run:
        parts.append("--dry-run")
    parts.append("--json")
    return " ".join(parts)


def _symbols_needing_import(readiness: dict[str, Any], requested_symbols: Sequence[str]) -> list[str]:
    problem_symbols = {
        str(symbol).upper()
        for key in (
            "missing_required_underlyings",
            "thin_required_underlyings",
            "low_executable_required_underlyings",
        )
        for symbol in readiness.get(key) or []
    }
    return [symbol for symbol in requested_symbols if symbol in problem_symbols]


def _ready_symbols(readiness: dict[str, Any], requested_symbols: Sequence[str]) -> list[str]:
    needs_import = set(_symbols_needing_import(readiness, requested_symbols))
    return [symbol for symbol in requested_symbols if symbol not in needs_import]


def _status_for_plan(
    readiness: dict[str, Any],
    theta_status: dict[str, Any],
    symbols_needing_import: Sequence[str],
) -> str:
    if readiness.get("status") == "ready_for_exact_replay" and not symbols_needing_import:
        return "ready_for_sector_replay"
    if symbols_needing_import and theta_status.get("status") == "not_checked":
        return "blocked_theta_not_checked"
    if symbols_needing_import and not theta_status.get("available"):
        return "blocked_theta_unavailable"
    if symbols_needing_import:
        return "ready_to_import_sector_etfs"
    return "blocked_sector_readiness_quality"


def _blockers_for_plan(
    readiness: dict[str, Any],
    theta_status: dict[str, Any],
    symbols_needing_import: Sequence[str],
) -> list[str]:
    blockers: list[str] = []
    if readiness.get("blocker"):
        blockers.append(str(readiness["blocker"]))
    if symbols_needing_import:
        blockers.append("sector_etf_trusted_intraday_rows_missing_or_thin")
    if symbols_needing_import and not theta_status.get("available"):
        blockers.append("theta_terminal_unavailable")
    return sorted(set(blockers))


def _next_action(status: str, symbols_needing_import: Sequence[str], readiness: dict[str, Any] | None = None) -> str:
    if status == "ready_for_sector_replay":
        return "Add or rerun sector ETF sleeves only after the all-planned runner confirms clean replay metrics."
    if status == "ready_to_import_sector_etfs":
        missing = set((readiness or {}).get("missing_required_underlyings") or [])
        thin = set((readiness or {}).get("thin_required_underlyings") or [])
        if thin and not missing:
            return "Continue the full-import commands for thin sector ETFs, rerun this planner, then add sector sleeves only after ready_for_sector_replay."
        first = symbols_needing_import[0] if symbols_needing_import else "GLD"
        return f"Run the {first} dry-run command first, then import missing sector ETFs and rerun this planner."
    if status == "blocked_theta_not_checked":
        return "Rerun without --skip-theta-check, or verify a trusted OPRA/NBBO source manually before importing."
    if status == "blocked_theta_unavailable":
        return "Start or license ThetaTerminal on the configured URL, rerun this planner, then start with a one-day dry run."
    return "Repair the trusted intraday readiness blocker before adding sector ETF sleeves."


def build_regular_sector_etf_import_plan(
    *,
    db_path: str | Path = DEFAULT_DB_PATH,
    sector_symbols: Sequence[str] = DEFAULT_SECTOR_ETF_SYMBOLS,
    control_symbols: Sequence[str] = DEFAULT_CONTROL_SYMBOLS,
    theta_url: str = DEFAULT_THETA_URL,
    theta_status: dict[str, Any] | None = None,
    source_label: str = DEFAULT_SOURCE_LABEL,
    date_from: str = DEFAULT_DATE_FROM,
    date_to: str = DEFAULT_DATE_TO,
    probe_date: str = DEFAULT_PROBE_DATE,
    min_quote_dates: int = 252,
    min_shared_quote_dates: int = 252,
    min_executable_quote_pct: float = 90.0,
    import_timeout: float = 30.0,
    generated_at: str | None = None,
) -> dict[str, Any]:
    sector_symbols = parse_symbol_list(sector_symbols, DEFAULT_SECTOR_ETF_SYMBOLS)
    control_symbols = parse_symbol_list(control_symbols, DEFAULT_CONTROL_SYMBOLS)
    if not sector_symbols:
        raise ValueError("At least one sector ETF symbol is required.")
    readiness = build_paid_data_readiness_audit(
        db_path=db_path,
        required_underlyings=sector_symbols,
        snapshot_kind=INTRADAY_SNAPSHOT_KIND,
        min_quote_dates=int(min_quote_dates),
        min_shared_quote_dates=int(min_shared_quote_dates),
        min_executable_quote_pct=float(min_executable_quote_pct),
        source_labels=[source_label],
        trusted_only=True,
    )
    control_readiness = (
        build_paid_data_readiness_audit(
            db_path=db_path,
            required_underlyings=control_symbols,
            snapshot_kind=INTRADAY_SNAPSHOT_KIND,
            min_quote_dates=int(min_quote_dates),
            min_shared_quote_dates=min(int(min_shared_quote_dates), int(min_quote_dates)),
            min_executable_quote_pct=float(min_executable_quote_pct),
            source_labels=[source_label],
            trusted_only=True,
        )
        if control_symbols
        else {
            "status": "not_requested",
            "required_underlyings": [],
            "available_underlyings": [],
            "shared_required_quote_dates": {"count": 0, "first": None, "last": None},
        }
    )
    theta = theta_status or check_theta_terminal(theta_url)
    symbols_needing_import = _symbols_needing_import(readiness, sector_symbols)
    status = _status_for_plan(readiness, theta, symbols_needing_import)
    commands = [
        {
            "symbol": symbol,
            "dry_run_command": _import_command(
                symbol,
                date_from=probe_date,
                date_to=probe_date,
                theta_url=theta_url,
                timeout=import_timeout,
                dry_run=True,
            ),
            "full_import_command": _import_command(
                symbol,
                date_from=date_from,
                date_to=date_to,
                theta_url=theta_url,
                timeout=import_timeout,
                dry_run=False,
            ),
        }
        for symbol in symbols_needing_import
    ]
    return {
        "generated_at": generated_at or _utc_now_iso(),
        "status": status,
        "blockers": _blockers_for_plan(readiness, theta, symbols_needing_import),
        "next_action": _next_action(status, symbols_needing_import, readiness),
        "proof_policy": (
            "Sector ETF sleeves are not proof candidates until each symbol has trusted intraday "
            "OPRA/NBBO rows and the frozen all-planned/evaluator gates pass."
        ),
        "db_path": str(Path(db_path)),
        "source_label": source_label,
        "snapshot_kind": INTRADAY_SNAPSHOT_KIND,
        "sector_symbols": list(sector_symbols),
        "control_symbols": list(control_symbols),
        "ready_sector_symbols": _ready_symbols(readiness, sector_symbols),
        "symbols_needing_import": symbols_needing_import,
        "theta_terminal": theta,
        "sector_readiness": readiness,
        "control_readiness": control_readiness,
        "import_window": {
            "date_from": date_from,
            "date_to": date_to,
            "probe_date": probe_date,
            "min_dte": 21,
            "max_dte": 45,
            "strike_range": 20,
            "right": "both",
            "start_time": "09:45",
            "end_time": "15:55",
            "interval": DEFAULT_INTRADAY_INTERVAL,
        },
        "import_commands": commands,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan trusted intraday ThetaData imports for regular stock-options sector ETF lanes."
    )
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--symbols", default=",".join(DEFAULT_SECTOR_ETF_SYMBOLS))
    parser.add_argument("--control-symbols", default=",".join(DEFAULT_CONTROL_SYMBOLS))
    parser.add_argument("--theta-url", default=DEFAULT_THETA_URL)
    parser.add_argument("--date-from", default=DEFAULT_DATE_FROM)
    parser.add_argument("--date-to", default=DEFAULT_DATE_TO)
    parser.add_argument("--probe-date", default=DEFAULT_PROBE_DATE)
    parser.add_argument("--min-quote-dates", type=int, default=252)
    parser.add_argument("--min-shared-quote-dates", type=int, default=252)
    parser.add_argument("--min-executable-quote-pct", type=float, default=90.0)
    parser.add_argument("--timeout", type=float, default=5.0, help="ThetaTerminal status-check timeout in seconds.")
    parser.add_argument("--import-timeout", type=float, default=30.0)
    parser.add_argument("--skip-theta-check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    theta_status = (
        {"available": False, "status": "not_checked", "url": f"{args.theta_url.rstrip('/')}/v2/system/status"}
        if args.skip_theta_check
        else check_theta_terminal(args.theta_url, timeout=float(args.timeout))
    )
    plan = build_regular_sector_etf_import_plan(
        db_path=args.db_path,
        sector_symbols=parse_symbol_list(args.symbols, DEFAULT_SECTOR_ETF_SYMBOLS),
        control_symbols=parse_symbol_list(args.control_symbols, DEFAULT_CONTROL_SYMBOLS),
        theta_url=args.theta_url,
        theta_status=theta_status,
        date_from=args.date_from,
        date_to=args.date_to,
        probe_date=args.probe_date,
        min_quote_dates=int(args.min_quote_dates),
        min_shared_quote_dates=int(args.min_shared_quote_dates),
        min_executable_quote_pct=float(args.min_executable_quote_pct),
        import_timeout=float(args.import_timeout),
    )
    if args.json:
        print(json.dumps(plan, indent=2))
        return 0
    compact = {
        "status": plan["status"],
        "blockers": plan["blockers"],
        "ready_sector_symbols": plan["ready_sector_symbols"],
        "symbols_needing_import": plan["symbols_needing_import"],
        "theta_terminal": plan["theta_terminal"],
        "next_action": plan["next_action"],
        "first_import_command": (plan["import_commands"][0] if plan["import_commands"] else None),
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
