export const MAIN_APP_TAB_IDS = ["predictions", "strategy"] as const;

export type MainAppTabId = (typeof MAIN_APP_TAB_IDS)[number];

export type MainAppTab = {
  id: MainAppTabId;
  label: string;
  title: string;
  subtitle: string;
};

export const DEFAULT_MAIN_APP_TAB_ID: MainAppTabId = "predictions";

export const MAIN_APP_TABS: Record<MainAppTabId, MainAppTab> = {
  predictions: {
    id: "predictions",
    label: "Trading Desk",
    title: "Trading Desk",
    subtitle: "Open positions, scan picks, and paper ideas",
  },
  strategy: {
    id: "strategy",
    label: "Strategy Lab",
    title: "Strategy Lab",
    subtitle: "Replay validation and policy tuning",
  },
};

export const MAIN_APP_TAB_LIST: readonly MainAppTab[] = MAIN_APP_TAB_IDS.map(
  (id) => MAIN_APP_TABS[id]
);

export function getMainAppTab(id: MainAppTabId): MainAppTab {
  return MAIN_APP_TABS[id];
}
