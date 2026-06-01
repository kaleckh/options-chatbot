import {
  fetchBackendJson,
  fetchBackendJsonWithHeaders,
  postBackendJson,
  pythonBackendTimingHeaders,
  toSearchSuffix,
} from "@/lib/backend/transport";

type PositionListWindow = {
  limit?: number | string | null;
  offset?: number | string | null;
  compact?: number | string | null;
};

type BackendBodyWithTimingHeaders<T = Record<string, unknown>> = {
  body: T;
  headers: Record<string, string>;
};

export async function getTrackedPositions(
  status: "open" | "closed" | "all" = "open",
  window: PositionListWindow = {}
): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>(
    `/api/positions${toSearchSuffix({ status, ...window })}`,
    undefined,
    "Failed to fetch positions"
  );
}

export async function getTrackedPositionsWithBackendHeaders(
  status: "open" | "closed" | "all" = "open",
  window: PositionListWindow = {}
): Promise<BackendBodyWithTimingHeaders> {
  const result = await fetchBackendJsonWithHeaders<Record<string, unknown>>(
    `/api/positions${toSearchSuffix({ status, ...window })}`,
    undefined,
    "Failed to fetch positions"
  );
  return { body: result.body, headers: pythonBackendTimingHeaders(result.headers) };
}

export async function getGroupedTrackedPositions(
  status: "open" | "closed" | "all" = "all",
  window: PositionListWindow = {}
): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>(
    `/api/positions${toSearchSuffix({ status, grouped: 1, ...window })}`
  );
}

export async function getGroupedTrackedPositionsWithBackendHeaders(
  status: "open" | "closed" | "all" = "all",
  window: PositionListWindow = {}
): Promise<BackendBodyWithTimingHeaders> {
  const result = await fetchBackendJsonWithHeaders<Record<string, unknown>>(
    `/api/positions${toSearchSuffix({ status, grouped: 1, ...window })}`
  );
  return { body: result.body, headers: pythonBackendTimingHeaders(result.headers) };
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
  status: "open" | "closed" | "all" = "open",
  window: PositionListWindow = {}
): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>(
    `/api/suggested-trades${toSearchSuffix({ status, ...window })}`,
    undefined,
    "Failed to fetch suggested trades"
  );
}

export async function getSuggestedTradesWithBackendHeaders(
  status: "open" | "closed" | "all" = "open",
  window: PositionListWindow = {}
): Promise<BackendBodyWithTimingHeaders> {
  const result = await fetchBackendJsonWithHeaders<Record<string, unknown>>(
    `/api/suggested-trades${toSearchSuffix({ status, ...window })}`,
    undefined,
    "Failed to fetch suggested trades"
  );
  return { body: result.body, headers: pythonBackendTimingHeaders(result.headers) };
}

export async function getGroupedSuggestedTrades(
  status: "open" | "closed" | "all" = "all",
  window: PositionListWindow = {}
): Promise<Record<string, unknown>> {
  return fetchBackendJson<Record<string, unknown>>(
    `/api/suggested-trades${toSearchSuffix({ status, grouped: 1, ...window })}`
  );
}

export async function getGroupedSuggestedTradesWithBackendHeaders(
  status: "open" | "closed" | "all" = "all",
  window: PositionListWindow = {}
): Promise<BackendBodyWithTimingHeaders> {
  const result = await fetchBackendJsonWithHeaders<Record<string, unknown>>(
    `/api/suggested-trades${toSearchSuffix({ status, grouped: 1, ...window })}`
  );
  return { body: result.body, headers: pythonBackendTimingHeaders(result.headers) };
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
