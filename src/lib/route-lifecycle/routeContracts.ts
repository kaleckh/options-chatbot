export const OPTIONS_ROUTE_CONTRACT_HEADER = "x-options-route-contract";
export const OPTIONS_ROUTE_FAMILY_HEADER = "x-options-route-family";
export const OPTIONS_ROUTE_STORE_HEADER = "x-options-route-store";
export const OPTIONS_ROUTE_LIFECYCLE_HEADER = "x-options-route-lifecycle";
export const OPTIONS_ROUTE_RECORD_CLASS_HEADER = "x-options-route-record-class";

export const OPTIONS_ROUTE_LIFECYCLE_CONTRACT_IDS = [
  "scan_run",
  "predictions_read",
  "predictions_grade",
  "risk_settings_read",
  "options_profit_status_read",
  "operator_session_status",
  "operator_session_unlock",
  "sectors_read",
  "tool_dispatch",
] as const;

export type OptionsRouteLifecycleContractId = (typeof OPTIONS_ROUTE_LIFECYCLE_CONTRACT_IDS)[number];

export type OptionsRouteLifecycleContract = {
  id: OptionsRouteLifecycleContractId;
  method: "GET" | "POST";
  route: string;
  family: string;
  store: string;
  lifecycle: string;
  recordClass: string;
  owner: string;
};

export const OPTIONS_ROUTE_LIFECYCLE_CONTRACTS: Record<
  OptionsRouteLifecycleContractId,
  OptionsRouteLifecycleContract
> = {
  scan_run: {
    id: "scan_run",
    method: "POST",
    route: "/api/scan",
    family: "scan",
    store: "forward_evidence_artifacts",
    lifecycle: "live_scan_run",
    recordClass: "scan_result",
    owner: "python-backend/main.py /api/scan and forward_options_ledger.py",
  },
  predictions_read: {
    id: "predictions_read",
    method: "GET",
    route: "/api/predictions",
    family: "predictions",
    store: "predictions_json",
    lifecycle: "read",
    recordClass: "prediction_history",
    owner: "options_chatbot.py predictions.json",
  },
  predictions_grade: {
    id: "predictions_grade",
    method: "POST",
    route: "/api/predictions/grade",
    family: "predictions",
    store: "predictions_json",
    lifecycle: "prediction_grade",
    recordClass: "prediction_history",
    owner: "python-backend/predictions_routes.py grade_predictions_endpoint",
  },
  risk_settings_read: {
    id: "risk_settings_read",
    method: "GET",
    route: "/api/risk-settings",
    family: "profile_status",
    store: "strategy_profile_files",
    lifecycle: "read",
    recordClass: "risk_settings",
    owner: "python-backend/profile_routes.py /api/risk",
  },
  options_profit_status_read: {
    id: "options_profit_status_read",
    method: "GET",
    route: "/api/options-profit/status",
    family: "profile_status",
    store: "options_profit_state_artifacts",
    lifecycle: "read",
    recordClass: "options_profit_status",
    owner: "python-backend/main.py /api/options-profit/status",
  },
  operator_session_status: {
    id: "operator_session_status",
    method: "GET",
    route: "/api/operator/session",
    family: "operator_auth",
    store: "local_operator_session_cookie",
    lifecycle: "session_status",
    recordClass: "operator_session",
    owner: "src/lib/operator-auth.ts",
  },
  operator_session_unlock: {
    id: "operator_session_unlock",
    method: "POST",
    route: "/api/operator/session",
    family: "operator_auth",
    store: "local_operator_session_cookie",
    lifecycle: "session_unlock",
    recordClass: "operator_session",
    owner: "src/lib/operator-auth.ts",
  },
  sectors_read: {
    id: "sectors_read",
    method: "GET",
    route: "/api/sectors",
    family: "support",
    store: "market_data_cache",
    lifecycle: "read",
    recordClass: "sector_sentiment_snapshot",
    owner: "python-backend/main.py /api/sectors",
  },
  tool_dispatch: {
    id: "tool_dispatch",
    method: "POST",
    route: "/api/tools/{name}",
    family: "support",
    store: "backend_tool_dispatch",
    lifecycle: "tool_dispatch",
    recordClass: "tool_result",
    owner: "python-backend/tools_routes.py /api/tools/{tool_name}",
  },
};

export function getOptionsRouteLifecycleContract(
  id: OptionsRouteLifecycleContractId
): OptionsRouteLifecycleContract {
  return OPTIONS_ROUTE_LIFECYCLE_CONTRACTS[id];
}

export function optionsRouteLifecycleHeaders(id: OptionsRouteLifecycleContractId): HeadersInit {
  const contract = getOptionsRouteLifecycleContract(id);
  return {
    [OPTIONS_ROUTE_CONTRACT_HEADER]: contract.id,
    [OPTIONS_ROUTE_FAMILY_HEADER]: contract.family,
    [OPTIONS_ROUTE_STORE_HEADER]: contract.store,
    [OPTIONS_ROUTE_LIFECYCLE_HEADER]: contract.lifecycle,
    [OPTIONS_ROUTE_RECORD_CLASS_HEADER]: contract.recordClass,
  };
}
