export const TRADING_DESK_STORE_HEADER = "x-trading-desk-store";
export const TRADING_DESK_LIFECYCLE_HEADER = "x-trading-desk-lifecycle";
export const TRADING_DESK_RECORD_CLASS_HEADER = "x-trading-desk-record-class";

export type TradingDeskStoreId =
  | "postgres_tracked_positions"
  | "sqlite_suggested_trades";

export type TradingDeskLifecycle =
  | "read"
  | "create"
  | "review"
  | "close";

export type TradingDeskRecordClass =
  | "tracked_position"
  | "suggested_trade";

export const TRADING_DESK_ROUTE_CONTRACT_IDS = [
  "tracked_positions_read",
  "tracked_positions_create",
  "tracked_positions_review",
  "tracked_positions_close",
  "suggested_trades_read",
  "suggested_trades_create",
  "suggested_trades_review",
  "suggested_trades_close",
] as const;

export type TradingDeskRouteContractId = (typeof TRADING_DESK_ROUTE_CONTRACT_IDS)[number];

export type TradingDeskRouteContract = {
  id: TradingDeskRouteContractId;
  method: "GET" | "POST";
  route: string;
  store: TradingDeskStoreId;
  lifecycle: TradingDeskLifecycle;
  recordClass: TradingDeskRecordClass;
  owner: string;
};

export const TRADING_DESK_ROUTE_CONTRACTS: Record<
  TradingDeskRouteContractId,
  TradingDeskRouteContract
> = {
  tracked_positions_read: {
    id: "tracked_positions_read",
    method: "GET",
    route: "/api/positions",
    store: "postgres_tracked_positions",
    lifecycle: "read",
    recordClass: "tracked_position",
    owner: "python-backend/positions_repository.py via DATABASE_URL",
  },
  tracked_positions_create: {
    id: "tracked_positions_create",
    method: "POST",
    route: "/api/positions",
    store: "postgres_tracked_positions",
    lifecycle: "create",
    recordClass: "tracked_position",
    owner: "python-backend/positions_repository.py via DATABASE_URL",
  },
  tracked_positions_review: {
    id: "tracked_positions_review",
    method: "POST",
    route: "/api/positions/review",
    store: "postgres_tracked_positions",
    lifecycle: "review",
    recordClass: "tracked_position",
    owner: "python-backend/positions_service.py and positions_repository.py via DATABASE_URL",
  },
  tracked_positions_close: {
    id: "tracked_positions_close",
    method: "POST",
    route: "/api/positions/{id}/close",
    store: "postgres_tracked_positions",
    lifecycle: "close",
    recordClass: "tracked_position",
    owner: "python-backend/positions_repository.py via DATABASE_URL",
  },
  suggested_trades_read: {
    id: "suggested_trades_read",
    method: "GET",
    route: "/api/suggested-trades",
    store: "sqlite_suggested_trades",
    lifecycle: "read",
    recordClass: "suggested_trade",
    owner: "python-backend/suggested_trades_repository.py via chat_history.db",
  },
  suggested_trades_create: {
    id: "suggested_trades_create",
    method: "POST",
    route: "/api/suggested-trades",
    store: "sqlite_suggested_trades",
    lifecycle: "create",
    recordClass: "suggested_trade",
    owner: "python-backend/suggested_trades_repository.py via chat_history.db",
  },
  suggested_trades_review: {
    id: "suggested_trades_review",
    method: "POST",
    route: "/api/suggested-trades/review",
    store: "sqlite_suggested_trades",
    lifecycle: "review",
    recordClass: "suggested_trade",
    owner: "python-backend/positions_service.py and suggested_trades_repository.py via chat_history.db",
  },
  suggested_trades_close: {
    id: "suggested_trades_close",
    method: "POST",
    route: "/api/suggested-trades/{id}/close",
    store: "sqlite_suggested_trades",
    lifecycle: "close",
    recordClass: "suggested_trade",
    owner: "python-backend/suggested_trades_repository.py via chat_history.db",
  },
};

export function getTradingDeskRouteContract(
  id: TradingDeskRouteContractId
): TradingDeskRouteContract {
  return TRADING_DESK_ROUTE_CONTRACTS[id];
}

export function tradingDeskStoreHeaders(id: TradingDeskRouteContractId): HeadersInit {
  const contract = getTradingDeskRouteContract(id);
  return {
    [TRADING_DESK_STORE_HEADER]: contract.store,
    [TRADING_DESK_LIFECYCLE_HEADER]: contract.lifecycle,
    [TRADING_DESK_RECORD_CLASS_HEADER]: contract.recordClass,
  };
}
