from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "forward-tracking" / "regular-options-parked-branch-ledger"
DEFAULT_DOC = ROOT / "docs" / "regular-options-parked-branch-ledger.md"
DEFAULT_DOCS_INDEX = ROOT / "docs" / "index.md"
DEFAULT_DAILY_OPS = ROOT / "scripts" / "run_daily_ops.py"


@dataclass(frozen=True)
class ParkedBranch:
    branch_id: str
    title: str
    status: str
    blocker: str
    revival_condition: str
    script_path: str
    live_doc_path: str
    archived_doc_path: str
    data_artifact_path: str


PARKED_BRANCHES: tuple[ParkedBranch, ...] = (
    ParkedBranch(
        branch_id="quote_surface_opening_range_reversal",
        title="Quote-surface opening-range reversal replay",
        status="parked_blocked_replay",
        blocker="Latest-four strict executable rows remain below the 30-row evidence bar and PF/lower-bound/concentration blockers remain unresolved.",
        revival_condition="Revive only if a new trusted quote/underlying opening-bucket surface changes the strict executable row blocker.",
        script_path="scripts/build_regular_options_quote_surface_opening_range_reversal_replay.py",
        live_doc_path="docs/regular-options-quote-surface-opening-range-reversal-replay.md",
        archived_doc_path="docs/archive/regular-options-quote-surface-opening-range-reversal-replay.md",
        data_artifact_path="data/profitability-lab/regular-options-quote-surface-opening-range-reversal-replay/latest.json",
    ),
    ParkedBranch(
        branch_id="quote_derived_synthetic_forward_surface",
        title="Quote-derived synthetic-forward surface",
        status="parked_missing_surface_coverage",
        blocker="Same-minute call/put pair coverage has zero ready buckets and zero train/latest-month coverage.",
        revival_condition="Revive only if imported or otherwise trusted same-minute call/put quote coverage can satisfy the synthetic-forward coverage gate without synthetic marks as fills.",
        script_path="scripts/build_regular_options_quote_derived_synthetic_forward_surface.py",
        live_doc_path="docs/regular-options-quote-derived-synthetic-forward-surface.md",
        archived_doc_path="docs/archive/regular-options-quote-derived-synthetic-forward-surface.md",
        data_artifact_path="data/profitability-lab/regular-options-quote-derived-synthetic-forward-surface/latest.json",
    ),
    ParkedBranch(
        branch_id="local_quote_structure_capability_matrix",
        title="Local quote-structure capability matrix",
        status="exhausted_under_current_data",
        blocker="No 13-symbol structure is replay-feasible because current local OPRA/NBBO coverage fails full-window, train-month, or latest-four feasibility gates.",
        revival_condition="Revive only after trusted local quote coverage expands enough to satisfy the fixed feasibility gates for at least one structure.",
        script_path="scripts/build_regular_options_local_quote_structure_capability_matrix.py",
        live_doc_path="docs/regular-options-local-quote-structure-capability-matrix.md",
        archived_doc_path="docs/archive/regular-options-local-quote-structure-capability-matrix.md",
        data_artifact_path="data/profitability-lab/regular-options-local-quote-structure-capability-matrix/latest.json",
    ),
    ParkedBranch(
        branch_id="all_local_quote_minute_structure_capability_atlas",
        title="All-local quote-minute structure capability atlas",
        status="exhausted_under_current_data",
        blocker="All selected local quote-minute surfaces fail the 20-train-month feasibility gate despite dense latest-four quote depth.",
        revival_condition="Revive only after new trusted quote history or a separately approved feasibility contract changes the train-month coverage blocker.",
        script_path="scripts/build_regular_options_all_local_quote_minute_structure_capability_atlas.py",
        live_doc_path="docs/regular-options-all-local-quote-minute-structure-capability-atlas.md",
        archived_doc_path="docs/archive/regular-options-all-local-quote-minute-structure-capability-atlas.md",
        data_artifact_path="data/profitability-lab/regular-options-all-local-quote-minute-structure-capability-atlas/latest.json",
    ),
    ParkedBranch(
        branch_id="direct_vix_source_repair_packet",
        title="Direct VIX source-repair packet",
        status="superseded_by_materialized_vix_source",
        blocker="Point-in-time VIX bucket is already ready from the materialized source, so no direct-VIX import approval question is current.",
        revival_condition="Revive only if the materialized VIX source or VIX bucket becomes missing, stale, malformed, or policy-incompatible.",
        script_path="scripts/build_regular_options_direct_vix_source_repair_packet.py",
        live_doc_path="docs/regular-options-direct-vix-source-repair-packet.md",
        archived_doc_path="docs/archive/regular-options-direct-vix-source-repair-packet.md",
        data_artifact_path="data/profitability-lab/regular-options-direct-vix-source-repair-packet/latest.json",
    ),
    ParkedBranch(
        branch_id="chain_native_relaxation_archive",
        title="Chain-native relaxation archive",
        status="archived_disproved_branch",
        blocker="Exact-exit readback disproved all current and relaxed chain-native scenarios with negative net P&L and PF below one.",
        revival_condition="Revive only if a new exact-priced scenario or source surface changes the disproved chain-native relaxation evidence.",
        script_path="scripts/build_regular_options_chain_native_relaxation_archive.py",
        live_doc_path="docs/regular-options-chain-native-relaxation-archive.md",
        archived_doc_path="docs/archive/regular-options-chain-native-relaxation-archive.md",
        data_artifact_path="data/forward-tracking/regular_options_chain_native_relaxation_archive_latest.json",
    ),
    ParkedBranch(
        branch_id="exhausted_contract_archive",
        title="Exhausted contract archive",
        status="archived_exhausted_source_targets",
        blocker="Repeated exact contract/date repair attempts returned no exact OPRA/NBBO rows from the current source.",
        revival_condition="Revive individual targets only if a new trusted source family or provider backfill changes the exact-date no-match result.",
        script_path="scripts/build_regular_options_exhausted_contract_archive.py",
        live_doc_path="docs/regular-options-exhausted-contract-archive.md",
        archived_doc_path="docs/archive/regular-options-exhausted-contract-archive.md",
        data_artifact_path="data/profitability-lab/regular-options-exhausted-contract-archive/latest.json",
    ),
)


