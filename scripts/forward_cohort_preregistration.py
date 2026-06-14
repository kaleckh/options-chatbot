from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FORWARD_COHORT_PREREGISTRATION = ROOT / "data" / "contracts" / "forward-cohort-preregistration.json"

AI_COMMODITY_PLAYBOOK_ID = "ai_commodity_infra_observation"
PARKED_PROMOTION_STATE = "parked"
PARKED_CANDIDATE_STATUS_REASON = "parked_outside_forward_cohort"


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def load_forward_cohort_preregistration(
    path: Path | str | None = DEFAULT_FORWARD_COHORT_PREREGISTRATION,
) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def forward_cohort_is_active(contract: dict[str, Any] | None) -> bool:
    if not isinstance(contract, dict):
        return False
    cohort = contract.get("cohort") if isinstance(contract.get("cohort"), dict) else {}
    return (
        _norm(contract.get("contract_id")) == "forward-cohort-preregistration"
        and _norm(contract.get("status")) == "active"
        and bool(cohort.get("frozen"))
    )


def forward_cohort_lane_ids(contract: dict[str, Any] | None) -> list[str]:
    if not isinstance(contract, dict):
        return []
    lanes = contract.get("lanes")
    if not isinstance(lanes, list):
        return []
    lane_ids: list[str] = []
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane_id = _norm(lane.get("lane_id"))
        if lane_id:
            lane_ids.append(lane_id)
    return list(dict.fromkeys(lane_ids))


def parked_regular_lane_ids(contract: dict[str, Any] | None) -> list[str]:
    if not isinstance(contract, dict):
        return []
    suspension = contract.get("suspension") if isinstance(contract.get("suspension"), dict) else {}
    lanes = suspension.get("parked_regular_lanes")
    if not isinstance(lanes, list):
        return []
    return list(dict.fromkeys(_norm(item) for item in lanes if _norm(item)))


def forward_cohort_playbook_is_parked(playbook_id: str | None, contract: dict[str, Any] | None) -> bool:
    if not forward_cohort_is_active(contract):
        return False
    playbook = _norm(playbook_id)
    if not playbook:
        return False
    return playbook in set(parked_regular_lane_ids(contract)) and playbook not in set(forward_cohort_lane_ids(contract))


def scan_enabled_playbook_ids(
    available: Iterable[str],
    *,
    contract: dict[str, Any] | None = None,
    include_commodity: bool = False,
    include_parked: bool = False,
) -> list[str]:
    available_ids = [_norm(item) for item in available if _norm(item)]
    if not forward_cohort_is_active(contract):
        if include_commodity:
            return available_ids
        return [item for item in available_ids if item != AI_COMMODITY_PLAYBOOK_ID]

    cohort_ids = set(forward_cohort_lane_ids(contract))
    parked_ids = set(parked_regular_lane_ids(contract))
    selected: set[str] = set(cohort_ids)
    if include_commodity:
        selected.add(AI_COMMODITY_PLAYBOOK_ID)
    if include_parked:
        selected.update(parked_ids)
    return [item for item in available_ids if item in selected]


def forward_cohort_summary(contract: dict[str, Any] | None) -> dict[str, Any]:
    if not forward_cohort_is_active(contract):
        return {
            "active": False,
            "freeze_date": None,
            "eval_date": None,
            "lane_ids": [],
            "parked_regular_lane_count": 0,
            "parked_regular_lanes": [],
        }
    cohort = contract.get("cohort") if isinstance(contract.get("cohort"), dict) else {}
    parked = parked_regular_lane_ids(contract)
    return {
        "active": True,
        "freeze_date": cohort.get("freeze_date"),
        "eval_date": cohort.get("eval_date"),
        "lane_ids": forward_cohort_lane_ids(contract),
        "parked_regular_lane_count": len(parked),
        "parked_regular_lanes": parked,
    }
