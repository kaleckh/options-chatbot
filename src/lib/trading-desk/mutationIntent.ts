export const TRADING_DESK_MUTATION_HEADER = "x-trading-desk-mutation";

export type TradingDeskMutationIntent =
  | "create_tracked_position"
  | "review_tracked_positions"
  | "close_tracked_position"
  | "create_suggested_trade"
  | "review_suggested_trades"
  | "close_suggested_trade";

export function tradingDeskMutationHeaders(intent: TradingDeskMutationIntent): HeadersInit {
  return {
    "Content-Type": "application/json",
    [TRADING_DESK_MUTATION_HEADER]: intent,
  };
}
