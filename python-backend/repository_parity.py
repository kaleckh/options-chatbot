from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from repository_contracts import (
    TRACKED_POSITIONS_OPTIONAL_METHODS,
    TRACKED_POSITIONS_REQUIRED_METHODS,
    TRACKING_REPOSITORY_REQUIRED_METHODS,
)
from repository_migrations import (
    POSTGRES_TRACKED_POSITIONS_STORE_ID,
    SQLITE_SUGGESTED_TRADES_STORE_ID,
)


TRACKED_POSITION_RECORD_CLASS = "tracked_position"
SUGGESTED_TRADE_RECORD_CLASS = "suggested_trade"

COMMON_LIFECYCLES = ("read", "create", "review", "close")

COMMON_REPOSITORY_METHODS = TRACKING_REPOSITORY_REQUIRED_METHODS
TRACKED_ONLY_REPOSITORY_METHODS = tuple(
    method
    for method in TRACKED_POSITIONS_REQUIRED_METHODS
    if method not in TRACKING_REPOSITORY_REQUIRED_METHODS
) + TRACKED_POSITIONS_OPTIONAL_METHODS

COMMON_POSITION_TABLE_COLUMNS = (
    "id",
    "status",
    "ticker",
    "direction",
    "contract_symbol",
    "strike",
    "expiry",
    "asset_class",
    "contracts",
    "entry_option_price",
    "entry_execution_price",
    "entry_execution_basis",
    "entry_fee_total_usd",
    "entry_underlying_price",
    "filled_at",
    "stop_loss_pct",
    "profit_target_pct",
    "time_exit_day",
    "peak_pnl_pct",
    "last_option_price",
    "last_pnl_pct",
    "last_recommendation",
    "last_recommendation_reason",
    "last_reviewed_at",
    "source_pick_snapshot",
    "notes",
    "closed_at",
    "exit_option_price",
    "exit_execution_price",
    "exit_execution_basis",
    "exit_reason",
    "gross_pnl_pct",
    "net_pnl_pct",
    "gross_pnl_usd",
    "net_pnl_usd",
    "fee_total_usd",
    "created_at",
    "updated_at",
)

COMMON_POSITION_ROW_FIELDS = COMMON_POSITION_TABLE_COLUMNS + ("latest_review",)

COMMON_LATEST_REVIEW_FIELDS = (
    "id",
    "reviewed_at",
    "pricing_source",
    "current_option_price",
    "current_pnl_pct",
    "gross_pnl_pct",
    "net_pnl_pct",
    "gross_pnl_usd",
    "net_pnl_usd",
    "entry_execution_price",
    "exit_execution_price",
    "entry_execution_basis",
    "exit_execution_basis",
    "fee_total_usd",
    "recommendation",
    "reason",
    "warnings",
    "metrics_snapshot",
)

COMMON_REVIEW_TABLE_COLUMNS = (
    "id",
    "position_id",
    "reviewed_at",
    "pricing_source",
    "current_option_price",
    "current_pnl_pct",
    "gross_pnl_pct",
    "net_pnl_pct",
    "gross_pnl_usd",
    "net_pnl_usd",
    "entry_execution_price",
    "exit_execution_price",
    "entry_execution_basis",
    "exit_execution_basis",
    "fee_total_usd",
    "recommendation",
    "reason",
    "warnings",
    "metrics_snapshot",
    "created_at",
)

TRACKED_ONLY_TOP_LEVEL_FIELDS = (
    "source_scan_session_id",
    "source_scan_event_key",
    "source_scan_run_id",
    "source_scan_recorded_at_utc",
    "proof_eligible",
    "proof_ineligibility_reason",
    "proof_class",
    "proof_class_reason",
)

SUGGESTED_TRADE_FORBIDDEN_TOP_LEVEL_FIELDS = TRACKED_ONLY_TOP_LEVEL_FIELDS
TRACKED_ONLY_RESPONSE_FIELDS = ("position_event_persistence",)


