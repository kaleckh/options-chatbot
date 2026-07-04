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


REPORT_ID = "regular_options_frozen_filtered_policy"
POLICY_ID = "historical_filtered_candidate_policy_v1"
FREEZE_TOKEN = "freeze_filtered_policy_v1"
TRACKING_START_AT_UTC = "2026-06-30T05:03:45Z"
DEFAULT_FILTERED_AUDIT = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-filtered-simulated-forward-audit" / "latest.json"
)
DEFAULT_FILTER_ITERATION = (
    ROOT / "data" / "profitability-lab" / "regular-options-historical-profitability-filter-iteration" / "latest.json"
)
DEFAULT_OUTPUT = ROOT / "data" / "contracts" / "regular-options-frozen-filtered-policy-v1.json"

PROHIBITED_ACTIONS = (
    "do_not_change_scanner_policy_from_filtered_policy_freeze",
    "do_not_promote_lanes_from_filtered_policy_freeze",
    "do_not_enable_live_validation_or_auto_track_from_filtered_policy_freeze",
    "do_not_submit_broker_orders_from_filtered_policy_freeze",
    "do_not_import_quotes_from_filtered_policy_freeze",
    "do_not_mutate_evidence_stores_from_filtered_policy_freeze",
    "do_not_lower_proof_bars_from_filtered_policy_freeze",
    "do_not_consume_protected_holdout_from_filtered_policy_freeze",
    "do_not_treat_historical_rows_as_forward_profitability_proof",
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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _conditions_sha256(conditions: Sequence[Any]) -> str:
    payload = json.dumps(list(conditions), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf8")).hexdigest()


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
    filtered_audit_path: Path = DEFAULT_FILTERED_AUDIT,
    filter_iteration_path: Path = DEFAULT_FILTER_ITERATION,
    frozen_at_utc: str | None = None,
) -> dict[str, Any]:
    filtered_audit = _load_json(filtered_audit_path)
    filter_iteration = _load_json(filter_iteration_path)
    filter_source = _as_dict(filtered_audit.get("filter_source"))
    conditions = _as_list(filter_source.get("conditions"))
    if not conditions:
        raise SystemExit("filtered audit artifact has no filter_source.conditions to freeze")
    split = _as_dict(filtered_audit.get("split"))
    iteration_split = _as_dict(filter_iteration.get("split"))
    return {
        "report_id": REPORT_ID,
        "schema_version": 1,
        "policy_id": POLICY_ID,
        "frozen_at_utc": frozen_at_utc or _utc_now_iso(),
        "filter_id": filter_source.get("filter_id"),
        "description": filter_source.get("description"),
        "conditions": conditions,
        "conditions_sha256": _conditions_sha256(conditions),
        "tracking_start_at_utc": TRACKING_START_AT_UTC,
        "provenance": {
            "filtered_audit_artifact": {
                "path": _rel(filtered_audit_path),
                "sha256": _file_hash(filtered_audit_path),
                "report_id": filtered_audit.get("report_id"),
                "status": filtered_audit.get("status"),
                "generated_at_utc": filtered_audit.get("generated_at_utc"),
            },
            "filter_iteration_artifact": {
                "path": _rel(filter_iteration_path),
                "sha256": _file_hash(filter_iteration_path),
                "report_id": filter_iteration.get("report_id"),
                "status": filter_iteration.get("status"),
                "generated_at_utc": filter_iteration.get("generated_at_utc"),
            },
            "train_months_at_freeze": split.get("train_months") or iteration_split.get("train_months") or [],
            "audit_months_at_freeze": split.get("audit_months") or iteration_split.get("audit_months") or [],
            "window_months_at_freeze": split.get("window_months") or iteration_split.get("window_months") or [],
        },
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
    }


def write_contract(contract: dict[str, Any], output_path: Path, *, overwrite: bool = False) -> None:
    if output_path.exists() and not overwrite:
        raise SystemExit(f"refusing to overwrite existing contract: {_rel(output_path)}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf8")


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze the regular-options filtered policy contract.")
    parser.add_argument("--filtered-audit", type=Path, default=DEFAULT_FILTERED_AUDIT)
    parser.add_argument("--filter-iteration", type=Path, default=DEFAULT_FILTER_ITERATION)
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
    contract = build_contract(filtered_audit_path=args.filtered_audit, filter_iteration_path=args.filter_iteration)
    if not args.no_write:
        write_contract(contract, output_path, overwrite=False)
    if args.json_output:
        print(json.dumps({"contract": contract, "output": _rel(output_path), "wrote": not args.no_write}, indent=2, sort_keys=True))
    else:
        print(f"{'would write' if args.no_write else 'wrote'} {_rel(output_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
