import type {
  BacktestReplayReport,
  BacktestResult,
  ForwardEvidenceReport,
  LiveTradePolicy,
  MetricTruthReport,
  OptionsProfitStatus,
  PlaybookExitAudit,
  TruthLaneComparisonReport,
} from "@/lib/types";
import {
  fetchBackendJson,
  fetchBackendJsonWithHeaders,
  postBackendJson,
  pythonBackendTimingHeaders,
  toSearchSuffix,
} from "@/lib/backend/transport";

export async function runScan(
  payload: number | Record<string, unknown> = 5
): Promise<Record<string, unknown>> {
  const body = typeof payload === "number" ? { n_picks: payload } : payload;
  return postBackendJson<Record<string, unknown>>(
    "/api/scan",
    body,
    "Failed to run scan"
  );
}

export async function getLiveTradePolicy(
  params: Record<string, unknown> = {}
): Promise<LiveTradePolicy> {
  return fetchBackendJson<LiveTradePolicy>(`/api/backtest/live-policy${toSearchSuffix(params)}`);
}

export async function getBacktestReport(
  params: Record<string, unknown> = {}
): Promise<BacktestReplayReport> {
  return fetchBackendJson<BacktestReplayReport>(`/api/backtest/report${toSearchSuffix(params)}`);
}

export async function getMetricTruthReport(
  params: Record<string, unknown> = {}
): Promise<MetricTruthReport> {
  return fetchBackendJson<MetricTruthReport>(`/api/backtest/metric-truth${toSearchSuffix(params)}`);
}

export async function getPlaybookExitAudit(
  params: Record<string, unknown> = {}
): Promise<PlaybookExitAudit> {
  return fetchBackendJson<PlaybookExitAudit>(`/api/backtest/exit-audit${toSearchSuffix(params)}`);
}

export async function getBacktestLast(
  params: Record<string, unknown> = {}
): Promise<BacktestResult> {
  return fetchBackendJson<BacktestResult>(`/api/backtest/last${toSearchSuffix(params)}`);
}

export async function getTruthLaneComparison(
  params: Record<string, unknown> = {}
): Promise<TruthLaneComparisonReport> {
  return fetchBackendJson<TruthLaneComparisonReport>(`/api/backtest/comparison${toSearchSuffix(params)}`);
}

export async function getBacktestSummary(
  params: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>(`/api/backtest/summary${toSearchSuffix(params)}`);
}

export async function getForwardEvidenceReport(
  params: Record<string, unknown> = {}
): Promise<ForwardEvidenceReport> {
  return fetchBackendJson<ForwardEvidenceReport>(`/api/backtest/forward-evidence${toSearchSuffix(params)}`);
}

export async function getOptionsProfitStatus(): Promise<OptionsProfitStatus> {
  return fetchBackendJson<OptionsProfitStatus>("/api/options-profit/status");
}

export async function getOptionsProfitStatusWithBackendHeaders(): Promise<{
  body: OptionsProfitStatus;
  headers: Record<string, string>;
}> {
  const result = await fetchBackendJsonWithHeaders<OptionsProfitStatus>("/api/options-profit/status");
  return { body: result.body, headers: pythonBackendTimingHeaders(result.headers) };
}

export async function runBacktest(
  params: Record<string, unknown>
): Promise<BacktestResult> {
  return postBackendJson<BacktestResult>(
    "/api/backtest",
    params,
    "Failed to run backtest"
  );
}
