import {
  fetchBackendJson,
  fetchBackendJsonWithHeaders,
  postBackendJson,
  pythonBackendTimingHeaders,
  toSearchSuffix,
} from "@/lib/backend/transport";
import type {
  CloseSuggestedTradeRequest,
  CloseSuggestedTradeResponse,
  CloseTrackedPositionRequest,
  CloseTrackedPositionResponse,
  CreateSuggestedTradeRequest,
  CreateSuggestedTradeResponse,
  CreateTrackedPositionRequest,
  CreateTrackedPositionResponse,
  GroupedSuggestedTradesResponse,
  GroupedTrackedPositionsResponse,
  ReviewSuggestedTradesRequest,
  ReviewSuggestedTradesResponse,
  ReviewTrackedPositionsRequest,
  ReviewTrackedPositionsResponse,
  SuggestedTradesListResponse,
  TrackedPositionsListResponse,
  TradingDeskBackendResponseWithTiming,
  TradingDeskListStatus,
  TradingDeskListWindow,
} from "@/lib/trading-desk/apiContracts";

export async function getTrackedPositions(
  status: TradingDeskListStatus = "open",
  window: TradingDeskListWindow = {}
): Promise<TrackedPositionsListResponse> {
  return fetchBackendJson<TrackedPositionsListResponse>(
    `/api/positions${toSearchSuffix({ status, ...window })}`,
    undefined,
    "Failed to fetch positions"
  );
}

export async function getTrackedPositionsWithBackendHeaders(
  status: TradingDeskListStatus = "open",
  window: TradingDeskListWindow = {}
): Promise<TradingDeskBackendResponseWithTiming<TrackedPositionsListResponse>> {
  const result = await fetchBackendJsonWithHeaders<TrackedPositionsListResponse>(
    `/api/positions${toSearchSuffix({ status, ...window })}`,
    undefined,
    "Failed to fetch positions"
  );
  return { body: result.body, headers: pythonBackendTimingHeaders(result.headers) };
}

export async function getGroupedTrackedPositions(
  status: TradingDeskListStatus = "all",
  window: TradingDeskListWindow = {}
): Promise<GroupedTrackedPositionsResponse> {
  return fetchBackendJson<GroupedTrackedPositionsResponse>(
    `/api/positions${toSearchSuffix({ status, grouped: 1, ...window })}`
  );
}

export async function getGroupedTrackedPositionsWithBackendHeaders(
  status: TradingDeskListStatus = "all",
  window: TradingDeskListWindow = {}
): Promise<TradingDeskBackendResponseWithTiming<GroupedTrackedPositionsResponse>> {
  const result = await fetchBackendJsonWithHeaders<GroupedTrackedPositionsResponse>(
    `/api/positions${toSearchSuffix({ status, grouped: 1, ...window })}`
  );
  return { body: result.body, headers: pythonBackendTimingHeaders(result.headers) };
}

export async function createTrackedPosition(
  payload: CreateTrackedPositionRequest
): Promise<CreateTrackedPositionResponse> {
  return postBackendJson<CreateTrackedPositionResponse, CreateTrackedPositionRequest>(
    "/api/positions",
    payload,
    "Failed to create tracked position"
  );
}

export async function reviewTrackedPositions(
  payload: ReviewTrackedPositionsRequest = {}
): Promise<ReviewTrackedPositionsResponse> {
  return postBackendJson<ReviewTrackedPositionsResponse, ReviewTrackedPositionsRequest>(
    "/api/positions/review",
    payload,
    "Failed to review tracked positions"
  );
}

export async function closeTrackedPosition(
  positionId: number,
  payload: CloseTrackedPositionRequest
): Promise<CloseTrackedPositionResponse> {
  return postBackendJson<CloseTrackedPositionResponse, CloseTrackedPositionRequest>(
    `/api/positions/${positionId}/close`,
    payload,
    "Failed to close tracked position"
  );
}

export async function getSuggestedTrades(
  status: TradingDeskListStatus = "open",
  window: TradingDeskListWindow = {}
): Promise<SuggestedTradesListResponse> {
  return fetchBackendJson<SuggestedTradesListResponse>(
    `/api/suggested-trades${toSearchSuffix({ status, ...window })}`,
    undefined,
    "Failed to fetch suggested trades"
  );
}

export async function getSuggestedTradesWithBackendHeaders(
  status: TradingDeskListStatus = "open",
  window: TradingDeskListWindow = {}
): Promise<TradingDeskBackendResponseWithTiming<SuggestedTradesListResponse>> {
  const result = await fetchBackendJsonWithHeaders<SuggestedTradesListResponse>(
    `/api/suggested-trades${toSearchSuffix({ status, ...window })}`,
    undefined,
    "Failed to fetch suggested trades"
  );
  return { body: result.body, headers: pythonBackendTimingHeaders(result.headers) };
}

export async function getGroupedSuggestedTrades(
  status: TradingDeskListStatus = "all",
  window: TradingDeskListWindow = {}
): Promise<GroupedSuggestedTradesResponse> {
  return fetchBackendJson<GroupedSuggestedTradesResponse>(
    `/api/suggested-trades${toSearchSuffix({ status, grouped: 1, ...window })}`
  );
}

export async function getGroupedSuggestedTradesWithBackendHeaders(
  status: TradingDeskListStatus = "all",
  window: TradingDeskListWindow = {}
): Promise<TradingDeskBackendResponseWithTiming<GroupedSuggestedTradesResponse>> {
  const result = await fetchBackendJsonWithHeaders<GroupedSuggestedTradesResponse>(
    `/api/suggested-trades${toSearchSuffix({ status, grouped: 1, ...window })}`
  );
  return { body: result.body, headers: pythonBackendTimingHeaders(result.headers) };
}

export async function createSuggestedTrade(
  payload: CreateSuggestedTradeRequest
): Promise<CreateSuggestedTradeResponse> {
  return postBackendJson<CreateSuggestedTradeResponse, CreateSuggestedTradeRequest>(
    "/api/suggested-trades",
    payload,
    "Failed to create suggested trade"
  );
}

export async function reviewSuggestedTrades(
  payload: ReviewSuggestedTradesRequest = {}
): Promise<ReviewSuggestedTradesResponse> {
  return postBackendJson<ReviewSuggestedTradesResponse, ReviewSuggestedTradesRequest>(
    "/api/suggested-trades/review",
    payload,
    "Failed to review suggested trades"
  );
}

export async function closeSuggestedTrade(
  positionId: number,
  payload: CloseSuggestedTradeRequest
): Promise<CloseSuggestedTradeResponse> {
  return postBackendJson<CloseSuggestedTradeResponse, CloseSuggestedTradeRequest>(
    `/api/suggested-trades/${positionId}/close`,
    payload,
    "Failed to close suggested trade"
  );
}