def _exists(root: Path, rel_path: str) -> bool:
    return (root / rel_path).exists()


def _read_text_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _contains(index_text: str, rel_path: str) -> bool:
    return f"`{rel_path}`" in index_text or rel_path in index_text


def _daily_ops_step_present(daily_ops_text: str, branch: ParkedBranch) -> bool:
    return Path(branch.script_path).name in daily_ops_text or branch.branch_id in daily_ops_text


def build_ledger(
    *,
    root: Path = ROOT,
    docs_index: Path = DEFAULT_DOCS_INDEX,
    daily_ops: Path = DEFAULT_DAILY_OPS,
    branches: Iterable[ParkedBranch] = PARKED_BRANCHES,
) -> dict:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    index_text = _read_text_if_exists(docs_index)
    daily_ops_text = _read_text_if_exists(daily_ops)

    branch_rows = []
    for branch in branches:
        row = asdict(branch)
        row.update(
            {
                "script_exists": _exists(root, branch.script_path),
                "live_doc_exists": _exists(root, branch.live_doc_path),
                "archived_doc_exists": _exists(root, branch.archived_doc_path),
                "data_artifact_exists": _exists(root, branch.data_artifact_path),
                "referenced_from_live_index": _contains(index_text, branch.live_doc_path),
                "archived_doc_referenced_from_live_index": _contains(index_text, branch.archived_doc_path),
                "daily_ops_step_present": _daily_ops_step_present(daily_ops_text, branch),
                "accepted_profitability": False,
                "historical_rows_are_forward_proof": False,
            }
        )
        branch_rows.append(row)

    return {
        "report_id": "regular_options_parked_branch_ledger",
        "generated_at_utc": generated_at,
        "status": "parked_branch_ledger_ready",
        "accepted_profitability": False,
        "historical_rows_are_forward_proof": False,
        "archival_only": True,
        "data_artifacts_deleted": False,
        "scanner_policy_changed": False,
        "branch_count": len(branch_rows),
        "live_index_reference_count": sum(1 for row in branch_rows if row["referenced_from_live_index"]),
        "archived_doc_live_index_reference_count": sum(
            1 for row in branch_rows if row["archived_doc_referenced_from_live_index"]
        ),
        "daily_ops_step_reference_count": sum(1 for row in branch_rows if row["daily_ops_step_present"]),
        "branches": branch_rows,
    }


