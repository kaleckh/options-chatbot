import { fetchBackendJson, postBackendJson } from "@/lib/backend/transport";

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
