"""Small shared contract for the AI commodity infrastructure lane."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

AI_COMMODITY_INFRA_OBSERVATION_PLAYBOOK_ID = "ai_commodity_infra_observation"

AI_COMMODITY_UNDERLYING_FILTER_OVERRIDES = {
    "avg_volume_20d_min": 1_000_000,
    "avg_dollar_volume_20d_min": 100_000_000,
}


def is_ai_commodity_playbook_id(playbook_id: Any) -> bool:
    return (
        str(playbook_id or "").strip().lower()
        == AI_COMMODITY_INFRA_OBSERVATION_PLAYBOOK_ID
    )


def ai_commodity_underlying_filters(base_filters: Mapping[str, Any]) -> dict[str, Any]:
    return {
        **dict(base_filters),
        **AI_COMMODITY_UNDERLYING_FILTER_OVERRIDES,
    }
