import type {
  BacktestReplayReport,
  BacktestResult,
  LiveTradePolicy,
  MetricTruthReport,
  PlaybookExitAudit,
  TruthLaneComparisonReport,
} from "@/lib/types";

const PYTHON_BACKEND_URL =
  process.env.PYTHON_BACKEND_URL || "http://localhost:8100";
const PYTHON_BACKEND_TIMEOUT_MS = Number(process.env.PYTHON_BACKEND_TIMEOUT_MS || 15000);

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
  init?: RequestInit
): Promise<T> {
  const res = await fetchBackendResponse(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok || (data as Record<string, unknown>).error) {
    throw new Error(String((data as Record<string, unknown>).error || `Python backend error: ${res.status}`));
  }
  return data as T;
}

export async function callTool(
  toolName: string,
  args: Record<string, unknown>
): Promise<string> {
  const res = await fetchBackendResponse(`/api/tools/${toolName}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!res.ok) {
    const text = await res.text();
    return JSON.stringify({
      error: `Python backend error: ${res.status}`,
      message: text,
    });
  }
  const data = await res.json();
  return data.result;
}

export async function getProfile(
  profileType: "equity" | "index" = "equity"
): Promise<Record<string, unknown>> {
  const res = await fetchBackendResponse(`/api/profile?type=${profileType}`);
  if (!res.ok) throw new Error(`Failed to fetch profile: ${res.status}`);
  return res.json();
}

export async function saveProfile(
  profileType: string,
  updates: Record<string, unknown>,
  note?: string
): Promise<void> {
  const res = await fetchBackendResponse(`/api/profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: profileType, updates, note }),
  });
  if (!res.ok) throw new Error(`Failed to save profile: ${res.status}`);
}

export async function getPredictions(): Promise<unknown[]> {
  const res = await fetchBackendResponse(`/api/predictions`);
  if (!res.ok) throw new Error(`Failed to fetch predictions: ${res.status}`);
  return res.json();
}

export async function getTrackedPositions(
  status: "open" | "closed" | "all" = "open"
): Promise<Record<string, unknown>> {
  const res = await fetchBackendResponse(`/api/positions?status=${status}`);
  const data = await res.json();
  if (!res.ok || (data as Record<string, unknown>).error) {
    throw new Error(String((data as Record<string, unknown>).error || `Failed to fetch positions: ${res.status}`));
  }
  return data;
}

export async function createTrackedPosition(
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const res = await fetchBackendResponse(`/api/positions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || (data as Record<string, unknown>).error) {
    throw new Error(String((data as Record<string, unknown>).error || `Failed to create tracked position: ${res.status}`));
  }
  return data;
}

export async function reviewTrackedPositions(
  payload: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
  const res = await fetchBackendResponse(`/api/positions/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || (data as Record<string, unknown>).error) {
    throw new Error(String((data as Record<string, unknown>).error || `Failed to review tracked positions: ${res.status}`));
  }
  return data;
}

export async function closeTrackedPosition(
  positionId: number,
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const res = await fetchBackendResponse(`/api/positions/${positionId}/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || (data as Record<string, unknown>).error) {
    throw new Error(String((data as Record<string, unknown>).error || `Failed to close tracked position: ${res.status}`));
  }
  return data;
}

export async function getSuggestedTrades(
  status: "open" | "closed" | "all" = "open"
): Promise<Record<string, unknown>> {
  const res = await fetchBackendResponse(`/api/suggested-trades?status=${status}`);
  const data = await res.json();
  if (!res.ok || (data as Record<string, unknown>).error) {
    throw new Error(String((data as Record<string, unknown>).error || `Failed to fetch suggested trades: ${res.status}`));
  }
  return data;
}

export async function createSuggestedTrade(
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const res = await fetchBackendResponse(`/api/suggested-trades`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || (data as Record<string, unknown>).error) {
    throw new Error(String((data as Record<string, unknown>).error || `Failed to create suggested trade: ${res.status}`));
  }
  return data;
}

export async function reviewSuggestedTrades(
  payload: Record<string, unknown> = {}
): Promise<Record<string, unknown>> {
  const res = await fetchBackendResponse(`/api/suggested-trades/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || (data as Record<string, unknown>).error) {
    throw new Error(String((data as Record<string, unknown>).error || `Failed to review suggested trades: ${res.status}`));
  }
  return data;
}

export async function closeSuggestedTrade(
  positionId: number,
  payload: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const res = await fetchBackendResponse(`/api/suggested-trades/${positionId}/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok || (data as Record<string, unknown>).error) {
    throw new Error(String((data as Record<string, unknown>).error || `Failed to close suggested trade: ${res.status}`));
  }
  return data;
}

export async function runScan(
  payload: number | Record<string, unknown> = 5
): Promise<Record<string, unknown>> {
  const body = typeof payload === "number" ? { n_picks: payload } : payload;
  const res = await fetchBackendResponse(`/api/scan`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Failed to run scan: ${res.status}`);
  return res.json();
}

export async function getLiveTradePolicy(
  params: Record<string, unknown> = {}
): Promise<LiveTradePolicy> {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value != null) acc[key] = String(value);
      return acc;
    }, {})
  );
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchBackendJson<LiveTradePolicy>(`/api/backtest/live-policy${suffix}`);
}

export async function getBacktestReport(
  params: Record<string, unknown> = {}
): Promise<BacktestReplayReport> {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value != null) acc[key] = String(value);
      return acc;
    }, {})
  );
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchBackendJson<BacktestReplayReport>(`/api/backtest/report${suffix}`);
}

export async function getMetricTruthReport(
  params: Record<string, unknown> = {}
): Promise<MetricTruthReport> {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value != null) acc[key] = String(value);
      return acc;
    }, {})
  );
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchBackendJson<MetricTruthReport>(`/api/backtest/metric-truth${suffix}`);
}

export async function getPlaybookExitAudit(
  params: Record<string, unknown> = {}
): Promise<PlaybookExitAudit> {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value != null) acc[key] = String(value);
      return acc;
    }, {})
  );
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchBackendJson<PlaybookExitAudit>(`/api/backtest/exit-audit${suffix}`);
}

export async function getBacktestLast(
  params: Record<string, unknown> = {}
): Promise<BacktestResult> {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value != null) acc[key] = String(value);
      return acc;
    }, {})
  );
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchBackendJson<BacktestResult>(`/api/backtest/last${suffix}`);
}

export async function getTruthLaneComparison(
  params: Record<string, unknown> = {}
): Promise<TruthLaneComparisonReport> {
  const search = new URLSearchParams(
    Object.entries(params).reduce<Record<string, string>>((acc, [key, value]) => {
      if (value != null) acc[key] = String(value);
      return acc;
    }, {})
  );
  const suffix = search.toString() ? `?${search.toString()}` : "";
  return fetchBackendJson<TruthLaneComparisonReport>(`/api/backtest/comparison${suffix}`);
}

export async function runBacktest(
  params: Record<string, unknown>
): Promise<BacktestResult> {
  const res = await fetch(`${PYTHON_BACKEND_URL}/api/backtest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`Failed to run backtest: ${res.status}`);
  return res.json() as Promise<BacktestResult>;
}

export async function getSectorSentiments(): Promise<unknown[]> {
  const res = await fetch(`${PYTHON_BACKEND_URL}/api/sectors`);
  if (!res.ok)
    throw new Error(`Failed to fetch sector data: ${res.status}`);
  return res.json();
}
