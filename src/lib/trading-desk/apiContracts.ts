import type { TradingDeskRouteContractId } from "@/lib/trading-desk/storeOwnership";
import type { ScanPick, SuggestedTrade, TrackedPosition } from "@/lib/types";

export type TradingDeskListStatus = "open" | "closed" | "all";

export type TradingDeskListWindow = {
  limit?: number | string | null;
  offset?: number | string | null;
  compact?: number | string | null;
};

export type TradingDeskPage = {
  limit: number;
  offset: number;
  returned: number;
};

export type TradingDeskUnavailableResponse = {
  error: string;
  position?: never;
  positions?: never;
  trade?: never;
  trades?: never;
  duplicate?: never;
  position_event_persistence?: never;
};

export type TradingDeskPnlSummary = {
  count: number;
  priced_count: number;
  wins: number;
  losses: number;
  flat: number;
  net_pnl_usd: number | null;
  avg_pnl_pct: number | null;
};

export type TradingDeskProofSummary = {
  tracked: TradingDeskPnlSummary;
  proof: TradingDeskPnlSummary;
};

export type TradingDeskGroupedSummary = {
  open: TradingDeskProofSummary;
  closed: TradingDeskProofSummary;
  all: TradingDeskProofSummary;
};

export type TrackedPositionsListResponse =
  | TradingDeskUnavailableResponse
  | {
      positions: TrackedPosition[];
      page?: TradingDeskPage;
    };

export type GroupedTrackedPositionsResponse =
  | TradingDeskUnavailableResponse
  | {
      open: TrackedPosition[];
      closed: TrackedPosition[];
      summary: TradingDeskGroupedSummary;
      page?: TradingDeskPage;
    };

export type SuggestedTradesListResponse =
  | TradingDeskUnavailableResponse
  | {
      trades: SuggestedTrade[];
      page?: TradingDeskPage;
    };

export type GroupedSuggestedTradesResponse =
  | TradingDeskUnavailableResponse
  | {
      open: SuggestedTrade[];
      closed: SuggestedTrade[];
      summary: TradingDeskGroupedSummary;
      page?: TradingDeskPage;
    };

export type PositionEventPersistence = {
  status?: "recorded" | "failed" | "skipped" | string;
  operation?: string;
  position_ids?: number[];
  error?: string | null;
  reason?: string | null;
  ledger_session_id?: number | string | null;
  ledger_event_key?: string | null;
  skipped?: boolean;
  skip_reason?: string | null;
  [key: string]: unknown;
};

export type CreateTrackedPositionRequest = {
  scan_pick: ScanPick;
  fill_price: number;
  contracts: number;
  filled_at?: string | null;
  notes?: string | null;
  creation_mode?: "scanner" | "manual_paper" | "manual_broker" | string | null;
};

export type CreateSuggestedTradeRequest = {
  scan_pick: ScanPick;
  fill_price: number;
  contracts?: number | null;
  filled_at?: string | null;
  notes?: string | null;
  creation_mode?: "scanner" | "manual_paper" | "manual_broker" | string | null;
};

export type ReviewTrackedPositionsRequest = {
  position_ids?: number[] | null;
};

export type ReviewSuggestedTradesRequest = {
  position_ids?: number[] | null;
};

export type CloseTrackedPositionRequest = {
  exit_price: number;
  closed_at?: string | null;
  notes?: string | null;
};

export type CloseSuggestedTradeRequest = {
  exit_price: number;
  closed_at?: string | null;
  notes?: string | null;
};

export type CreateTrackedPositionResponse =
  | TradingDeskUnavailableResponse
  | {
      position: TrackedPosition;
      duplicate?: boolean;
      position_event_persistence?: PositionEventPersistence;
      trade?: never;
    };

export type ReviewTrackedPositionsResponse =
  | TradingDeskUnavailableResponse
  | {
      positions: TrackedPosition[];
      position_event_persistence?: PositionEventPersistence;
      trades?: never;
    };

export type CloseTrackedPositionResponse =
  | TradingDeskUnavailableResponse
  | {
      position: TrackedPosition;
      position_event_persistence?: PositionEventPersistence;
      trade?: never;
    };

export type CreateSuggestedTradeResponse =
  | TradingDeskUnavailableResponse
  | {
      trade: SuggestedTrade;
      duplicate?: boolean;
      position_event_persistence?: never;
      position?: never;
    };

export type ReviewSuggestedTradesResponse =
  | TradingDeskUnavailableResponse
  | {
      trades: SuggestedTrade[];
      position_event_persistence?: never;
      positions?: never;
    };

export type CloseSuggestedTradeResponse =
  | TradingDeskUnavailableResponse
  | {
      trade: SuggestedTrade;
      position_event_persistence?: never;
      position?: never;
    };

export type TradingDeskBackendResponseWithTiming<T> = {
  body: T;
  headers: Record<string, string>;
};

export type TradingDeskApiContract = {
  id: TradingDeskRouteContractId;
  request: string | null;
  response: string;
  envelope: "position" | "positions" | "trade" | "trades";
  includesPositionEventPersistence: boolean;
};

export const TRADING_DESK_API_CONTRACTS: TradingDeskApiContract[] = [
  {
    id: "tracked_positions_read",
    request: "TradingDeskListWindow",
    response: "TrackedPositionsListResponse | GroupedTrackedPositionsResponse",
    envelope: "positions",
    includesPositionEventPersistence: false,
  },
  {
    id: "tracked_positions_create",
    request: "CreateTrackedPositionRequest",
    response: "CreateTrackedPositionResponse",
    envelope: "position",
    includesPositionEventPersistence: true,
  },
  {
    id: "tracked_positions_review",
    request: "ReviewTrackedPositionsRequest",
    response: "ReviewTrackedPositionsResponse",
    envelope: "positions",
    includesPositionEventPersistence: true,
  },
  {
    id: "tracked_positions_close",
    request: "CloseTrackedPositionRequest",
    response: "CloseTrackedPositionResponse",
    envelope: "position",
    includesPositionEventPersistence: true,
  },
  {
    id: "suggested_trades_read",
    request: "TradingDeskListWindow",
    response: "SuggestedTradesListResponse | GroupedSuggestedTradesResponse",
    envelope: "trades",
    includesPositionEventPersistence: false,
  },
  {
    id: "suggested_trades_create",
    request: "CreateSuggestedTradeRequest",
    response: "CreateSuggestedTradeResponse",
    envelope: "trade",
    includesPositionEventPersistence: false,
  },
  {
    id: "suggested_trades_review",
    request: "ReviewSuggestedTradesRequest",
    response: "ReviewSuggestedTradesResponse",
    envelope: "trades",
    includesPositionEventPersistence: false,
  },
  {
    id: "suggested_trades_close",
    request: "CloseSuggestedTradeRequest",
    response: "CloseSuggestedTradeResponse",
    envelope: "trade",
    includesPositionEventPersistence: false,
  },
];
