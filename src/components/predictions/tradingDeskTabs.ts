export const TRADING_DESK_CONTENT_TAB_IDS = [
  "positions",
  "tracked-stocks",
  "scanner",
  "suggestions",
  "pending",
  "graded",
  "breakdown",
  "sim",
  "sectors",
] as const;

export type TradingDeskSubTabId = (typeof TRADING_DESK_CONTENT_TAB_IDS)[number];

export const TRADING_DESK_VISIBLE_TAB_IDS = [
  "positions",
  "closed-trades",
  "tracked-stocks",
  "scanner",
  "suggestions",
  "pending",
  "graded",
  "breakdown",
  "sim",
  "sectors",
] as const;

export type TradingDeskVisibleTabId = (typeof TRADING_DESK_VISIBLE_TAB_IDS)[number];
export type TradingDeskPositionsView = "open" | "closed";

export const LEGACY_PREDICTION_TAB_IDS = [
  "pending",
  "graded",
  "breakdown",
  "sim",
  "sectors",
] as const satisfies readonly TradingDeskSubTabId[];

const LEGACY_PREDICTION_TAB_SET = new Set<TradingDeskSubTabId>(LEGACY_PREDICTION_TAB_IDS);

export function isLegacyPredictionTabId(
  tabId: TradingDeskSubTabId
): tabId is (typeof LEGACY_PREDICTION_TAB_IDS)[number] {
  return LEGACY_PREDICTION_TAB_SET.has(tabId);
}

export function toTradingDeskVisibleTabId(
  activeSubTab: TradingDeskSubTabId,
  positionsView: TradingDeskPositionsView
): TradingDeskVisibleTabId {
  if (activeSubTab === "positions" && positionsView === "closed") {
    return "closed-trades";
  }
  return activeSubTab;
}

export function resolveTradingDeskVisibleTab(tabId: TradingDeskVisibleTabId): {
  activeSubTab: TradingDeskSubTabId;
  positionsView?: TradingDeskPositionsView;
} {
  if (tabId === "closed-trades") {
    return { activeSubTab: "positions", positionsView: "closed" };
  }
  if (tabId === "positions") {
    return { activeSubTab: "positions", positionsView: "open" };
  }
  return { activeSubTab: tabId };
}
