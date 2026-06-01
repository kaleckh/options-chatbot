export const STRATEGY_LAB_MUTATION_HEADER = "x-strategy-lab-mutation";
export const STRATEGY_LAB_STORE_HEADER = "x-strategy-lab-store";
export const STRATEGY_LAB_LIFECYCLE_HEADER = "x-strategy-lab-lifecycle";
export const STRATEGY_LAB_RECORD_CLASS_HEADER = "x-strategy-lab-record-class";

export type StrategyLabMutationIntent =
  | "run_replay_backtest"
  | "save_strategy_profile";

export type StrategyLabStoreId =
  | "latest_replay_artifacts"
  | "strategy_profile_files"
  | "forward_evidence_artifacts";

export type StrategyLabLifecycle =
  | "read"
  | "replay_run"
  | "profile_save";

export type StrategyLabRecordClass =
  | "backtest_result"
  | "backtest_artifact_bundle"
  | "strategy_profile"
  | "forward_evidence_report";

export type StrategyLabRouteContractId =
  | "backtest_run"
  | "backtest_summary_read"
  | "backtest_last_read"
  | "backtest_report_read"
  | "metric_truth_read"
  | "truth_lane_comparison_read"
  | "live_policy_read"
  | "exit_audit_read"
  | "forward_evidence_read"
  | "profile_read"
  | "profile_changelog_read"
  | "profile_save";

export type StrategyLabRouteContract = {
  id: StrategyLabRouteContractId;
  method: "GET" | "POST" | "PUT";
  route: string;
  store: StrategyLabStoreId;
  lifecycle: StrategyLabLifecycle;
  recordClass: StrategyLabRecordClass;
  owner: string;
};

export const STRATEGY_LAB_ROUTE_CONTRACTS: Record<
  StrategyLabRouteContractId,
  StrategyLabRouteContract
> = {
  backtest_run: {
    id: "backtest_run",
    method: "POST",
    route: "/api/backtest",
    store: "latest_replay_artifacts",
    lifecycle: "replay_run",
    recordClass: "backtest_result",
    owner: "wfo_optimizer.py run_historical_backtest(save_result=True)",
  },
  backtest_summary_read: {
    id: "backtest_summary_read",
    method: "GET",
    route: "/api/backtest/summary",
    store: "latest_replay_artifacts",
    lifecycle: "read",
    recordClass: "backtest_artifact_bundle",
    owner: "wfo_optimizer.py load_preferred_results_by_truth_lane",
  },
  backtest_last_read: {
    id: "backtest_last_read",
    method: "GET",
    route: "/api/backtest/last",
    store: "latest_replay_artifacts",
    lifecycle: "read",
    recordClass: "backtest_result",
    owner: "wfo_optimizer.py load_last_results_by_truth_lane",
  },
  backtest_report_read: {
    id: "backtest_report_read",
    method: "GET",
    route: "/api/backtest/report",
    store: "latest_replay_artifacts",
    lifecycle: "read",
    recordClass: "backtest_artifact_bundle",
    owner: "wfo_optimizer.py build_prediction_replay_report",
  },
  metric_truth_read: {
    id: "metric_truth_read",
    method: "GET",
    route: "/api/backtest/metric-truth",
    store: "latest_replay_artifacts",
    lifecycle: "read",
    recordClass: "backtest_artifact_bundle",
    owner: "wfo_optimizer.py build_metric_truth_report",
  },
  truth_lane_comparison_read: {
    id: "truth_lane_comparison_read",
    method: "GET",
    route: "/api/backtest/comparison",
    store: "latest_replay_artifacts",
    lifecycle: "read",
    recordClass: "backtest_artifact_bundle",
    owner: "wfo_optimizer.py build_truth_lane_comparison_report",
  },
  live_policy_read: {
    id: "live_policy_read",
    method: "GET",
    route: "/api/backtest/live-policy",
    store: "latest_replay_artifacts",
    lifecycle: "read",
    recordClass: "backtest_artifact_bundle",
    owner: "wfo_optimizer.py build_live_trade_policy_report",
  },
  exit_audit_read: {
    id: "exit_audit_read",
    method: "GET",
    route: "/api/backtest/exit-audit",
    store: "latest_replay_artifacts",
    lifecycle: "read",
    recordClass: "backtest_artifact_bundle",
    owner: "wfo_optimizer.py build_playbook_exit_audit_report",
  },
  forward_evidence_read: {
    id: "forward_evidence_read",
    method: "GET",
    route: "/api/backtest/forward-evidence",
    store: "forward_evidence_artifacts",
    lifecycle: "read",
    recordClass: "forward_evidence_report",
    owner: "data/forward-tracking and data/options-validation artifacts",
  },
  profile_read: {
    id: "profile_read",
    method: "GET",
    route: "/api/profile",
    store: "strategy_profile_files",
    lifecycle: "read",
    recordClass: "strategy_profile",
    owner: "options_chatbot.py STRATEGY_PROFILES and strategy_profile.json",
  },
  profile_changelog_read: {
    id: "profile_changelog_read",
    method: "GET",
    route: "/api/changelog",
    store: "strategy_profile_files",
    lifecycle: "read",
    recordClass: "strategy_profile",
    owner: "options_chatbot.py CHANGELOG_FILES and brain_changelog*.json",
  },
  profile_save: {
    id: "profile_save",
    method: "PUT",
    route: "/api/profile",
    store: "strategy_profile_files",
    lifecycle: "profile_save",
    recordClass: "strategy_profile",
    owner: "options_chatbot.py _save_profile and profile changelog files",
  },
};

export function strategyLabMutationHeaders(intent: StrategyLabMutationIntent): HeadersInit {
  return {
    "Content-Type": "application/json",
    [STRATEGY_LAB_MUTATION_HEADER]: intent,
  };
}

export function getStrategyLabRouteContract(
  id: StrategyLabRouteContractId
): StrategyLabRouteContract {
  return STRATEGY_LAB_ROUTE_CONTRACTS[id];
}

export function strategyLabRouteHeaders(id: StrategyLabRouteContractId): HeadersInit {
  const contract = getStrategyLabRouteContract(id);
  return {
    [STRATEGY_LAB_STORE_HEADER]: contract.store,
    [STRATEGY_LAB_LIFECYCLE_HEADER]: contract.lifecycle,
    [STRATEGY_LAB_RECORD_CLASS_HEADER]: contract.recordClass,
  };
}