ParityCategory = Literal[
    "shared_workflow",
    "shared_row_shape",
    "shared_review_shape",
    "intentional_difference",
    "tracked_only",
    "suggested_trade_boundary",
]


@dataclass(frozen=True)
class TradingDeskRouteParity:
    lifecycle: str
    tracked_method: str
    tracked_route: str
    tracked_response_key: str
    suggested_method: str
    suggested_route: str
    suggested_response_key: str
    shared_contract: str
    intentional_difference: str


@dataclass(frozen=True)
class TradingDeskRecordParity:
    parity_id: str
    category: ParityCategory
    tracked: str
    suggested: str
    rule: str
    notes: str


ROUTE_PARITY: tuple[TradingDeskRouteParity, ...] = (
    TradingDeskRouteParity(
        lifecycle="read",
        tracked_method="GET",
        tracked_route="/api/positions",
        tracked_response_key="positions",
        suggested_method="GET",
        suggested_route="/api/suggested-trades",
        suggested_response_key="trades",
        shared_contract="status filtering, optional paging, grouped all-status reads, and lifecycle headers",
        intentional_difference="Tracked readbacks can feed proof/profit summaries; suggested reads are paper ideas only.",
    ),
    TradingDeskRouteParity(
        lifecycle="create",
        tracked_method="POST",
        tracked_route="/api/positions",
        tracked_response_key="position",
        suggested_method="POST",
        suggested_route="/api/suggested-trades",
        suggested_response_key="trade",
        shared_contract="manual/scanner-origin payload building and scanner creation-safety validation",
        intentional_difference="Tracked creates persist proof/source-scan fields and lifecycle event status; suggested creates do not.",
    ),
    TradingDeskRouteParity(
        lifecycle="review",
        tracked_method="POST",
        tracked_route="/api/positions/review",
        tracked_response_key="positions",
        suggested_method="POST",
        suggested_route="/api/suggested-trades/review",
        suggested_response_key="trades",
        shared_contract="positions_service.review_open_positions computes review payloads for open rows",
        intentional_difference="Tracked reviews report position_event_persistence; suggested reviews update paper ideas only.",
    ),
    TradingDeskRouteParity(
        lifecycle="close",
        tracked_method="POST",
        tracked_route="/api/positions/{id}/close",
        tracked_response_key="position",
        suggested_method="POST",
        suggested_route="/api/suggested-trades/{id}/close",
        suggested_response_key="trade",
        shared_contract="close rows store exit price, close time, P&L snapshot, and synthetic SELL latest_review",
        intentional_difference="Suggested close reason is manual_hypothetical_close and never broker/live proof.",
    ),
)

