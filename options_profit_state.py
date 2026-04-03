from __future__ import annotations

import copy
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_OPTIONS_PROFIT_STATE_DIR = ROOT_DIR / "data" / "options-profit"
DEFAULT_CANDIDATE_MANIFEST_PATH = ROOT_DIR / "docs" / "autoresearch" / "truth-first-champions.json"
OPTIONS_PROFIT_STATE_VERSION = 2
ALLOWED_OPTIONS_PROFIT_SYMBOLS = ("SPY", "QQQ")
ALLOWED_OPTIONS_PROFIT_DIRECTIONS = ("call", "put")
TARGET_SYMBOLS = ALLOWED_OPTIONS_PROFIT_SYMBOLS
DEFAULT_BASE_PROFILE_BY_SYMBOL = {
    "SPY": "index",
    "QQQ": "index",
}

_LIVE_PROFILE_CACHE: dict[str, Any] = {
    "path": None,
    "mtime_ns": None,
    "payload": None,
}


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def utc_now_iso() -> str:
    return _utc_now()


def _state_dir() -> Path:
    override = os.getenv("OPTIONS_PROFIT_STATE_DIR")
    return Path(override).resolve() if override else DEFAULT_OPTIONS_PROFIT_STATE_DIR


def candidates_dir() -> Path:
    return _state_dir() / "candidates"


def decisions_dir() -> Path:
    return _state_dir() / "decisions"


def live_profile_path() -> Path:
    return _state_dir() / "live_profile.json"


def incumbents_path() -> Path:
    return _state_dir() / "incumbents.json"


def status_path() -> Path:
    return _state_dir() / "status.json"


