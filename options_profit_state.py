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
ALLOWED_OPTIONS_PROFIT_SYMBOLS = ("SPY", "QQQ")
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


def _candidate_filename(candidate_id: str) -> Path:
    safe_id = str(candidate_id or "").strip()
    if not safe_id:
        raise ValueError("candidate_id is required")
    return candidates_dir() / f"{safe_id}.json"


def _baseline_candidate_id(symbol: str) -> str:
    return f"{str(symbol).strip().upper()}__baseline_broad_control"


def _normalize_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    symbol = str(candidate.get("symbol") or "").strip().upper()
    candidate_id = str(candidate.get("candidate_id") or "").strip()
    if not symbol or symbol not in ALLOWED_OPTIONS_PROFIT_SYMBOLS:
        raise ValueError(f"Unsupported options profit symbol: {symbol!r}")
    if not candidate_id:
        raise ValueError("candidate_id is required")
    base_profile = str(candidate.get("base_profile") or DEFAULT_BASE_PROFILE_BY_SYMBOL.get(symbol, "index")).strip()
    return {
        "candidate_id": candidate_id,
        "symbol": symbol,
        "cohort_id": str(candidate.get("cohort_id") or "").strip() or None,
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
        for cohort in cohorts:
            cohort_id = str(cohort.get("id") or "").strip()
            if not cohort_id:
                continue
            candidate_id = f"{normalized_symbol}__{cohort_id}"
            if _candidate_filename(candidate_id).exists():
                continue
            save_candidate(
                {
                    "candidate_id": candidate_id,
                    "symbol": normalized_symbol,
                    "cohort_id": cohort_id,
                    "base_profile": DEFAULT_BASE_PROFILE_BY_SYMBOL.get(normalized_symbol, "index"),
                    "overrides": dict(cohort.get("overrides") or {}),
                    "manifest_source": str(manifest_path),
                    "role": str(cohort.get("role") or "candidate"),
                    "status": "candidate",
                }
            )


def _default_live_symbol_entry(symbol: str) -> dict[str, Any]:
    normalized_symbol = str(symbol).strip().upper()
    candidate_id = _baseline_candidate_id(normalized_symbol)
    baseline_candidate = load_candidate(candidate_id)
    if not baseline_candidate:
        baseline_candidate = {
            "candidate_id": candidate_id,
            "symbol": normalized_symbol,
            "cohort_id": "baseline_broad_control",
            "base_profile": DEFAULT_BASE_PROFILE_BY_SYMBOL.get(normalized_symbol, "index"),
            "overrides": {},
            "manifest_source": str(_default_manifest_path()),
            "role": "control",
            "status": "candidate",
        }
        save_candidate(baseline_candidate)
    return {
        "symbol": normalized_symbol,
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


def _bootstrap_incumbents() -> dict[str, Any]:
    payload = {
        "generated_at": _utc_now(),
        "symbols": {
            symbol: _default_live_symbol_entry(symbol)
            for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS
        },
        "current_canary": None,
    }
    _atomic_write_json(incumbents_path(), payload)
    return payload


def _bootstrap_live_profile() -> dict[str, Any]:
    payload = {
        "generated_at": _utc_now(),
        "symbols": {
            symbol: _default_live_symbol_entry(symbol)
            for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS
        },
    }
    _atomic_write_json(live_profile_path(), payload)
    _LIVE_PROFILE_CACHE.update({"path": str(live_profile_path()), "mtime_ns": None, "payload": None})
    return payload


def _default_status_payload() -> dict[str, Any]:
    incumbents = {
        symbol: {
            "symbol": symbol,
            "active": _default_live_symbol_entry(symbol),
            "previous": None,
            "canary": None,
            "objective": None,
        }
        for symbol in ALLOWED_OPTIONS_PROFIT_SYMBOLS
    }
    return {
        "generated_at": _utc_now(),
        "measurement_gate": {
            "state": "blocked",
            "blockers": ["Options profit cycle has not run yet."],
            "warnings": [],
        },
        "active_incumbents": copy.deepcopy(incumbents),
        "current_canary": None,
        "last_decision": {
            "action": "not_started",
            "summary": "Options profit cycle has not run yet.",
        },
        "blockers": ["Options profit cycle has not run yet."],
    }


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
    return state_dir


def load_incumbents_state() -> dict[str, Any]:
    ensure_options_profit_state()
    payload = _load_json(incumbents_path())
    return payload if payload else _bootstrap_incumbents()


def save_incumbents_state(payload: dict[str, Any]) -> Path:
    ensure_options_profit_state()
    current = dict(payload or {})
    current["generated_at"] = _utc_now()
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
    _LIVE_PROFILE_CACHE.update(
        {
            "path": cache_key,
            "mtime_ns": stat.st_mtime_ns,
            "payload": copy.deepcopy(payload),
        }
    )
    return copy.deepcopy(payload)


def save_live_profile_state(payload: dict[str, Any]) -> Path:
    ensure_options_profit_state()
    current = dict(payload or {})
    current["generated_at"] = _utc_now()
    written = _atomic_write_json(live_profile_path(), current)
    _LIVE_PROFILE_CACHE.update({"path": str(written), "mtime_ns": None, "payload": None})
    return written


def load_profit_status() -> dict[str, Any]:
    ensure_options_profit_state()
    payload = _load_json(status_path())
    if payload:
        return payload
    return _default_status_payload()


def save_profit_status(payload: dict[str, Any]) -> Path:
    ensure_options_profit_state()
    current = dict(payload or {})
    current["generated_at"] = _utc_now()
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


def live_profile_overrides_for_symbol(symbol: str) -> dict[str, Any]:
    payload = load_live_profile_state()
    normalized_symbol = str(symbol or "").strip().upper()
    entry = dict((payload.get("symbols") or {}).get(normalized_symbol) or {})
    return copy.deepcopy(dict(entry.get("overrides") or {}))


def live_profile_entry_for_symbol(symbol: str) -> dict[str, Any]:
    payload = load_live_profile_state()
    normalized_symbol = str(symbol or "").strip().upper()
    return copy.deepcopy(dict((payload.get("symbols") or {}).get(normalized_symbol) or {}))


def merge_live_profile(base_profile: dict[str, Any], symbol: str) -> dict[str, Any]:
    overrides = live_profile_overrides_for_symbol(symbol)
    if not overrides:
        return base_profile
    return _deep_merge(base_profile, overrides)


def default_symbol_manifest(symbol: str) -> dict[str, Any]:
    return _default_live_symbol_entry(symbol)


def load_live_profile() -> dict[str, Any]:
    payload = load_live_profile_state()
    payload.setdefault("version", 1)
    payload["updated_at"] = str(payload.get("generated_at") or _utc_now())
    return payload


def write_live_profile(payload: dict[str, Any]) -> None:
    save_live_profile_state(payload)


def load_incumbents() -> dict[str, Any]:
    payload = load_incumbents_state()
    payload.setdefault("version", 1)
    payload["updated_at"] = str(payload.get("generated_at") or _utc_now())
    symbols = dict(payload.get("symbols") or {})
    for symbol, entry in list(symbols.items()):
        if "active" not in entry:
            symbols[symbol] = {
                "symbol": symbol,
                "active": copy.deepcopy(entry),
                "previous": None,
                "canary": None,
                "objective": None,
            }
    payload["symbols"] = symbols
    return payload


def write_incumbents(payload: dict[str, Any]) -> None:
    save_incumbents_state(payload)


def load_status() -> dict[str, Any]:
    payload = load_profit_status()
    payload.setdefault("version", 1)
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
