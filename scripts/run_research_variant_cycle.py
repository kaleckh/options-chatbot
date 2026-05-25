from __future__ import annotations

import argparse
import copy
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import options_chatbot as oc
import scripts.autoresearch_cycle as cycle
import wfo_optimizer as wfo
from scripts.autoresearch_governance import build_experiment_fingerprint


class VariantConfigError(RuntimeError):
    """Raised when a research variant config cannot be applied safely."""


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf8"))
    except FileNotFoundError as exc:
        raise VariantConfigError(f"Variant config does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise VariantConfigError(f"Variant config is not valid JSON: {path}") from exc


def _resolve_input_path(root_dir: Path, value: str) -> Path:
    raw = Path(value)
    return raw if raw.is_absolute() else root_dir / raw


def _merge_profile_overrides(
    base_profiles: dict[str, dict[str, Any]],
    overrides: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    merged = copy.deepcopy(base_profiles)
    for profile_name, profile_overrides in dict(overrides or {}).items():
        key = str(profile_name or "").strip().lower()
        if key not in merged:
            raise VariantConfigError(f"Unknown strategy profile in variant config: {profile_name}")
        if not isinstance(profile_overrides, dict):
            raise VariantConfigError(f"Profile override for {profile_name} must be an object.")
        for section_name, section_value in profile_overrides.items():
            if isinstance(section_value, dict) and isinstance(merged[key].get(section_name), dict):
                merged[key][section_name].update(copy.deepcopy(section_value))
            else:
                merged[key][section_name] = copy.deepcopy(section_value)
    return merged


def _merge_ai_commodity_option_filter_overrides(
    base_filters: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    merged = copy.deepcopy(base_filters)
    if not overrides:
        return merged
    if not isinstance(overrides, dict):
        raise VariantConfigError("ai_commodity_option_filter_overrides must be an object when provided.")
    unknown_keys = sorted(str(key) for key in overrides if key not in merged)
    if unknown_keys:
        raise VariantConfigError(
            "Unknown AI commodity option filter override(s): " + ", ".join(unknown_keys)
        )
    for key, value in overrides.items():
        try:
            merged[str(key)] = float(value)
        except (TypeError, ValueError) as exc:
            raise VariantConfigError(f"AI commodity option filter override for {key} must be numeric.") from exc
    return merged


def _merge_playbook_overrides(
    base_playbooks: dict[str, dict[str, Any]],
    overrides: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    merged = copy.deepcopy(base_playbooks)
    if not overrides:
        return merged
    if not isinstance(overrides, dict):
        raise VariantConfigError("playbook_overrides must be an object when provided.")
    for playbook_name, playbook_overrides in overrides.items():
        key = str(playbook_name or "").strip().lower()
        if key not in merged:
            raise VariantConfigError(f"Unknown replay playbook in variant config: {playbook_name}")
        if not isinstance(playbook_overrides, dict):
            raise VariantConfigError(f"Playbook override for {playbook_name} must be an object.")
        merged[key].update(copy.deepcopy(playbook_overrides))
    return merged


def _replace_profiles(target: Any, profiles: dict[str, dict[str, Any]]) -> None:
    target.STRATEGY_PROFILES.clear()
    target.STRATEGY_PROFILES.update(copy.deepcopy(profiles))
    target.STRATEGY_PROFILE = target.STRATEGY_PROFILES["equity"]


@contextmanager
def _temporary_variant_context(config: dict[str, Any]) -> Iterator[None]:
    previous_oc_profiles = copy.deepcopy(oc.STRATEGY_PROFILES)
    previous_wfo_profiles = copy.deepcopy(wfo.STRATEGY_PROFILES)
    previous_imported_universe = tuple(wfo.IMPORTED_VALIDATION_UNIVERSE)
    previous_ai_commodity_option_filters = copy.deepcopy(oc.AI_COMMODITY_OPTION_FILTERS)
    previous_replay_playbooks = copy.deepcopy(wfo.REPLAY_PLAYBOOKS)

    try:
        merged_profiles = _merge_profile_overrides(
            previous_oc_profiles,
            dict(config.get("profile_overrides") or {}),
        )
        _replace_profiles(oc, merged_profiles)
        _replace_profiles(wfo, merged_profiles)

        oc.AI_COMMODITY_OPTION_FILTERS.clear()
        oc.AI_COMMODITY_OPTION_FILTERS.update(
            _merge_ai_commodity_option_filter_overrides(
                previous_ai_commodity_option_filters,
                config.get("ai_commodity_option_filter_overrides") or {},
            )
        )
        wfo.REPLAY_PLAYBOOKS.clear()
        wfo.REPLAY_PLAYBOOKS.update(
            _merge_playbook_overrides(
                previous_replay_playbooks,
                config.get("playbook_overrides") or {},
            )
        )

        imported_validation_universe = config.get("imported_validation_universe")
        if imported_validation_universe is not None:
            if not isinstance(imported_validation_universe, list) or not imported_validation_universe:
                raise VariantConfigError("imported_validation_universe must be a non-empty list when provided.")
            wfo.IMPORTED_VALIDATION_UNIVERSE = tuple(
                str(symbol).strip().upper()
                for symbol in imported_validation_universe
                if str(symbol).strip()
            )
        yield
    finally:
        oc.STRATEGY_PROFILES.clear()
        oc.STRATEGY_PROFILES.update(previous_oc_profiles)
        oc.STRATEGY_PROFILE = oc.STRATEGY_PROFILES["equity"]

        wfo.STRATEGY_PROFILES.clear()
        wfo.STRATEGY_PROFILES.update(previous_wfo_profiles)
        wfo.STRATEGY_PROFILE = wfo.STRATEGY_PROFILES["equity"]
        wfo.IMPORTED_VALIDATION_UNIVERSE = previous_imported_universe
        oc.AI_COMMODITY_OPTION_FILTERS.clear()
        oc.AI_COMMODITY_OPTION_FILTERS.update(previous_ai_commodity_option_filters)
        wfo.REPLAY_PLAYBOOKS.clear()
        wfo.REPLAY_PLAYBOOKS.update(previous_replay_playbooks)


def _find_new_run_dir(root_dir: Path, before: set[Path]) -> Path | None:
    run_root = root_dir / "research_runs"
    if not run_root.exists():
        return None
    candidates = {path for path in run_root.iterdir() if path.is_dir()}
    new_dirs = sorted(candidates - before, key=lambda path: path.name)
    return new_dirs[-1] if new_dirs else None


def main(argv: list[str] | None = None, *, root_dir: Path | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one autoresearch cycle with temporary research-only strategy overrides."
    )
    parser.add_argument(
        "--variant-config",
        required=True,
        help="JSON file describing temporary strategy overrides for this run.",
    )
    parser.add_argument(
        "cycle_args",
        nargs=argparse.REMAINDER,
        help="Arguments forwarded to scripts/autoresearch_cycle.py after an optional -- separator.",
    )
    args = parser.parse_args(argv)

    root = Path(root_dir) if root_dir is not None else ROOT
    variant_path = _resolve_input_path(root, args.variant_config)
    config = _read_json(variant_path)
    forwarded = list(args.cycle_args)
    if forwarded and forwarded[0] == "--":
        forwarded = forwarded[1:]
    if not forwarded:
        raise VariantConfigError("No autoresearch cycle arguments were provided.")

    run_root = root / "research_runs"
    before_dirs = {path for path in run_root.iterdir() if path.is_dir()} if run_root.exists() else set()

    with _temporary_variant_context(config):
        exit_code = cycle.main(forwarded, root_dir=root)

    new_run_dir = _find_new_run_dir(root, before_dirs)
    if new_run_dir is not None:
        (new_run_dir / "variant_config.json").write_text(
            json.dumps(config, indent=2),
            encoding="utf8",
        )
        manifest_path = new_run_dir / "manifest.json"
        if manifest_path.exists():
            payload = json.loads(manifest_path.read_text(encoding="utf8"))
            effective_override_diff = dict(config.get("profile_overrides") or {}).get("equity") or {}
            ai_commodity_option_filter_overrides = dict(
                config.get("ai_commodity_option_filter_overrides") or {}
            )
            playbook_overrides = dict(config.get("playbook_overrides") or {})
            payload["effective_override_diff"] = effective_override_diff
            payload["ai_commodity_option_filter_overrides"] = ai_commodity_option_filter_overrides
            payload["playbook_overrides"] = playbook_overrides
            fingerprint = dict(payload.get("experiment_fingerprint") or {})
            imported_store_metadata = dict((fingerprint.get("imported_store_metadata") or {}))
            fingerprint_overrides = dict(effective_override_diff)
            if ai_commodity_option_filter_overrides:
                fingerprint_overrides["ai_commodity_option_filter_overrides"] = ai_commodity_option_filter_overrides
            if playbook_overrides:
                fingerprint_overrides["playbook_overrides"] = playbook_overrides
            payload["experiment_fingerprint"] = build_experiment_fingerprint(
                phase_id=payload.get("phase_id"),
                mode=payload.get("mode") or "search",
                cohort_id=payload.get("cohort_id"),
                batch_id=payload.get("batch_id"),
                playbooks=list(payload.get("playbooks") or []),
                truth_lane=payload.get("truth_lane") or "synthetic_research",
                window_mode=payload.get("window_mode") or "full",
                watchlist_symbols=list(((payload.get("watchlist_manifest") or {}).get("symbols") or [])),
                baseline_id=(payload.get("baseline_compatibility") or {}).get("required_baseline_id"),
                compare_to=payload.get("compare_to"),
                effective_override_diff=fingerprint_overrides,
                imported_store_metadata=imported_store_metadata,
            )
            manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf8")

    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