RECORD_PARITY_BOUNDARIES: tuple[TradingDeskRecordParity, ...] = (
    TradingDeskRecordParity(
        parity_id="shared_lifecycle",
        category="shared_workflow",
        tracked="read/create/review/close tracked-position workflow",
        suggested="read/create/review/close suggested-trade workflow",
        rule="Keep lifecycle vocabulary parallel across the two route families.",
        notes="The shared vocabulary helps UI and agents compare rows without merging stores.",
    ),
    TradingDeskRecordParity(
        parity_id="shared_repository_surface",
        category="shared_workflow",
        tracked=", ".join(COMMON_REPOSITORY_METHODS),
        suggested=", ".join(COMMON_REPOSITORY_METHODS),
        rule="Both stores satisfy the common TradingDeskPositionRepository method surface.",
        notes="Tracked repositories have extra capabilities that suggested trades must not be forced to implement.",
    ),
    TradingDeskRecordParity(
        parity_id="shared_position_row_shape",
        category="shared_row_shape",
        tracked="tracked position normalized row",
        suggested="suggested trade normalized row",
        rule="Common display and review fields stay available under the same names.",
        notes="Frontend may currently use SuggestedTrade = TrackedPosition as a display-row alias only.",
    ),
    TradingDeskRecordParity(
        parity_id="shared_latest_review_shape",
        category="shared_review_shape",
        tracked="position_reviews latest_review",
        suggested="suggested_trade_reviews latest_review",
        rule="Latest review keys stay parallel for review and close displays.",
        notes="Repositories normalize warning and metrics snapshots before returning latest_review.",
    ),
    TradingDeskRecordParity(
        parity_id="store_and_record_class_split",
        category="intentional_difference",
        tracked=f"{POSTGRES_TRACKED_POSITIONS_STORE_ID} / {TRACKED_POSITION_RECORD_CLASS}",
        suggested=f"{SQLITE_SUGGESTED_TRADES_STORE_ID} / {SUGGESTED_TRADE_RECORD_CLASS}",
        rule="Never collapse suggested trades into tracked positions or tracked positions into SQLite fallback state.",
        notes="Route headers and docs must keep the store and record class distinct.",
    ),
    TradingDeskRecordParity(
        parity_id="response_envelope_split",
        category="intentional_difference",
        tracked="position / positions",
        suggested="trade / trades",
        rule="Public response envelopes remain intentionally different.",
        notes="Envelope names are a semantic cue that suggested trades are paper ideas, not tracked-position rows.",
    ),
    TradingDeskRecordParity(
        parity_id="tracked_only_proof_fields",
        category="tracked_only",
        tracked=", ".join(TRACKED_ONLY_TOP_LEVEL_FIELDS),
        suggested="absent from suggested_trades top-level rows",
        rule="Proof/source-scan top-level fields stay tracked-position-only.",
        notes="Suggested source snapshots can contain scanner context, but suggested rows are not production proof rows.",
    ),
    TradingDeskRecordParity(
        parity_id="tracked_only_lifecycle_event_persistence",
        category="tracked_only",
        tracked="position_event_persistence",
        suggested="absent from suggested create/review/close responses",
        rule="Forward-evidence lifecycle event persistence remains tracked-position-only.",
        notes="Suggested-trade mutations are local paper workflow state and do not write lifecycle proof events.",
    ),
    TradingDeskRecordParity(
        parity_id="tracked_only_profit_readbacks",
        category="tracked_only",
        tracked="profit_status_snapshot, list_compact_positions, get_realized_pnl_since",
        suggested="not required and not production proof/profit input",
        rule="Suggested trades do not feed proof-summary or options-profit production truth.",
        notes="Open paper ideas can be reviewed for operator workflow, not proof-lane claims.",
    ),
    TradingDeskRecordParity(
        parity_id="suggested_trade_paper_boundary",
        category="suggested_trade_boundary",
        tracked="production tracked positions and historical learning rows",
        suggested="local paper/hypothetical suggested trades",
        rule="Suggested trades are not broker fills, not production proof, and not a tracked-position fallback.",
        notes="This boundary survives even when scanner-origin safety gates are shared.",
    ),
)


def route_parity_manifest() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "lifecycle": route.lifecycle,
            "tracked_method": route.tracked_method,
            "tracked_route": route.tracked_route,
            "tracked_store_id": POSTGRES_TRACKED_POSITIONS_STORE_ID,
            "tracked_record_class": TRACKED_POSITION_RECORD_CLASS,
            "tracked_response_key": route.tracked_response_key,
            "suggested_method": route.suggested_method,
            "suggested_route": route.suggested_route,
            "suggested_store_id": SQLITE_SUGGESTED_TRADES_STORE_ID,
            "suggested_record_class": SUGGESTED_TRADE_RECORD_CLASS,
            "suggested_response_key": route.suggested_response_key,
            "shared_contract": route.shared_contract,
            "intentional_difference": route.intentional_difference,
        }
        for route in ROUTE_PARITY
    )


def record_parity_manifest() -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "parity_id": boundary.parity_id,
            "category": boundary.category,
            "tracked": boundary.tracked,
            "suggested": boundary.suggested,
            "rule": boundary.rule,
            "notes": boundary.notes,
        }
        for boundary in RECORD_PARITY_BOUNDARIES
    )


def boundaries_by_category(category: ParityCategory) -> tuple[TradingDeskRecordParity, ...]:
    return tuple(boundary for boundary in RECORD_PARITY_BOUNDARIES if boundary.category == category)