def archived_docs_referenced_from_live_index(ledger: dict) -> list[str]:
    return [
        row["archived_doc_path"]
        for row in ledger["branches"]
        if row.get("archived_doc_referenced_from_live_index")
    ]


def render_markdown(ledger: dict) -> str:
    lines = [
        "# Regular Options Parked-Branch Ledger",
        "",
        "This generated ledger consolidates parked, falsified, exhausted, and superseded regular-options branch docs that should not be rerun unless their revival condition changes.",
        "",
        "## Summary",
        "",
        f"- Status: `{ledger['status']}`.",
        f"- Generated at UTC: `{ledger['generated_at_utc']}`.",
        f"- Branches: `{ledger['branch_count']}`.",
        f"- Live index references to parked source docs: `{ledger['live_index_reference_count']}`.",
        f"- Live index references to archived docs: `{ledger['archived_doc_live_index_reference_count']}`.",
        f"- Daily-ops parked step references: `{ledger['daily_ops_step_reference_count']}`.",
        f"- Accepted profitability: `{str(ledger['accepted_profitability']).lower()}`.",
        f"- Historical rows are forward proof: `{str(ledger['historical_rows_are_forward_proof']).lower()}`.",
        f"- Data artifacts deleted: `{str(ledger['data_artifacts_deleted']).lower()}`.",
        "",
        "## Branch Ledger",
        "",
        "| Branch | Title | Status | Blocker | Revival Condition | Archived Doc | Script | Data Artifact |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in ledger["branches"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{row['branch_id']}`",
                    row["title"],
                    f"`{row['status']}`",
                    row["blocker"],
                    row["revival_condition"],
                    f"`{row['archived_doc_path']}`",
                    f"`{row['script_path']}`",
                    f"`{row['data_artifact_path']}`",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Reconstruction Contract",
            "",
            "- Archived docs preserve generated report content under `docs/archive/`.",
            "- Scripts and data artifacts remain in place for reconstruction or revival-condition review.",
            "- These branches are not accepted profitability, not forward proof, and not production scanner evidence.",
            "- Do not rerun a parked branch unless its ledger revival condition is met by new trusted data or a separate approved research contract.",
            "",
            "## Boundary",
            "",
            "This ledger is archival documentation only. It does not import quotes, mutate `options_history.db`, mutate evidence stores, consume protected holdout, change scanner policy, change stops or sizing, lower proof bars, enable live validation, enable auto-track, prepare broker orders, or promote any lane.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_outputs(ledger: dict, *, output_dir: Path = DEFAULT_OUTPUT_DIR, docs_report: Path = DEFAULT_DOC) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    docs_report.parent.mkdir(parents=True, exist_ok=True)
    latest_json = output_dir / "latest.json"
    latest_md = output_dir / "latest.md"
    timestamp = ledger["generated_at_utc"].replace(":", "").replace("-", "")
    timestamped_json = output_dir / f"{timestamp}.json"

    payload = json.dumps(ledger, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(ledger)
    latest_json.write_text(payload, encoding="utf-8")
    timestamped_json.write_text(payload, encoding="utf-8")
    latest_md.write_text(markdown, encoding="utf-8")
    docs_report.write_text(markdown, encoding="utf-8")
    return {
        "latest_json": str(latest_json.relative_to(ROOT)),
        "timestamped_json": str(timestamped_json.relative_to(ROOT)),
        "latest_markdown": str(latest_md.relative_to(ROOT)),
        "docs_report": str(docs_report.relative_to(ROOT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="Print JSON payload.")
    parser.add_argument("--check-live-index", action="store_true", help="Fail if archived docs are referenced from docs/index.md.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--docs-report", type=Path, default=DEFAULT_DOC)
    args = parser.parse_args()

    ledger = build_ledger()
    artifacts = write_outputs(ledger, output_dir=args.output_dir, docs_report=args.docs_report)
    ledger["artifacts"] = artifacts

    offenders = archived_docs_referenced_from_live_index(ledger)
    if args.json:
        print(json.dumps(ledger, indent=2, sort_keys=True))
    else:
        print(render_markdown(ledger))

    if args.check_live_index and offenders:
        print(
            "Archived docs are still referenced from live docs/index.md: " + ", ".join(offenders),
            flush=True,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
