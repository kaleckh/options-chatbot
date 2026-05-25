from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
LANE_UNIVERSE_DIR = ROOT / "data" / "options-lanes" / "universes"


def _normalize_lane_id(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _manifest_path(lane_id: str, path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path)
    normalized = _normalize_lane_id(lane_id)
    return LANE_UNIVERSE_DIR / f"{normalized}.json"


def load_lane_universe_manifest(lane_id: str, path: Path | str | None = None) -> dict[str, Any]:
    manifest_path = _manifest_path(lane_id, path)
    with manifest_path.open("r", encoding="utf8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Lane universe manifest must be a JSON object")
    expected_lane = _normalize_lane_id(lane_id)
    actual_lane = _normalize_lane_id(payload.get("lane_id"))
    if expected_lane and actual_lane and expected_lane != actual_lane:
        raise ValueError(f"Lane universe manifest lane_id {actual_lane!r} does not match {expected_lane!r}")
    return payload


def validate_lane_universe_manifest(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["manifest must be a JSON object"]
    if not payload.get("schema_version"):
        errors.append("schema_version is required")
    lane_id = _normalize_lane_id(payload.get("lane_id"))
    if not lane_id:
        errors.append("lane_id is required")
    if not str(payload.get("universe_version") or "").strip():
        errors.append("universe_version is required")
    tiers = payload.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        errors.append("tiers must be a non-empty list")
        return errors

    seen_symbols: set[str] = set()
    seen_tiers: set[str] = set()
    for index, tier in enumerate(tiers):
        if not isinstance(tier, dict):
            errors.append(f"tiers[{index}] must be an object")
            continue
        tier_id = str(tier.get("tier_id") or "").strip()
        if not tier_id:
            errors.append(f"tiers[{index}] missing tier_id")
        elif tier_id in seen_tiers:
            errors.append(f"duplicate tier_id {tier_id}")
        seen_tiers.add(tier_id)
        if "scan_eligible" not in tier:
            errors.append(f"{tier_id or f'tiers[{index}]'} missing scan_eligible")
        if not str(tier.get("admission_status") or "").strip():
            errors.append(f"{tier_id or f'tiers[{index}]'} missing admission_status")
        symbols = [_normalize_symbol(symbol) for symbol in tier.get("symbols") or []]
        symbols = [symbol for symbol in symbols if symbol]
        if not symbols:
            errors.append(f"{tier_id or f'tiers[{index}]'} symbols must be a non-empty list")
        for symbol in symbols:
            if symbol in seen_symbols:
                errors.append(f"duplicate symbol {symbol}")
            seen_symbols.add(symbol)
    return errors


def lane_universe_symbol_rows(
    lane_id: str,
    *,
    path: Path | str | None = None,
    tiers: Iterable[str] | None = None,
    scan_eligible_only: bool = True,
    fallback: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    tier_filter = {str(tier or "").strip() for tier in tiers or [] if str(tier or "").strip()}
    try:
        payload = load_lane_universe_manifest(lane_id, path)
        errors = validate_lane_universe_manifest(payload)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        if fallback is None:
            raise
        return [
            {
                "lane_id": _normalize_lane_id(lane_id),
                "symbol": _normalize_symbol(symbol),
                "tier": "fallback",
                "scan_eligible": True,
                "admission_status": "fallback_manifest_unavailable",
                "sequence": index,
            }
            for index, symbol in enumerate(fallback, start=1)
            if _normalize_symbol(symbol)
        ]
    if errors:
        if fallback is None:
            raise ValueError("Invalid lane universe manifest: " + "; ".join(errors))
        return [
            {
                "lane_id": _normalize_lane_id(lane_id),
                "symbol": _normalize_symbol(symbol),
                "tier": "fallback",
                "scan_eligible": True,
                "admission_status": "fallback_manifest_invalid",
                "sequence": index,
            }
            for index, symbol in enumerate(fallback, start=1)
            if _normalize_symbol(symbol)
        ]

    rows: list[dict[str, Any]] = []
    overrides = payload.get("symbol_overrides") if isinstance(payload.get("symbol_overrides"), dict) else {}
    for tier in payload.get("tiers") or []:
        if not isinstance(tier, dict):
            continue
        tier_id = str(tier.get("tier_id") or "").strip()
        if tier_filter and tier_id not in tier_filter:
            continue
        tier_scan_eligible = tier.get("scan_eligible") is True
        if scan_eligible_only and not tier_scan_eligible:
            continue
        for symbol_value in tier.get("symbols") or []:
            symbol = _normalize_symbol(symbol_value)
            if not symbol:
                continue
            row = {
                "lane_id": payload.get("lane_id"),
                "universe_version": payload.get("universe_version"),
                "symbol": symbol,
                "tier": tier_id,
                "tier_label": tier.get("label"),
                "scan_eligible": tier_scan_eligible,
                "admission_status": tier.get("admission_status"),
                "admission_rule": tier.get("admission_rule"),
                "admission_metadata": dict(tier.get("admission_metadata") or {}),
                "source_label": tier.get("source_label") or payload.get("source_label"),
                "sequence": len(rows) + 1,
            }
            override = overrides.get(symbol)
            if isinstance(override, dict):
                row.update(override)
            rows.append(row)
    return rows


def lane_universe_symbols(
    lane_id: str,
    *,
    path: Path | str | None = None,
    tiers: Iterable[str] | None = None,
    scan_eligible_only: bool = True,
    fallback: Iterable[str] | None = None,
) -> list[str]:
    return [
        row["symbol"]
        for row in lane_universe_symbol_rows(
            lane_id,
            path=path,
            tiers=tiers,
            scan_eligible_only=scan_eligible_only,
            fallback=fallback,
        )
    ]


def lane_universe_summary(lane_id: str, path: Path | str | None = None) -> dict[str, Any]:
    payload = load_lane_universe_manifest(lane_id, path)
    rows = lane_universe_symbol_rows(lane_id, path=path, scan_eligible_only=False)
    by_tier: dict[str, int] = {}
    by_admission_status: dict[str, int] = {}
    scan_eligible_count = 0
    for row in rows:
        tier = str(row.get("tier") or "unknown")
        by_tier[tier] = by_tier.get(tier, 0) + 1
        status = str(row.get("admission_status") or "unknown")
        by_admission_status[status] = by_admission_status.get(status, 0) + 1
        if row.get("scan_eligible") is True:
            scan_eligible_count += 1
    return {
        "lane_id": payload.get("lane_id"),
        "schema_version": payload.get("schema_version"),
        "universe_version": payload.get("universe_version"),
        "generated_at": payload.get("generated_at"),
        "symbol_count": len(rows),
        "scan_eligible_count": scan_eligible_count,
        "by_tier": by_tier,
        "by_admission_status": by_admission_status,
        "admission_policy": payload.get("admission_policy") or {},
    }
