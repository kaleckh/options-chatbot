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

const PYTHON_BACKEND_URL =
  process.env.PYTHON_BACKEND_URL || "http://localhost:8100";
const PYTHON_BACKEND_TIMEOUT_MS = Number(process.env.PYTHON_BACKEND_TIMEOUT_MS || 30000);
const JSON_REQUEST_HEADERS = { "Content-Type": "application/json" };

function buildBackendTimeoutError(path: string): Error {
  return new Error(`Python backend request timed out for ${path} after ${Math.round(PYTHON_BACKEND_TIMEOUT_MS / 1000)}s`);
}

async function fetchBackendResponse(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), PYTHON_BACKEND_TIMEOUT_MS);
  try {
    return await fetch(`${PYTHON_BACKEND_URL}${path}`, {
      ...init,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw buildBackendTimeoutError(path);
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }
}

async function fetchBackendJson<T = Record<string, unknown>>(
  path: string,
  init?: RequestInit,
  errorPrefix: string = "Python backend error"
): Promise<T> {
  const res = await fetchBackendResponse(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || (data as Record<string, unknown>).error) {
    throw new Error(String((data as Record<string, unknown>).error || `${errorPrefix}: ${res.status}`));
  }
  return data as T;
}

function toJsonBody(value: Record<string, unknown>): string {
  return JSON.stringify(value);
}

function toSearchSuffix(params: Record<string, unknown> = {}): string {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value != null) acc[key] = String(value);
      return acc;
    }, {})
  );
  return search.toString() ? `?${search.toString()}` : "";
}

function normalizeToolResult(result: unknown): string {
  if (result == null) return "";
  if (typeof result === "string") return result;
  return JSON.stringify(result) ?? "";
}

async function postBackendJson<T = Record<string, unknown>>(
  path: string,
  payload: Record<string, unknown>,
  errorPrefix: string
): Promise<T> {
  return fetchBackendJson<T>(
    path,
    {
      method: "POST",
      headers: JSON_REQUEST_HEADERS,
      body: toJsonBody(payload),
    },
    errorPrefix
  );
}

async function putBackendJson(
  path: string,
  payload: Record<string, unknown>,
  errorPrefix: string
): Promise<void> {
  await fetchBackendJson<Record<string, unknown>>(
    path,
    {
      method: "PUT",
      headers: JSON_REQUEST_HEADERS,
      body: toJsonBody(payload),
    },
    errorPrefix
  );
}

export async function callTool(
  toolName: string,
  args: Record<string, unknown>
): Promise<string> {
  const res = await fetchBackendResponse(`/api/tools/${toolName}`, {
    method: "POST",
    headers: JSON_REQUEST_HEADERS,
    body: toJsonBody(args),
  });
  if (!res.ok) {
    const text = await res.text();
    return JSON.stringify({
      error: `Python backend error: ${res.status}`,
      message: text,
    });
  }
  const data = await res.json();
  return normalizeToolResult(data.result);
}

export async function getRiskSettings(): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>("/api/risk");
}

export async function getProfiles(): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>("/api/profiles");
}

export async function getPredictionHistory(): Promise<unknown[]> {
  return fetchBackendJson<unknown[]>("/api/predictions");
}

export async function gradePredictions(
  payload: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
  return postBackendJson<Record<string, unknown>>(
    "/api/predictions/grade",
    payload,
    "Failed to grade predictions"
  );
}

export async function getChangelog(profile: string = "equity"): Promise<unknown[]> {
  return fetchBackendJson<unknown[]>(`/api/changelog?profile=${encodeURIComponent(profile)}`);
}

export async function getProfile(
  profileType: "equity" | "index" = "equity"
): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>(
    `/api/profile?type=${profileType}`,
    undefined,
    "Failed to fetch profile"
  );
}

export async function saveProfile(
  profileType: string,
  updates: Record<string, unknown>,
  note?: string
): Promise<void> {
  await putBackendJson(
    "/api/profile",
    { type: profileType, updates, note },
    "Failed to save profile"
  );
}

export async function getPredictions(): Promise<unknown[]> {
  return fetchBackendJson<unknown[]>(
    "/api/predictions",
    undefined,
    "Failed to fetch predictions"
  );
}

export async function getTrackedPositions(
  status: "open" | "closed" | "all" = "open"
): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>(
    `/api/positions?status=${status}`,
    undefined,
    "Failed to fetch positions"
  );
}

export async function getGroupedTrackedPositions(): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>("/api/positions?status=all&grouped=1");
}

export async function createTrackedPosition(
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  return postBackendJson<Record<string, unknown>>(
    "/api/positions",
    payload,
    "Failed to create tracked position"
  );
}

export async function reviewTrackedPositions(
  payload: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
  return postBackendJson<Record<string, unknown>>(
    "/api/positions/review",
    payload,
    "Failed to review tracked positions"
  );
}

export async function closeTrackedPosition(
  positionId: number,
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  return postBackendJson<Record<string, unknown>>(
    `/api/positions/${positionId}/close`,
    payload,
    "Failed to close tracked position"
  );
}

export async function getSuggestedTrades(
  status: "open" | "closed" | "all" = "open"
): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>(
    `/api/suggested-trades?status=${status}`,
    undefined,
    "Failed to fetch suggested trades"
  );
}

export async function getGroupedSuggestedTrades(): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>("/api/suggested-trades?status=all&grouped=1");
}

export async function createSuggestedTrade(
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  return postBackendJson<Record<string, unknown>>(
    "/api/suggested-trades",
    payload,
    "Failed to create suggested trade"
  );
}

export async function reviewSuggestedTrades(
  payload: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
  return postBackendJson<Record<string, unknown>>(
    "/api/suggested-trades/review",
    payload,
    "Failed to review suggested trades"
  );
}

export async function closeSuggestedTrade(
  positionId: number,
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  return postBackendJson<Record<string, unknown>>(
    `/api/suggested-trades/${positionId}/close`,
    payload,
    "Failed to close suggested trade"
  );
}

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

export async function runBacktest(
  params: Record<string, unknown>
): Promise<BacktestResult> {
  return postBackendJson<BacktestResult>(
    "/api/backtest",
    params,
    "Failed to run backtest"
  );
}

export async function getSectorSentiments(): Promise<unknown[]> {
  return fetchBackendJson<unknown[]>(
    "/api/sectors",
    undefined,
    "Failed to fetch sector data"
  );
}