def _default_manifest_path() -> Path:
    override = os.getenv("OPTIONS_PROFIT_CANDIDATE_MANIFEST")
    return Path(override).resolve() if override else DEFAULT_CANDIDATE_MANIFEST_PATH


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except FileNotFoundError:
        return None
    except Exception:
        return None


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(dict(base or {}))
    for key, value in dict(overrides or {}).items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(dict(merged.get(key) or {}), value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _normalize_direction(direction: Any) -> str | None:
    value = str(direction or "").strip().lower()
    return value if value in ALLOWED_OPTIONS_PROFIT_DIRECTIONS else None


def _side_candidate_id(symbol: str, direction: str, cohort_id: str) -> str:
    return f"{str(symbol).strip().upper()}__{str(direction).strip().lower()}__{str(cohort_id).strip()}"


def _candidate_filename(candidate_id: str) -> Path:
    safe_id = str(candidate_id or "").strip()
    if not safe_id:
        raise ValueError("candidate_id is required")
    return candidates_dir() / f"{safe_id}.json"


def _candidate_parts(candidate_id: str) -> tuple[str | None, str | None, str | None]:
    raw = str(candidate_id or "").strip()
    if not raw:
        return None, None, None
    parts = raw.split("__")
    if len(parts) >= 3:
        symbol = parts[0].strip().upper()
        direction = _normalize_direction(parts[1])
        cohort_id = "__".join(part for part in parts[2:] if str(part).strip()).strip() or None
        return symbol or None, direction, cohort_id
    if len(parts) >= 2:
        symbol = parts[0].strip().upper()
        cohort_id = "__".join(part for part in parts[1:] if str(part).strip()).strip() or None
        return symbol or None, None, cohort_id
    return None, None, None


def _candidate_direction_from_id(candidate_id: str) -> str | None:
    _, direction, _ = _candidate_parts(candidate_id)
    return direction


def _candidate_direction_from_payload(payload: Any) -> str | None:
    current = dict(payload or {}) if isinstance(payload, dict) else {}
    return _candidate_direction_from_id(str(current.get("candidate_id") or ""))


def _cohort_id_from_candidate_id(candidate_id: str) -> str | None:
    _, _, cohort_id = _candidate_parts(candidate_id)
    return cohort_id


def _baseline_candidate_id(symbol: str, direction: str) -> str:
    return _side_candidate_id(symbol, direction, "baseline_broad_control")


def _normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    symbol = str(candidate.get("symbol") or "").strip().upper()
    raw_candidate_id = str(candidate.get("candidate_id") or "").strip()
    direction = _normalize_direction(candidate.get("direction")) or _candidate_direction_from_id(raw_candidate_id)
    cohort_id = str(candidate.get("cohort_id") or _cohort_id_from_candidate_id(raw_candidate_id) or "").strip()
    if not symbol or symbol not in ALLOWED_OPTIONS_PROFIT_SYMBOLS:
        raise ValueError(f"Unsupported options profit symbol: {symbol!r}")
    if not direction:
        raise ValueError(f"Unsupported options profit direction: {candidate.get('direction')!r}")
    if not cohort_id:
        raise ValueError("cohort_id is required")
    candidate_id = _side_candidate_id(symbol, direction, cohort_id)
    base_profile = str(candidate.get("base_profile") or DEFAULT_BASE_PROFILE_BY_SYMBOL.get(symbol, "index")).strip()
    return {
        "candidate_id": candidate_id,
        "symbol": symbol,
        "direction": direction,
        "cohort_id": cohort_id,
        "base_profile": base_profile,
        "overrides": copy.deepcopy(dict(candidate.get("overrides") or {})),
        "manifest_source": candidate.get("manifest_source"),
        "replay_policy_path": candidate.get("replay_policy_path"),
        "replay_validation": copy.deepcopy(dict(candidate.get("replay_validation") or {})),
        "role": str(candidate.get("role") or "candidate"),
        "status": str(candidate.get("status") or "candidate"),
        "created_at": str(candidate.get("created_at") or _utc_now()),
        "updated_at": str(candidate.get("updated_at") or _utc_now()),
    }


def save_candidate(candidate: dict[str, Any]) -> Path:
    normalized = _normalize_candidate(candidate)
    normalized["updated_at"] = _utc_now()
    path = _candidate_filename(normalized["candidate_id"])
    _atomic_write_json(path, normalized)
    return path


def load_candidate(candidate_id: str) -> dict[str, Any] | None:
    payload = _load_json(_candidate_filename(candidate_id))
    return dict(payload or {}) if payload else None


def list_candidates() -> list[dict[str, Any]]:
    ensure_options_profit_state()
    items: list[dict[str, Any]] = []
    for path in sorted(candidates_dir().glob("*.json")):
        payload = _load_json(path)
        if payload:
            items.append(payload)
    return items


def _seed_candidates_from_manifest() -> None:
    manifest_path = _default_manifest_path()
    payload = _load_json(manifest_path)
    cohorts = list((payload or {}).get("cohorts") or [])
    symbols = [
        symbol
        for symbol in list((payload or {}).get("symbols") or [])
        if str(symbol).strip().upper() in ALLOWED_OPTIONS_PROFIT_SYMBOLS
    ]
    if not cohorts or not symbols:
        return
    for symbol in symbols:
        normalized_symbol = str(symbol).strip().upper()
        for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS:
            for cohort in cohorts:
                cohort_id = str(cohort.get("id") or "").strip()
                if not cohort_id:
                    continue
                candidate_id = _side_candidate_id(normalized_symbol, direction, cohort_id)
                if _candidate_filename(candidate_id).exists():
                    continue
                save_candidate(
                    {
                        "candidate_id": candidate_id,
                        "symbol": normalized_symbol,
                        "direction": direction,
                        "cohort_id": cohort_id,
                        "base_profile": DEFAULT_BASE_PROFILE_BY_SYMBOL.get(normalized_symbol, "index"),
                        "overrides": dict(cohort.get("overrides") or {}),
                        "manifest_source": str(manifest_path),
                        "role": str(cohort.get("role") or "candidate"),
                        "status": "candidate",
                    }
                )


def _default_candidate(symbol: str, direction: str, *, cohort_id: str = "baseline_broad_control") -> dict[str, Any]:
    normalized_symbol = str(symbol).strip().upper()
    normalized_direction = _normalize_direction(direction) or "call"
    return {
        "candidate_id": _side_candidate_id(normalized_symbol, normalized_direction, cohort_id),
        "symbol": normalized_symbol,
        "direction": normalized_direction,
        "cohort_id": cohort_id,
        "base_profile": DEFAULT_BASE_PROFILE_BY_SYMBOL.get(normalized_symbol, "index"),
        "overrides": {},
        "manifest_source": str(_default_manifest_path()),
        "role": "control" if cohort_id == "baseline_broad_control" else "candidate",
        "status": "candidate",
    }


def _ensure_side_candidate(symbol: str, direction: str, seed: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized_symbol = str(symbol).strip().upper()
    normalized_direction = _normalize_direction(direction) or "call"
    cohort_id = str(
        (seed or {}).get("cohort_id")
        or _cohort_id_from_candidate_id(str((seed or {}).get("candidate_id") or ""))
        or "baseline_broad_control"
    ).strip()
    candidate_id = _side_candidate_id(normalized_symbol, normalized_direction, cohort_id)
    candidate = load_candidate(candidate_id)
    if candidate:
        return candidate
    payload = _default_candidate(normalized_symbol, normalized_direction, cohort_id=cohort_id)
    if seed:
        payload["base_profile"] = str(seed.get("base_profile") or payload["base_profile"])
        payload["overrides"] = copy.deepcopy(dict(seed.get("overrides") or payload["overrides"]))
        payload["manifest_source"] = seed.get("manifest_source") or payload["manifest_source"]
        payload["role"] = str(seed.get("role") or payload["role"])
        payload["status"] = str(seed.get("status") or payload["status"])
        payload["replay_policy_path"] = seed.get("replay_policy_path")
        payload["replay_validation"] = copy.deepcopy(dict(seed.get("replay_validation") or {}))
    return _normalize_candidate(payload)


def _default_live_symbol_side_entry(symbol: str, direction: str) -> dict[str, Any]:
    normalized_symbol = str(symbol).strip().upper()
    normalized_direction = _normalize_direction(direction) or "call"
    candidate_id = _baseline_candidate_id(normalized_symbol, normalized_direction)
    baseline_candidate = load_candidate(candidate_id)
    if not baseline_candidate:
        baseline_candidate = _ensure_side_candidate(
            normalized_symbol,
            normalized_direction,
            _default_candidate(normalized_symbol, normalized_direction),
        )
    return {
        "symbol": normalized_symbol,
        "direction": normalized_direction,
        "candidate_id": candidate_id,
        "cohort_id": baseline_candidate.get("cohort_id"),
        "base_profile": baseline_candidate.get("base_profile"),
        "overrides": copy.deepcopy(dict(baseline_candidate.get("overrides") or {})),
        "manifest_source": baseline_candidate.get("manifest_source"),
        "source": "bootstrap_default",
        "mode": "incumbent",
        "status": "incumbent",
        "applied_at": _utc_now(),
    }


def _default_direction_slots(factory: Any) -> dict[str, dict[str, Any]]:
    return {
        symbol: {
            direction: factory(symbol, direction)
            for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS
        }
        for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS
    }


def _empty_direction_slots() -> dict[str, dict[str, Any | None]]:
    return {
        symbol: {
            direction: None
            for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS
        }
        for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS
    }


def _default_incumbent_side_state(symbol: str, direction: str) -> dict[str, Any]:
    return {
        "symbol": str(symbol).strip().upper(),
        "direction": _normalize_direction(direction) or "call",
        "active": _default_live_symbol_side_entry(symbol, direction),
        "previous": None,
        "canary": None,
        "objective": None,
    }


def _bootstrap_incumbents() -> dict[str, Any]:
    payload = {
        "version": OPTIONS_PROFIT_STATE_VERSION,
        "generated_at": _utc_now(),
        "symbols": _default_direction_slots(_default_incumbent_side_state),
        "current_canary": _empty_direction_slots(),
    }
    _atomic_write_json(incumbents_path(), payload)
    return payload


def _bootstrap_live_profile() -> dict[str, Any]:
    payload = {
        "version": OPTIONS_PROFIT_STATE_VERSION,
        "generated_at": _utc_now(),
        "symbols": _default_direction_slots(_default_live_symbol_side_entry),
    }
    _atomic_write_json(live_profile_path(), payload)
    _LIVE_PROFILE_CACHE.update({"path": str(live_profile_path()), "mtime_ns": None, "payload": None})
    return payload


def _default_status_payload() -> dict[str, Any]:
    active_incumbents = _default_direction_slots(_default_live_symbol_side_entry)
    return {
        "version": OPTIONS_PROFIT_STATE_VERSION,
        "generated_at": _utc_now(),
        "measurement_gate": {
            "state": "blocked",
            "blockers": ["Options profit cycle has not run yet."],
            "warnings": [],
        },
        "active_incumbents": active_incumbents,
        "current_canary": _empty_direction_slots(),
        "candidate_rankings": [],
        "last_decision": {
            "action": "not_started",
            "summary": "Options profit cycle has not run yet.",
        },
        "blockers": ["Options profit cycle has not run yet."],
    }


def _copy_top_level_extras(payload: dict[str, Any], *, exclude: set[str]) -> dict[str, Any]:
    return {
        key: copy.deepcopy(value)
        for key, value in dict(payload or {}).items()
        if key not in exclude
    }


def _looks_like_direction_map(value: Any) -> bool:
    data = dict(value or {}) if isinstance(value, dict) else {}
    return any(direction in data for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS)


def _normalize_live_symbol_side_entry(symbol: str, direction: str, entry: dict[str, Any] | None) -> dict[str, Any]:
    if not entry:
        return _default_live_symbol_side_entry(symbol, direction)
    normalized_symbol = str(symbol).strip().upper()
    normalized_direction = _normalize_direction(direction) or "call"
    seed = dict(entry or {})
    candidate = _ensure_side_candidate(normalized_symbol, normalized_direction, seed)
    base = {
        "symbol": normalized_symbol,
        "direction": normalized_direction,
        "candidate_id": str(seed.get("candidate_id") or candidate.get("candidate_id") or _baseline_candidate_id(normalized_symbol, normalized_direction)),
        "cohort_id": str(seed.get("cohort_id") or candidate.get("cohort_id") or "baseline_broad_control"),
        "base_profile": str(seed.get("base_profile") or candidate.get("base_profile") or DEFAULT_BASE_PROFILE_BY_SYMBOL.get(normalized_symbol, "index")),
        "overrides": copy.deepcopy(dict(seed.get("overrides") or candidate.get("overrides") or {})),
        "manifest_source": seed.get("manifest_source") or candidate.get("manifest_source"),
        "source": str(seed.get("source") or "bootstrap_default"),
        "mode": str(seed.get("mode") or "incumbent"),
        "status": str(seed.get("status") or "incumbent"),
        "applied_at": str(seed.get("applied_at") or _utc_now()),
    }
    for key, value in seed.items():
        if key not in base:
            base[key] = copy.deepcopy(value)
    base["candidate_id"] = candidate.get("candidate_id") or base["candidate_id"]
    base["cohort_id"] = candidate.get("cohort_id") or base["cohort_id"]
    return base


def _normalize_optional_live_entry(symbol: str, direction: str, entry: Any) -> dict[str, Any] | None:
    if not entry:
        return None
    return _normalize_live_symbol_side_entry(symbol, direction, dict(entry))


def _normalize_canary_metadata(symbol: str, direction: str, entry: Any) -> dict[str, Any] | None:
    if not entry:
        return None
    current = copy.deepcopy(dict(entry or {}))
    normalized_symbol = str(current.get("symbol") or symbol).strip().upper()
    normalized_direction = (
        _normalize_direction(current.get("direction"))
        or _candidate_direction_from_payload(current)
        or _normalize_direction(direction)
        or "call"
    )
    current["symbol"] = normalized_symbol
    current["direction"] = normalized_direction
    candidate = _ensure_side_candidate(normalized_symbol, normalized_direction, current)
    current["candidate_id"] = candidate.get("candidate_id") or current.get("candidate_id")
    current["cohort_id"] = candidate.get("cohort_id") or current.get("cohort_id")
    return current


def _normalize_legacy_rollout_metadata(symbol: str, direction: str, entry: Any) -> dict[str, Any] | None:
    candidate_direction = _candidate_direction_from_payload(entry)
    if candidate_direction != _normalize_direction(direction):
        return None
    return _normalize_canary_metadata(symbol, direction, entry)


def _normalize_legacy_objective(symbol: str, direction: str, entry: Any) -> dict[str, Any] | None:
    candidate_direction = _candidate_direction_from_payload(entry)
    if candidate_direction != _normalize_direction(direction):
        return None
    current = copy.deepcopy(dict(entry or {}))
    candidate = _ensure_side_candidate(symbol, direction, current)
    if current.get("candidate_id") is not None:
        current["candidate_id"] = candidate.get("candidate_id") or current.get("candidate_id")
    if current.get("cohort_id") is not None:
        current["cohort_id"] = candidate.get("cohort_id") or current.get("cohort_id")
    if current.get("symbol") is not None:
        current["symbol"] = str(symbol).strip().upper()
    if current.get("direction") is not None:
        current["direction"] = _normalize_direction(direction) or "call"
    return current


def _normalize_live_profile_state(payload: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    current = dict(payload or {})
    raw_symbols = dict(current.get("symbols") or {})
    normalized_symbols: dict[str, dict[str, Any]] = {}
    for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS:
        raw_symbol_value = raw_symbols.get(symbol)
        if _looks_like_direction_map(raw_symbol_value):
            raw_direction_map = dict(raw_symbol_value or {})
        else:
            raw_direction_map = {
                direction: dict(raw_symbol_value or {})
                for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS
            }
        normalized_symbols[symbol] = {
            direction: _normalize_live_symbol_side_entry(symbol, direction, dict(raw_direction_map.get(direction) or {}))
            for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS
        }
    normalized = {
        "version": OPTIONS_PROFIT_STATE_VERSION,
        "generated_at": str(current.get("generated_at") or _utc_now()),
        "symbols": normalized_symbols,
        **_copy_top_level_extras(current, exclude={"version", "generated_at", "symbols"}),
    }
    return normalized, normalized != current


def _normalize_incumbent_side_state(symbol: str, direction: str, state: dict[str, Any] | None) -> dict[str, Any]:
    raw_state = dict(state or {})
    active_entry = _normalize_optional_live_entry(symbol, direction, raw_state.get("active"))
    if not active_entry:
        active_entry = _default_live_symbol_side_entry(symbol, direction)
    normalized = {
        "symbol": str(symbol).strip().upper(),
        "direction": _normalize_direction(direction) or "call",
        "active": active_entry,
        "previous": _normalize_optional_live_entry(symbol, direction, raw_state.get("previous")),
        "canary": _normalize_canary_metadata(symbol, direction, raw_state.get("canary")),
        "objective": copy.deepcopy(dict(raw_state.get("objective") or {})) or None,
    }
    for key, value in raw_state.items():
        if key not in normalized:
            normalized[key] = copy.deepcopy(value)
    return normalized


def _normalize_incumbents_state(payload: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    current = dict(payload or {})
    raw_symbols = dict(current.get("symbols") or {})
    normalized_symbols: dict[str, dict[str, Any]] = {}
    for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS:
        raw_symbol_value = raw_symbols.get(symbol)
        if _looks_like_direction_map(raw_symbol_value):
            raw_direction_map = dict(raw_symbol_value or {})
        else:
            legacy_state = dict(raw_symbol_value or {})
            if legacy_state and "active" not in legacy_state:
                legacy_state = {
                    "symbol": symbol,
                    "active": legacy_state,
                    "previous": None,
                    "canary": None,
                    "objective": None,
                }
            raw_direction_map = {}
            for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS:
                raw_direction_map[direction] = {
                    "symbol": symbol,
                    "active": copy.deepcopy(legacy_state.get("active")),
                    "previous": copy.deepcopy(legacy_state.get("previous")),
                    "canary": _normalize_legacy_rollout_metadata(symbol, direction, legacy_state.get("canary")),
                    "objective": _normalize_legacy_objective(symbol, direction, legacy_state.get("objective")),
                }
        normalized_symbols[symbol] = {
            direction: _normalize_incumbent_side_state(symbol, direction, dict(raw_direction_map.get(direction) or {}))
            for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS
        }
    normalized_current_canary = {
        symbol: {
            direction: copy.deepcopy(normalized_symbols[symbol][direction].get("canary"))
            for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS
        }
        for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS
    }
    normalized = {
        "version": OPTIONS_PROFIT_STATE_VERSION,
        "generated_at": str(current.get("generated_at") or _utc_now()),
        "symbols": normalized_symbols,
        "current_canary": normalized_current_canary,
        **_copy_top_level_extras(current, exclude={"version", "generated_at", "symbols", "current_canary"}),
    }
    return normalized, normalized != current


def _normalize_rankings(rankings: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for raw_item in list(rankings or []):
        item = dict(raw_item or {})
        symbol = str(item.get("symbol") or "").strip().upper()
        direction = _normalize_direction(item.get("direction")) or _candidate_direction_from_id(str(item.get("candidate_id") or ""))
        if symbol not in ALLOWED_OPTIONS_PROFIT_SYMBOLS or not direction:
            continue
        item["symbol"] = symbol
        item["direction"] = direction
        normalized.append(item)
    return normalized


def _normalize_status_state(payload: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    current = dict(payload or {})
    raw_active = dict(current.get("active_incumbents") or {})
    raw_canary = current.get("current_canary")
    normalized_active: dict[str, dict[str, Any]] = {}
    for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS:
        raw_symbol_value = raw_active.get(symbol)
        if _looks_like_direction_map(raw_symbol_value):
            raw_direction_map = dict(raw_symbol_value or {})
        else:
            raw_direction_map = {
                direction: dict(raw_symbol_value or {})
                for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS
            }
        normalized_active[symbol] = {
            direction: _normalize_live_symbol_side_entry(symbol, direction, dict(raw_direction_map.get(direction) or {}))
            for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS
        }
    normalized_canary = _empty_direction_slots()
    if isinstance(raw_canary, dict):
        if any(symbol in raw_canary for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS):
            for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS:
                symbol_canary = dict(raw_canary.get(symbol) or {})
                for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS:
                    normalized_canary[symbol][direction] = _normalize_canary_metadata(
                        symbol,
                        direction,
                        symbol_canary.get(direction),
                    )
        else:
            legacy_symbol = str(raw_canary.get("symbol") or "").strip().upper()
            if legacy_symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS:
                for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS:
                    normalized_canary[legacy_symbol][direction] = _normalize_legacy_rollout_metadata(
                        legacy_symbol,
                        direction,
                        raw_canary,
                    )
    defaults = _default_status_payload()
    normalized = {
        "version": OPTIONS_PROFIT_STATE_VERSION,
        "generated_at": str(current.get("generated_at") or _utc_now()),
        "measurement_gate": copy.deepcopy(dict(current.get("measurement_gate") or defaults.get("measurement_gate") or {})),
        "active_incumbents": normalized_active,
        "current_canary": normalized_canary,
        "candidate_rankings": _normalize_rankings(list(current.get("candidate_rankings") or [])),
        "last_decision": copy.deepcopy(dict(current.get("last_decision") or defaults.get("last_decision") or {})),
        "blockers": list(current.get("blockers") or defaults.get("blockers") or []),
        **_copy_top_level_extras(
            current,
            exclude={
                "version",
                "generated_at",
                "measurement_gate",
                "active_incumbents",
                "current_canary",
                "candidate_rankings",
                "last_decision",
                "blockers",
            },
        ),
    }
    return normalized, normalized != current


def ensure_options_profit_state() -> Path:
    state_dir = _state_dir()
    candidates_dir().mkdir(parents=True, exist_ok=True)
    decisions_dir().mkdir(parents=True, exist_ok=True)
    _seed_candidates_from_manifest()
    if not incumbents_path().exists():
        _bootstrap_incumbents()
    if not live_profile_path().exists():
        _bootstrap_live_profile()
    if not status_path().exists():
        _atomic_write_json(status_path(), _default_status_payload())

    incumbents_payload, incumbents_changed = _normalize_incumbents_state(_load_json(incumbents_path()))
    if incumbents_changed:
        _atomic_write_json(incumbents_path(), incumbents_payload)

    live_payload, live_changed = _normalize_live_profile_state(_load_json(live_profile_path()))
    if live_changed:
        _atomic_write_json(live_profile_path(), live_payload)
        _LIVE_PROFILE_CACHE.update({"path": str(live_profile_path()), "mtime_ns": None, "payload": None})

    status_payload, status_changed = _normalize_status_state(_load_json(status_path()))
    if status_changed:
        _atomic_write_json(status_path(), status_payload)
    return state_dir


def normalize_live_profile_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized, _ = _normalize_live_profile_state(payload)
    return normalized


def normalize_incumbents_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized, _ = _normalize_incumbents_state(payload)
    return normalized


def normalize_profit_status_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    normalized, _ = _normalize_status_state(payload)
    return normalized


def _raw_has_symbol_side_entry(raw_symbols: Any, symbol: str, direction: str) -> bool:
    symbols = dict(raw_symbols or {}) if isinstance(raw_symbols, dict) else {}
    raw_symbol_value = symbols.get(symbol)
    if not raw_symbol_value:
        return False
    if _looks_like_direction_map(raw_symbol_value):
        return bool(dict(raw_symbol_value or {}).get(direction))
    return True


def _raw_has_current_canary_side(raw_canary: Any, symbol: str, direction: str) -> bool:
    if not isinstance(raw_canary, dict):
        return False
    if any(candidate_symbol in raw_canary for candidate_symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS):
        symbol_canary = raw_canary.get(symbol)
        if _looks_like_direction_map(symbol_canary):
            return bool(dict(symbol_canary or {}).get(direction))
        return False
    legacy_symbol = str(raw_canary.get("symbol") or "").strip().upper()
    if legacy_symbol != symbol:
        return False
    return _candidate_direction_from_payload(raw_canary) == _normalize_direction(direction)


def _raw_incumbents_has_canary(raw_symbols: Any, symbol: str, direction: str) -> bool:
    symbols = dict(raw_symbols or {}) if isinstance(raw_symbols, dict) else {}
    raw_symbol_value = symbols.get(symbol)
    if not raw_symbol_value:
        return False
    if _looks_like_direction_map(raw_symbol_value):
        side_state = dict((raw_symbol_value or {}).get(direction) or {})
        return bool(side_state.get("canary"))
    state = dict(raw_symbol_value or {})
    if state and "active" not in state:
        state = {
            "symbol": symbol,
            "active": state,
            "previous": None,
            "canary": None,
            "objective": None,
        }
    return _candidate_direction_from_payload(state.get("canary")) == _normalize_direction(direction)


def build_read_only_profit_status_view(
    *,
    status_payload: dict[str, Any] | None,
    incumbents_payload: dict[str, Any] | None,
    live_profile_payload: dict[str, Any] | None,
    decision_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw_status = dict(status_payload or {})
    raw_incumbents = dict(incumbents_payload or {})
    raw_live_profile = dict(live_profile_payload or {})
    raw_decision = dict(decision_payload or {})

    normalized_status = normalize_profit_status_payload(raw_status)
    normalized_incumbents = normalize_incumbents_payload(raw_incumbents)
    normalized_live_profile = normalize_live_profile_payload(raw_live_profile)
    normalized_decision_canary = normalize_profit_status_payload(
        {"current_canary": raw_decision.get("current_canary")}
    )["current_canary"]
    defaults = _default_status_payload()

    raw_status_active = dict(raw_status.get("active_incumbents") or {})
    raw_incumbent_symbols = dict(raw_incumbents.get("symbols") or {})
    raw_live_symbols = dict(raw_live_profile.get("symbols") or {})
    raw_status_canary = raw_status.get("current_canary")
    raw_decision_canary = raw_decision.get("current_canary")

    active_incumbents: dict[str, dict[str, Any]] = {}
    current_canary: dict[str, dict[str, Any] | None] = {}
    for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS:
        active_incumbents[symbol] = {}
        current_canary[symbol] = {}
        for direction in ALLOWED_OPTIONS_PROFIT_DIRECTIONS:
            status_active = (
                copy.deepcopy(normalized_status["active_incumbents"][symbol][direction])
                if _raw_has_symbol_side_entry(raw_status_active, symbol, direction)
                else None
            )
            incumbent_active = (
                copy.deepcopy(normalized_incumbents["symbols"][symbol][direction]["active"])
                if _raw_has_symbol_side_entry(raw_incumbent_symbols, symbol, direction)
                else None
            )
            live_active = (
                copy.deepcopy(normalized_live_profile["symbols"][symbol][direction])
                if _raw_has_symbol_side_entry(raw_live_symbols, symbol, direction)
                else None
            )
            active_incumbents[symbol][direction] = (
                status_active
                or incumbent_active
                or live_active
                or copy.deepcopy(defaults["active_incumbents"][symbol][direction])
            )

            status_canary = (
                copy.deepcopy(normalized_status["current_canary"][symbol][direction])
                if _raw_has_current_canary_side(raw_status_canary, symbol, direction)
                else None
            )
            incumbent_canary = (
                copy.deepcopy(normalized_incumbents["current_canary"][symbol][direction])
                if _raw_incumbents_has_canary(raw_incumbent_symbols, symbol, direction)
                else None
            )
            decision_canary = (
                copy.deepcopy(normalized_decision_canary[symbol][direction])
                if _raw_has_current_canary_side(raw_decision_canary, symbol, direction)
                else None
            )
            current_canary[symbol][direction] = status_canary or incumbent_canary or decision_canary

    measurement_gate = (
        copy.deepcopy(dict(raw_status.get("measurement_gate") or {}))
        or copy.deepcopy(dict(raw_decision.get("measurement_gate") or {}))
        or copy.deepcopy(dict(defaults.get("measurement_gate") or {}))
    )
    last_decision = (
        copy.deepcopy(dict(raw_status.get("last_decision") or {}))
        or copy.deepcopy(raw_decision)
        or copy.deepcopy(dict(defaults.get("last_decision") or {}))
    )
    blockers = (
        list(raw_status.get("blockers") or [])
        or list(measurement_gate.get("blockers") or [])
        or list(defaults.get("blockers") or [])
    )
    candidate_rankings = (
        copy.deepcopy(list(normalized_status.get("candidate_rankings") or []))
        if "candidate_rankings" in raw_status
        else []
    )
    return {
        "generated_at": (
            str(raw_status.get("generated_at") or "")
            or str(raw_decision.get("generated_at") or "")
            or str(defaults.get("generated_at") or _utc_now())
        ),
        "daily_truth_refresh": copy.deepcopy(raw_status.get("daily_truth_refresh")),
        "measurement_gate": measurement_gate,
        "active_incumbents": active_incumbents,
        "current_canary": current_canary,
        "last_decision": last_decision,
        "blockers": blockers,
        "candidate_rankings": candidate_rankings,
    }


def load_incumbents_state() -> dict[str, Any]:
    ensure_options_profit_state()
    payload = _load_json(incumbents_path())
    return normalize_incumbents_payload(payload)


def save_incumbents_state(payload: dict[str, Any]) -> Path:
    ensure_options_profit_state()
    current, _ = _normalize_incumbents_state(payload)
    current["generated_at"] = _utc_now()
    current["version"] = OPTIONS_PROFIT_STATE_VERSION
    return _atomic_write_json(incumbents_path(), current)


def load_live_profile_state(*, refresh: bool = False) -> dict[str, Any]:
    ensure_options_profit_state()
    path = live_profile_path()
    try:
        stat = path.stat()
    except FileNotFoundError:
        return _bootstrap_live_profile()
    cache_key = str(path)
    if (
        not refresh
        and _LIVE_PROFILE_CACHE.get("path") == cache_key
        and _LIVE_PROFILE_CACHE.get("mtime_ns") == stat.st_mtime_ns
        and _LIVE_PROFILE_CACHE.get("payload") is not None
    ):
        return copy.deepcopy(dict(_LIVE_PROFILE_CACHE["payload"] or {}))
    payload = _load_json(path) or _bootstrap_live_profile()
    normalized, changed = _normalize_live_profile_state(payload)
    if changed:
        _atomic_write_json(path, normalized)
        stat = path.stat()
    _LIVE_PROFILE_CACHE.update(
        {
            "path": cache_key,
            "mtime_ns": stat.st_mtime_ns,
            "payload": copy.deepcopy(normalized),
        }
    )
    return copy.deepcopy(normalized)


def save_live_profile_state(payload: dict[str, Any]) -> Path:
    ensure_options_profit_state()
    current, _ = _normalize_live_profile_state(payload)
    current["generated_at"] = _utc_now()
    current["version"] = OPTIONS_PROFIT_STATE_VERSION
    written = _atomic_write_json(live_profile_path(), current)
    _LIVE_PROFILE_CACHE.update({"path": str(written), "mtime_ns": None, "payload": None})
    return written


def load_profit_status() -> dict[str, Any]:
    ensure_options_profit_state()
    payload = _load_json(status_path())
    return normalize_profit_status_payload(payload)


def save_profit_status(payload: dict[str, Any]) -> Path:
    ensure_options_profit_state()
    current, _ = _normalize_status_state(payload)
    current["generated_at"] = _utc_now()
    current["version"] = OPTIONS_PROFIT_STATE_VERSION
    return _atomic_write_json(status_path(), current)


def write_decision_record(payload: dict[str, Any], *, suffix: str | None = None) -> Path:
    ensure_options_profit_state()
    current = dict(payload or {})
    current["recorded_at"] = _utc_now()
    candidate_id = str(current.get("candidate_id") or current.get("symbol") or "system").strip() or "system"
    extra = f"_{suffix}" if suffix else ""
    file_name = f"{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{candidate_id}{extra}.json"
    return _atomic_write_json(decisions_dir() / file_name, current)


def latest_decision_record() -> dict[str, Any] | None:
    ensure_options_profit_state()
    files = sorted(decisions_dir().glob("*.json"))
    if not files:
        return None
    return _load_json(files[-1])


def live_profile_overrides_for_symbol(symbol: str, direction: str | None = None) -> dict[str, Any]:
    normalized_direction = _normalize_direction(direction)
    if not normalized_direction:
        return {}
    payload = load_live_profile_state()
    normalized_symbol = str(symbol or "").strip().upper()
    symbol_bucket = dict((payload.get("symbols") or {}).get(normalized_symbol) or {})
    entry = dict(symbol_bucket.get(normalized_direction) or {})
    return copy.deepcopy(dict(entry.get("overrides") or {}))


def live_profile_entry_for_symbol(symbol: str, direction: str | None = None) -> dict[str, Any]:
    normalized_direction = _normalize_direction(direction)
    if not normalized_direction:
        return {}
    payload = load_live_profile_state()
    normalized_symbol = str(symbol or "").strip().upper()
    symbol_bucket = dict((payload.get("symbols") or {}).get(normalized_symbol) or {})
    return copy.deepcopy(dict(symbol_bucket.get(normalized_direction) or {}))


def merge_live_profile(base_profile: dict[str, Any], symbol: str, direction: str | None = None) -> dict[str, Any]:
    overrides = live_profile_overrides_for_symbol(symbol, direction)
    if not overrides:
        return base_profile
    return _deep_merge(base_profile, overrides)


def default_symbol_manifest(symbol: str, direction: str | None = None) -> dict[str, Any]:
    normalized_direction = _normalize_direction(direction)
    if normalized_direction:
        return _default_live_symbol_side_entry(symbol, normalized_direction)
    return {
        side: _default_live_symbol_side_entry(symbol, side)
        for side in ALLOWED_OPTIONS_PROFIT_DIRECTIONS
    }


def load_live_profile() -> dict[str, Any]:
    payload = load_live_profile_state()
    payload.setdefault("version", OPTIONS_PROFIT_STATE_VERSION)
    payload["updated_at"] = str(payload.get("generated_at") or _utc_now())
    return payload


def write_live_profile(payload: dict[str, Any]) -> None:
    save_live_profile_state(payload)


def load_incumbents() -> dict[str, Any]:
    payload = load_incumbents_state()
    payload.setdefault("version", OPTIONS_PROFIT_STATE_VERSION)
    payload["updated_at"] = str(payload.get("generated_at") or _utc_now())
    return payload


def write_incumbents(payload: dict[str, Any]) -> None:
    save_incumbents_state(payload)


def load_status() -> dict[str, Any]:
    payload = load_profit_status()
    payload.setdefault("version", OPTIONS_PROFIT_STATE_VERSION)
    return payload


def write_status(payload: dict[str, Any]) -> None:
    save_profit_status(payload)


def list_candidate_manifests() -> list[dict[str, Any]]:
    return list_candidates()


def write_decision(payload: dict[str, Any], *, candidate_id: str, stage: str | None = None) -> str:
    current = dict(payload or {})
    current["candidate_id"] = str(candidate_id or current.get("candidate_id") or "").strip()
    path = write_decision_record(current, suffix=stage)
    return str(path)
