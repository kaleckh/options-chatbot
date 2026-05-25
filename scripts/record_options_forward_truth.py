import argparse
import copy
import importlib.util
import json
import sys
from contextlib import contextmanager
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND_MAIN_PATH = ROOT / "python-backend" / "main.py"
BACKEND_DIR = BACKEND_MAIN_PATH.parent
DEFAULT_CHAMPION_MANIFEST = ROOT / "docs" / "autoresearch" / "truth-first-champions.json"
for candidate in (ROOT, BACKEND_DIR):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

import options_chatbot as oc
from forward_options_ledger import build_forward_scan_snapshot, record_forward_snapshot
from positions_service import review_open_positions
from supervised_scan import DEFAULT_SCAN_PLAYBOOK_ID, SCAN_PLAYBOOKS, get_scan_playbook, run_supervised_scan
from wfo_optimizer import build_live_options_trade_policy, build_playbook_exit_audit


def _load_backend_module():
    spec = importlib.util.spec_from_file_location("python_backend_main", BACKEND_MAIN_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load backend module from {BACKEND_MAIN_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_champion_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf8"))
    cohorts = list(payload.get("cohorts") or [])
    symbols = list(payload.get("symbols") or [])
    if not cohorts:
        raise ValueError(f"Champion manifest has no cohorts: {path}")
    if not symbols:
        raise ValueError(f"Champion manifest has no symbols: {path}")
    return {
        "path": str(path),
        "symbols": [str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()],
        "cohorts": cohorts,
        "raw": payload,
    }


def _normalize_profile_targets(values) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        target = str(raw or "").strip().lower()
        if target not in {"equity", "index"} or target in seen:
            continue
        seen.add(target)
        normalized.append(target)
    return normalized


def _normalize_directions(values) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        direction = str(raw or "").strip().lower()
        if direction not in {"call", "put"} or direction in seen:
            continue
        seen.add(direction)
        normalized.append(direction)
    return normalized


def _pick_direction(pick: dict) -> str | None:
    raw = pick.get("option_type") or pick.get("direction") or pick.get("type")
    normalized = str(raw or "").strip().lower()
    return normalized if normalized in {"call", "put"} else None


@contextmanager
def _temporary_cohort_context(
    *,
    overrides: dict,
    watchlist_symbols: list[str],
    playbook_id: str | None = None,
    dte_override: int | None = None,
    profile_targets: list[str] | None = None,
):
    previous_profiles = copy.deepcopy(oc.STRATEGY_PROFILES)
    previous_watchlist = list(oc.DEFAULT_WATCHLIST)
    previous_playbooks = copy.deepcopy(SCAN_PLAYBOOKS)
    try:
        oc.DEFAULT_WATCHLIST = list(watchlist_symbols)
        targets = _normalize_profile_targets(profile_targets) or ["equity"]
        for section_key, section_values in dict(overrides or {}).items():
            if not isinstance(section_values, dict):
                continue
            for target in targets:
                if section_key not in oc.STRATEGY_PROFILES.get(target, {}):
                    continue
                oc.STRATEGY_PROFILES[target][section_key].update(section_values)
        if playbook_id and dte_override is not None and playbook_id in SCAN_PLAYBOOKS:
            SCAN_PLAYBOOKS[playbook_id]["target_dte"] = int(dte_override)
        yield
    finally:
        oc.STRATEGY_PROFILES.clear()
        oc.STRATEGY_PROFILES.update(previous_profiles)
        oc.DEFAULT_WATCHLIST = previous_watchlist
        SCAN_PLAYBOOKS.clear()
        SCAN_PLAYBOOKS.update(previous_playbooks)


def _normalized_picks_with_cohort(
    *,
    backend_main,
    picks: list[dict],
    cohort: dict,
) -> list[dict]:
    normalized: list[dict] = []
    for idx, pick in enumerate(picks, start=1):
        item = backend_main._normalize_scan_pick(pick)
        item["cohort_id"] = cohort.get("id")
        item["cohort_role"] = cohort.get("role")
        item["cohort_label"] = cohort.get("label")
        item["candidate_rank"] = idx
        normalized.append(item)
    return normalized


def _normalized_scan_funnel(value: dict | None) -> dict:
    payload = dict(value or {})
    return {
        "raw_candidates": int(payload.get("raw_candidates") or 0),
        "post_policy_visible": int(payload.get("post_policy_visible") or 0),
        "post_guardrails_visible": int(payload.get("post_guardrails_visible") or 0),
        "returned_picks": int(payload.get("returned_picks") or 0),
        "policy_filtered_out": int(payload.get("policy_filtered_out") or 0),
        "guardrail_filtered_out": int(payload.get("guardrail_filtered_out") or 0),
        "final_trimmed": int(payload.get("final_trimmed") or 0),
        "policy_counts": dict(payload.get("policy_counts") or {}),
        "guardrail_counts": dict(payload.get("guardrail_counts") or {}),
        "policy_applied": bool(payload.get("policy_applied")),
        "policy_fail_closed": bool(payload.get("policy_fail_closed")),
        "include_blocked_policy_picks": bool(payload.get("include_blocked_policy_picks")),
        "include_blocked_guardrail_picks": bool(payload.get("include_blocked_guardrail_picks")),
        "drop_counts": dict(payload.get("drop_counts") or {}),
    }


def _aggregate_scan_funnels(values: list[dict]) -> dict:
    aggregate = _normalized_scan_funnel({})
    aggregate["policy_counts"] = {}
    aggregate["guardrail_counts"] = {}
    for value in values:
        current = _normalized_scan_funnel(value)
        for key in (
            "raw_candidates",
            "post_policy_visible",
            "post_guardrails_visible",
            "returned_picks",
            "policy_filtered_out",
            "guardrail_filtered_out",
            "final_trimmed",
        ):
            aggregate[key] += int(current.get(key) or 0)
        for key, count in dict(current.get("drop_counts") or {}).items():
            aggregate["drop_counts"][str(key)] = aggregate["drop_counts"].get(str(key), 0) + int(count or 0)
        for key, count in dict(current.get("policy_counts") or {}).items():
            aggregate["policy_counts"][str(key)] = aggregate["policy_counts"].get(str(key), 0) + int(count or 0)
        for key, count in dict(current.get("guardrail_counts") or {}).items():
            aggregate["guardrail_counts"][str(key)] = aggregate["guardrail_counts"].get(str(key), 0) + int(count or 0)
        aggregate["policy_applied"] = aggregate["policy_applied"] or bool(current.get("policy_applied"))
        aggregate["policy_fail_closed"] = aggregate["policy_fail_closed"] or bool(current.get("policy_fail_closed"))
        aggregate["include_blocked_policy_picks"] = aggregate["include_blocked_policy_picks"] or bool(current.get("include_blocked_policy_picks"))
        aggregate["include_blocked_guardrail_picks"] = aggregate["include_blocked_guardrail_picks"] or bool(current.get("include_blocked_guardrail_picks"))
    return aggregate


def _run_scan_for_cohort(
    *,
    backend_main,
    cohort: dict,
    watchlist_symbols: list[str],
    args,
    playbook: dict,
    policy: dict,
    exit_audit: dict,
) -> dict:
    with _temporary_cohort_context(
        overrides=dict(cohort.get("overrides") or {}),
        watchlist_symbols=watchlist_symbols,
        playbook_id=str(playbook.get("id") or ""),
        dte_override=args.dte,
        profile_targets=list(cohort.get("profile_targets") or []),
    ):
        guardrail_result = run_supervised_scan(
            scan_func=oc.scan_daily_top_trades,
            positions_repository=backend_main.POSITIONS_REPOSITORY,
            n_picks=int(args.n_picks),
            watchlist_size=len(watchlist_symbols),
            playbook_id=str(playbook.get("id") or DEFAULT_SCAN_PLAYBOOK_ID),
            use_recommended_policy=bool(args.use_recommended_policy),
            include_blocked_policy_picks=bool(args.include_blocked_policy_picks),
            include_blocked_guardrail_picks=bool(args.include_blocked_guardrail_picks),
            truth_lane=args.truth_lane,
            min_trades=20,
            max_tickers=8,
            max_sectors=8,
            min_profit_factor=1.05,
            min_directional_accuracy_pct=50.0,
        )
        requested_directions = _normalize_directions(cohort.get("directions"))
        filtered_picks = [
            pick for pick in list(guardrail_result.get("picks") or [])
            if not requested_directions or _pick_direction(pick) in requested_directions
        ]
        picks = _normalized_picks_with_cohort(
            backend_main=backend_main,
            picks=filtered_picks[: int(args.n_picks)],
            cohort=cohort,
        )
        return {
            "cohort_id": cohort.get("id"),
            "cohort_role": cohort.get("role"),
            "cohort_label": cohort.get("label"),
            "overrides": cohort.get("overrides") or {},
            "profile_targets": list(cohort.get("profile_targets") or []),
            "requested_directions": requested_directions,
            "picks": picks,
            "candidate_count": int(guardrail_result.get("candidate_count") or 0),
            "returned_count": len(picks),
            "policy_decision_counts": dict(guardrail_result.get("policy_decision_counts") or {}),
            "guardrail_decision_counts": dict(guardrail_result.get("guardrail_decision_counts") or {}),
            "scan_funnel": _normalized_scan_funnel(guardrail_result.get("scan_funnel")),
            "exposure_snapshot": guardrail_result["exposure_snapshot"],
            "playbook_exit_audit": None if exit_audit.get("error") else exit_audit,
            "playbook_exit_audit_error": exit_audit.get("error"),
        }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record a forward-looking options scanner and tracked-position snapshot into the local truth ledger."
    )
    parser.add_argument("--source", default="manual_snapshot", help="Short label for the recording session.")
    parser.add_argument("--n-picks", type=int, default=oc.DEFAULT_SCAN_PICKS, help="How many scan ideas to keep.")
    parser.add_argument("--playbook", default=DEFAULT_SCAN_PLAYBOOK_ID, help="Scanner playbook to use.")
    parser.add_argument("--dte", type=int, help="Optional DTE override for the scan.")
    parser.add_argument("--truth-lane", default=None, help="Optional truth lane override for the replay-backed policy.")
    parser.add_argument("--use-recommended-policy", action="store_true", help="Apply the replay-backed scan policy before recording.")
    parser.add_argument(
        "--include-exit-audit",
        action="store_true",
        help="Also compute and record the playbook exit audit. Leave off for faster daily maintenance snapshots.",
    )
    parser.add_argument("--include-blocked-policy-picks", action="store_true", help="Keep policy-blocked ideas in the recorded scan snapshot.")
    parser.add_argument("--include-blocked-guardrail-picks", action="store_true", help="Keep guardrail-blocked ideas in the recorded scan snapshot.")
    parser.add_argument(
        "--champion-manifest",
        default=str(DEFAULT_CHAMPION_MANIFEST),
        help="Optional champion manifest used when shadow-recording frozen cohorts.",
    )
    parser.add_argument(
        "--record-frozen-cohorts",
        action="store_true",
        help="Shadow-record the frozen cohort set from the champion manifest. Default behavior records only the current live defaults.",
    )
    parser.add_argument(
        "--cohort-id",
        action="append",
        default=[],
        help="Optional cohort id filter. Repeat to shadow-record only selected cohorts from the manifest.",
    )
    parser.add_argument(
        "--watchlist-symbol",
        action="append",
        default=[],
        help="Optional explicit watchlist override. Repeat to constrain the scan to a fixed symbol set without using frozen cohorts.",
    )
    parser.add_argument("--json", action="store_true", help="Print the full summary JSON.")
    args = parser.parse_args()

    backend_main = _load_backend_module()
    playbook = get_scan_playbook(args.playbook)

    tracked_positions = []
    reviewed_positions = []
    if getattr(backend_main.POSITIONS_REPOSITORY, "is_available", False):
        tracked_positions = backend_main.POSITIONS_REPOSITORY.list_positions("open")
        reviewed_positions = review_open_positions(backend_main.POSITIONS_REPOSITORY)

    policy = {}
    exit_audit = {"error": "Policy not requested"}
    if args.use_recommended_policy:
        policy = build_live_options_trade_policy(
            truth_lane=args.truth_lane,
            min_trades=20,
            max_tickers=8,
            max_sectors=8,
            min_profit_factor=1.05,
            min_directional_accuracy_pct=50.0,
        )
        if args.include_exit_audit:
            exit_audit = build_playbook_exit_audit(
                playbook=str(playbook.get("id") or DEFAULT_SCAN_PLAYBOOK_ID),
                truth_lane=args.truth_lane,
            )
        else:
            exit_audit = {"error": "Exit audit skipped for this snapshot"}

    cohort_snapshots: list[dict] = []
    champion_manifest = None
    manifest_path = Path(args.champion_manifest).expanduser()
    should_shadow_record_cohorts = bool(args.record_frozen_cohorts or args.cohort_id)
    if should_shadow_record_cohorts:
        if not manifest_path.exists():
            raise SystemExit(f"Champion manifest not found: {manifest_path}")
        champion_manifest = _load_champion_manifest(manifest_path)
        requested_ids = {str(item).strip() for item in args.cohort_id if str(item).strip()}
        cohorts = [
            cohort for cohort in champion_manifest["cohorts"]
            if not requested_ids or str(cohort.get("id") or "") in requested_ids
        ]
        if not cohorts:
            raise SystemExit("No cohorts matched the requested --cohort-id filters.")
        for cohort in cohorts:
            cohort_snapshots.append(
                _run_scan_for_cohort(
                    backend_main=backend_main,
                    cohort=cohort,
                    watchlist_symbols=champion_manifest["symbols"],
                    args=args,
                    playbook=playbook,
                    policy=policy,
                    exit_audit=exit_audit,
                )
            )
    else:
        watchlist_symbols = [
            str(symbol).strip().upper()
            for symbol in list(args.watchlist_symbol or [])
            if str(symbol).strip()
        ] or [str(symbol).strip().upper() for symbol in oc.DEFAULT_WATCHLIST]
        default_cohort = {
            "id": "live_default",
            "role": "current_live_defaults",
            "label": "Current Live Defaults",
            "overrides": {},
        }
        cohort_snapshots.append(
            _run_scan_for_cohort(
                backend_main=backend_main,
                cohort=default_cohort,
                watchlist_symbols=watchlist_symbols,
                args=args,
                playbook=playbook,
                policy=policy,
                exit_audit=exit_audit,
            )
        )

    combined_picks: list[dict] = []
    policy_counts: dict[str, int] = {}
    guardrail_counts: dict[str, int] = {}
    cohort_funnels: dict[str, dict] = {}
    for snapshot in cohort_snapshots:
        combined_picks.extend(snapshot.get("picks") or [])
        for key, value in dict(snapshot.get("policy_decision_counts") or {}).items():
            policy_counts[str(key)] = policy_counts.get(str(key), 0) + int(value or 0)
        for key, value in dict(snapshot.get("guardrail_decision_counts") or {}).items():
            guardrail_counts[str(key)] = guardrail_counts.get(str(key), 0) + int(value or 0)
        cohort_id = str(snapshot.get("cohort_id") or "").strip()
        if cohort_id:
            cohort_funnels[cohort_id] = _normalized_scan_funnel(snapshot.get("scan_funnel"))

    aggregate_scan_funnel = _aggregate_scan_funnels(list(cohort_funnels.values()))

    scan_snapshot = build_forward_scan_snapshot(
        picks=combined_picks,
        policy_applied=bool(args.use_recommended_policy),
        policy=policy,
        playbook_exit_audit=None if exit_audit.get("error") else exit_audit,
        playbook_exit_audit_error=exit_audit.get("error"),
        policy_decision_counts=policy_counts,
        guardrail_decision_counts=guardrail_counts,
        candidate_count=sum(int(snapshot.get("candidate_count") or 0) for snapshot in cohort_snapshots),
        returned_count=len(combined_picks),
        scan_funnel=aggregate_scan_funnel,
        playbook=playbook,
        truth_lane=policy.get("truth_source") if isinstance(policy, dict) else None,
        cohort_snapshots=cohort_snapshots,
        cohort_funnels=cohort_funnels,
        cohort_count=len(cohort_snapshots),
        cohort_ids=[
            str(item.get("cohort_id") or "").strip()
            for item in cohort_snapshots
            if str(item.get("cohort_id") or "").strip()
        ],
        champion_manifest_path=champion_manifest.get("path") if champion_manifest else None,
        positions_error=(
            getattr(backend_main.POSITIONS_REPOSITORY, "error_message", None)
            if not getattr(backend_main.POSITIONS_REPOSITORY, "is_available", False)
            else None
        ),
        run_mode="record_options_forward_truth",
        evidence_class=(
            "live_production"
            if str(args.source or "").strip().lower() == "api_scan_auto" and not champion_manifest
            else "research_backfill"
        ),
        is_fixture=bool(champion_manifest),
        policy_artifact_id=champion_manifest.get("id") if champion_manifest else None,
    )

    result = record_forward_snapshot(
        scan_snapshot=scan_snapshot,
        reviewed_positions=reviewed_positions,
        tracked_positions=tracked_positions,
        source_label=args.source,
    )
    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    summary = {
        "session_id": result["session_id"],
        "recorded_at_utc": result["recorded_at_utc"],
        "source_label": result["source_label"],
        "scan_picks_count": result["scan_picks_count"],
        "reviewed_positions_count": result["reviewed_positions_count"],
        "truth_source": result["truth_source"],
        "promotion_status": result["promotion_status"],
        "taken_pick_count": result["taken_pick_count"],
        "skipped_pick_count": result["skipped_pick_count"],
        "blocked_pick_count": result["blocked_pick_count"],
        "cohort_ids_recorded": result["cohort_ids_recorded"],
        "requested_cohort_ids": result.get("requested_cohort_ids"),
        "recording_scope": "frozen_manifest" if champion_manifest else "current_live_defaults",
        "scan_funnel": result.get("scan_funnel"),
        "db_path": result["db_path"],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
