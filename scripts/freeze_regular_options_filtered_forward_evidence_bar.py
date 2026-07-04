from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REPORT_ID = "regular_options_filtered_forward_evidence_bar"
BAR_ID = "regular_options_filtered_forward_evidence_bar_v1"
FREEZE_TOKEN = "freeze_filtered_forward_evidence_bar_v1"
DEFAULT_POLICY_CONTRACT = ROOT / "data" / "contracts" / "regular-options-frozen-filtered-policy-v1.json"
DEFAULT_OUTPUT = ROOT / "data" / "contracts" / "regular-options-filtered-forward-evidence-bar-v1.json"

PROHIBITED_ACTIONS = (
    "do_not_change_scanner_policy_from_forward_evidence_bar",
    "do_not_promote_lanes_from_forward_evidence_bar",
    "do_not_enable_live_validation_or_auto_track_from_forward_evidence_bar",
    "do_not_submit_broker_orders_from_forward_evidence_bar",
    "do_not_import_quotes_from_forward_evidence_bar",
    "do_not_mutate_evidence_stores_from_forward_evidence_bar",
    "do_not_lower_proof_bars_from_forward_evidence_bar",
    "do_not_consume_protected_holdout_from_forward_evidence_bar",
    "do_not_treat_forward_rows_as_profitability_proof_before_bar_is_met",
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required artifact: {_rel(path)}")
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid JSON in {_rel(path)}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"artifact is not a JSON object: {_rel(path)}")
    return payload


def _refreeze_output_path(output_path: Path, refreeze_token: str | None) -> Path:
    if not refreeze_token:
        return output_path
    suffix = refreeze_token.strip()
    if not suffix.startswith("v") or not suffix[1:].isdigit() or suffix == "v1":
        raise SystemExit("--refreeze-token must be a new version suffix such as v2")
    name = output_path.name
    if "-v1" not in name:
        raise SystemExit("default output name must contain -v1 before refreeze can choose a new version")
    return output_path.with_name(name.replace("-v1", f"-{suffix}", 1))


def build_contract(
    *,
    policy_contract_path: Path = DEFAULT_POLICY_CONTRACT,
    frozen_at_utc: str | None = None,
) -> dict[str, Any]:
    policy_contract = _load_json(policy_contract_path)
    policy_id = str(policy_contract.get("policy_id") or "historical_filtered_candidate_policy_v1")
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "bar_id": BAR_ID,
        "policy_id": policy_id,
        "frozen_at_utc": frozen_at_utc or _utc_now_iso(),
        "source_policy_contract": {
            "path": _rel(policy_contract_path),
            "sha256": _file_hash(policy_contract_path),
            "report_id": policy_contract.get("report_id"),
            "policy_id": policy_id,
            "filter_id": policy_contract.get("filter_id"),
            "conditions_sha256": policy_contract.get("conditions_sha256"),
        },
        "requirements": {
            "min_completed_forward_paper_shadow_rows": 30,
            "min_ticker_week_clusters": 8,
            "min_calendar_months_with_rows": 3,
            "min_percent_cluster_pf_lb_5pct": 1.0,
            "min_usd_cluster_pf_lb_5pct": 1.0,
            "min_total_net_pnl_usd_exclusive": 0.0,
            "max_fixture_rows": 0,
            "bootstrap_draws": 10000,
            "evaluation_may_not_occur_before_min_completed_rows": True,
            "pnl_basis": {
                "percent": "net_pnl_pct",
                "usd": "net_pnl_usd",
                "cluster_key": "ticker:ISO-week from scan_date",
            },
        },
        "approval_authority": False,
        "read_only": True,
        "research_only": True,
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
        "forward_rows_are_profitability_proof": False,
        "scanner_policy_changed": False,
        "live_validation_enabled": False,
        "auto_track_enabled": False,
        "broker_order_allowed": False,
        "quotes_imported": False,
        "evidence_stores_mutated": False,
        "protected_holdout_consumed": False,
        "prohibited_actions": list(PROHIBITED_ACTIONS),
        "notes": [
            "This contract pre-registers the minimum evidence bar for future filtered-policy paper-shadow rows.",
            "The tracker may report progress against this bar but cannot approve trading, promotion, profitability, or scanner-policy changes.",
        ],
    }


def write_contract(contract: dict[str, Any], output_path: Path, *, overwrite: bool = False) -> None:
    if output_path.exists() and not overwrite:
        raise SystemExit(f"refusing to overwrite existing contract: {_rel(output_path)}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze the filtered forward paper-shadow evidence bar contract.")
    parser.add_argument("--policy-contract", type=Path, default=DEFAULT_POLICY_CONTRACT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--freeze-token", default=None)
    parser.add_argument("--refreeze-token", default=None)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args(list(argv))


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.freeze_token != FREEZE_TOKEN:
        raise SystemExit(f"refusing to freeze without --freeze-token {FREEZE_TOKEN}")
    output_path = _refreeze_output_path(args.output, args.refreeze_token)
    contract = build_contract(policy_contract_path=args.policy_contract)
    if not args.no_write:
        write_contract(contract, output_path, overwrite=False)
    if args.json_output:
        print(json.dumps({"contract": contract, "output": _rel(output_path), "wrote": not args.no_write}, indent=2, sort_keys=True))
    else:
        print(f"{'would write' if args.no_write else 'wrote'} {_rel(output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
