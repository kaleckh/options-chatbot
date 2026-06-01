from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter, HTTPException


SaveProfileFn = Callable[..., None]


def create_profile_router(
    *,
    strategy_profiles: dict[str, dict[str, Any]],
    save_profile: SaveProfileFn,
    changelog_files: Mapping[str, str],
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/profile")
    async def get_profile(type: str = "equity"):
        """Return one strategy profile."""
        if type not in strategy_profiles:
            raise HTTPException(400, f"Unknown profile type: {type}")
        return strategy_profiles[type]

    @router.get("/api/profiles")
    async def get_profiles():
        """Return both strategy profiles."""
        return strategy_profiles

    @router.put("/api/profile")
    async def update_profile(body: dict[str, Any]):
        """Update a strategy profile section."""
        profile_type = body.get("type", "equity")
        updates = body.get("updates", {})
        note = body.get("note", "")

        if profile_type not in strategy_profiles:
            raise HTTPException(400, f"Unknown profile type: {profile_type}")
        if not isinstance(updates, dict):
            raise HTTPException(400, "updates must be an object")

        profile = strategy_profiles[profile_type]
        for section_key, section_value in updates.items():
            if (
                section_key in profile
                and isinstance(profile[section_key], dict)
                and isinstance(section_value, dict)
            ):
                profile[section_key].update(section_value)

        save_profile(note=note or f"{profile_type} profile updated", profile=profile_type)
        return {"ok": True}

    @router.get("/api/changelog")
    async def get_changelog(profile: str = "equity"):
        """Return brain changelog for a profile."""
        changelog_file = changelog_files.get(profile)
        if not changelog_file or not os.path.exists(changelog_file):
            return []
        try:
            with open(changelog_file, encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return []

    @router.get("/api/risk")
    async def get_risk_settings():
        """Return current risk settings for sidebar display."""
        return {
            "equity": strategy_profiles["equity"]["risk"],
            "index": strategy_profiles["index"]["risk"],
        }

    return router
