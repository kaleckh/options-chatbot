from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter, HTTPException


SaveProfileFn = Callable[..., None]
GetStrategyProfileFn = Callable[[str], dict[str, Any]]
GetStrategyProfilesFn = Callable[[], dict[str, dict[str, Any]]]
GetRiskSettingsFn = Callable[[], dict[str, dict[str, Any]]]
UpdateProfileSectionsFn = Callable[[str, dict[str, Any]], dict[str, Any]]


def create_profile_router(
    *,
    strategy_profiles: dict[str, dict[str, Any]] | None = None,
    save_profile: SaveProfileFn,
    changelog_files: Mapping[str, str],
    get_strategy_profile_fn: GetStrategyProfileFn | None = None,
    get_strategy_profiles_fn: GetStrategyProfilesFn | None = None,
    get_risk_settings_fn: GetRiskSettingsFn | None = None,
    update_profile_sections_fn: UpdateProfileSectionsFn | None = None,
) -> APIRouter:
    router = APIRouter()

    def _all_profiles() -> dict[str, dict[str, Any]]:
        if get_strategy_profiles_fn is not None:
            return get_strategy_profiles_fn()
        return strategy_profiles or {}

    def _one_profile(profile_type: str) -> dict[str, Any]:
        if get_strategy_profile_fn is not None:
            try:
                return get_strategy_profile_fn(profile_type)
            except KeyError:
                raise HTTPException(400, f"Unknown profile type: {profile_type}") from None
        profiles = _all_profiles()
        if profile_type not in profiles:
            raise HTTPException(400, f"Unknown profile type: {profile_type}")
        return profiles[profile_type]

    @router.get("/api/profile")
    async def get_profile(type: str = "equity"):
        """Return one strategy profile."""
        return _one_profile(type)

    @router.get("/api/profiles")
    async def get_profiles():
        """Return both strategy profiles."""
        return _all_profiles()

    @router.put("/api/profile")
    async def update_profile(body: dict[str, Any]):
        """Update a strategy profile section."""
        profile_type = body.get("type", "equity")
        updates = body.get("updates", {})
        note = body.get("note", "")

        if not isinstance(updates, dict):
            raise HTTPException(400, "updates must be an object")

        if update_profile_sections_fn is not None:
            try:
                update_profile_sections_fn(profile_type, updates)
            except KeyError:
                raise HTTPException(400, f"Unknown profile type: {profile_type}") from None
            except TypeError:
                raise HTTPException(400, "updates must be an object") from None
        else:
            profile = _one_profile(profile_type)
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
        if get_risk_settings_fn is not None:
            return get_risk_settings_fn()
        profiles = _all_profiles()
        return {
            "equity": profiles["equity"]["risk"],
            "index": profiles["index"]["risk"],
        }

    return router
