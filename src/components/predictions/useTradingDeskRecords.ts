"use client";

import { useCallback, useRef, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { fetchWithTimeout, readJsonResponseOrThrow } from "@/lib/client-json";
import { tradingDeskMutationHeaders } from "@/lib/trading-desk/mutationIntent";
import type { SuggestedTrade, TrackedPosition } from "@/lib/types";

const AUTO_REVIEW_STALE_MS = 5 * 60 * 1000;
export const CLOSED_POSITION_PAGE_SIZE = 100;
export const CLOSED_SUGGESTED_TRADE_PAGE_SIZE = 100;

export type PositionLoadOptions = {
  notify?: boolean;
  review?: "none" | "force";
  includeClosed?: boolean;
};

export type ClosedPageOptions = {
  append?: boolean;
  notify?: boolean;
};

function idsNeedingAutoReview<T extends { id: number }>(
  items: T[],
  lastReviewedAtById: globalThis.Map<number, number>,
  {
    force,
    staleMs = AUTO_REVIEW_STALE_MS,
  }: {
    force: boolean;
    staleMs?: number;
  }
): number[] {
  const now = Date.now();
  return items
    .map((item) => item.id)
    .filter((id) => force || now - (lastReviewedAtById.get(id) ?? 0) >= staleMs);
}

function dedupeById<T extends { id: number }>(items: T[]): T[] {
  const seen = new Set<number>();
  const result: T[] = [];
  for (const item of items) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    result.push(item);
  }
  return result;
}

function hasMorePage(payload: unknown, fallbackLimit: number): boolean {
  if (!payload || typeof payload !== "object") return false;
  const page = (payload as { page?: { returned?: unknown; limit?: unknown } }).page;
  if (!page) return false;
  const returned = Number(page.returned);
  const limit = Number(page.limit || fallbackLimit);
  return Number.isFinite(returned) && Number.isFinite(limit) && returned >= limit;
}

export function useTradingDeskRecords() {
  const toast = useToast();
  const [openPositions, setOpenPositions] = useState<TrackedPosition[]>([]);
  const [closedPositions, setClosedPositions] = useState<TrackedPosition[]>([]);
  const [openSuggestedTrades, setOpenSuggestedTrades] = useState<SuggestedTrade[]>([]);
  const [closedSuggestedTrades, setClosedSuggestedTrades] = useState<SuggestedTrade[]>([]);
  const [closedPositionsLoaded, setClosedPositionsLoaded] = useState(false);
  const [closedPositionsHasMore, setClosedPositionsHasMore] = useState(false);
  const [closedPositionsLoadingMore, setClosedPositionsLoadingMore] = useState(false);
  const [closedSuggestedTradesLoaded, setClosedSuggestedTradesLoaded] = useState(false);
  const [closedSuggestedTradesHasMore, setClosedSuggestedTradesHasMore] = useState(false);
  const [closedSuggestedTradesLoadingMore, setClosedSuggestedTradesLoadingMore] = useState(false);
  const [positionsLoaded, setPositionsLoaded] = useState(false);
  const [positionsLoading, setPositionsLoading] = useState(false);
  const [positionsError, setPositionsError] = useState<string | null>(null);
  const [suggestedTradesLoaded, setSuggestedTradesLoaded] = useState(false);
  const [suggestedTradesLoading, setSuggestedTradesLoading] = useState(false);
  const [suggestedTradesError, setSuggestedTradesError] = useState<string | null>(null);
  const [reviewingIds, setReviewingIds] = useState<number[]>([]);
  const [reviewingSuggestedTradeIds, setReviewingSuggestedTradeIds] = useState<number[]>([]);
  const positionsRequestIdRef = useRef(0);
  const closedPositionsRequestIdRef = useRef(0);
  const suggestedTradesRequestIdRef = useRef(0);
  const closedSuggestedTradesRequestIdRef = useRef(0);
  const positionsReviewInFlightRef = useRef(false);
  const suggestedTradesReviewInFlightRef = useRef(false);
  const positionsLastReviewedAtRef = useRef<globalThis.Map<number, number>>(new globalThis.Map());
  const suggestedTradesLastReviewedAtRef = useRef<globalThis.Map<number, number>>(new globalThis.Map());

  const mergeTrackedPosition = useCallback((position: TrackedPosition) => {
    setOpenPositions((prev) =>
      position.status === "open"
        ? [position, ...prev.filter((item) => item.id !== position.id)]
        : prev.filter((item) => item.id !== position.id)
    );
    setClosedPositions((prev) =>
      position.status === "closed"
        ? [position, ...prev.filter((item) => item.id !== position.id)]
        : prev.filter((item) => item.id !== position.id)
    );
  }, []);

  const mergeSuggestedTrade = useCallback((trade: SuggestedTrade) => {
    setOpenSuggestedTrades((prev) =>
      trade.status === "open"
        ? [trade, ...prev.filter((item) => item.id !== trade.id)]
        : prev.filter((item) => item.id !== trade.id)
    );
    setClosedSuggestedTrades((prev) =>
      trade.status === "closed"
        ? [trade, ...prev.filter((item) => item.id !== trade.id)]
        : prev.filter((item) => item.id !== trade.id)
    );
  }, []);

  const applyReviewedPositions = useCallback((reviewed: TrackedPosition[]) => {
    const reviewedById = new globalThis.Map<number, TrackedPosition>(
      reviewed.map((position) => [position.id, position])
    );
    const closedReviewed = reviewed.filter((position) => position.status === "closed");
    const closedReviewedIds = new Set(closedReviewed.map((position) => position.id));
    setOpenPositions((prev) =>
      prev
        .map((position) => reviewedById.get(position.id) ?? position)
        .filter((position) => position.status === "open")
    );
    if (closedReviewed.length > 0) {
      setClosedPositions((prev) => [
        ...closedReviewed,
        ...prev.filter((position) => !closedReviewedIds.has(position.id)),
      ]);
    }
  }, []);

  const applyReviewedSuggestedTrades = useCallback((reviewed: SuggestedTrade[]) => {
    const reviewedById = new globalThis.Map<number, SuggestedTrade>(
      reviewed.map((trade) => [trade.id, trade])
    );
    const closedReviewed = reviewed.filter((trade) => trade.status === "closed");
    const closedReviewedIds = new Set(closedReviewed.map((trade) => trade.id));
    setOpenSuggestedTrades((prev) =>
      prev
        .map((trade) => reviewedById.get(trade.id) ?? trade)
        .filter((trade) => trade.status === "open")
    );
    if (closedReviewed.length > 0) {
      setClosedSuggestedTrades((prev) => [
        ...closedReviewed,
        ...prev.filter((trade) => !closedReviewedIds.has(trade.id)),
      ]);
    }
  }, []);

  const fetchPositions = useCallback(async (options: PositionLoadOptions = {}) => {
    const notify = options.notify === true;
    const shouldReview = options.review === "force";
    const includeClosed = options.includeClosed === true;
    const requestId = ++positionsRequestIdRef.current;
    const isCurrentRequest = () => requestId === positionsRequestIdRef.current;
    setPositionsLoading(true);
    try {
      const [openRes, closedRes] = await Promise.all([
        fetchWithTimeout("/api/positions?status=open&compact=1", undefined, "Tracked open positions"),
        includeClosed
          ? fetchWithTimeout(
              `/api/positions?status=closed&limit=${CLOSED_POSITION_PAGE_SIZE}&offset=0&compact=1`,
              undefined,
              "Tracked closed positions"
            )
          : Promise.resolve(null),
      ]);
      const data = await readJsonResponseOrThrow<{ positions?: TrackedPosition[] }>(
        openRes,
        "Tracked open positions"
      );
      if (!isCurrentRequest()) return;
      const nextOpenPositions = (data.positions || []) as TrackedPosition[];
      setOpenPositions(nextOpenPositions);
      if (closedRes) {
        const closedData = await readJsonResponseOrThrow<{ positions?: TrackedPosition[] }>(
          closedRes,
          "Tracked closed positions"
        );
        if (!isCurrentRequest()) return;
        const nextClosedPositions = (closedData.positions || []) as TrackedPosition[];
        setClosedPositions(nextClosedPositions);
        setClosedPositionsLoaded(true);
        setClosedPositionsHasMore(hasMorePage(closedData, CLOSED_POSITION_PAGE_SIZE));
      }
      setPositionsLoaded(true);
      setPositionsError(null);
      let reviewFailed = false;
      const reviewIds = shouldReview
        ? idsNeedingAutoReview(
            nextOpenPositions,
            positionsLastReviewedAtRef.current,
            { force: true }
          )
        : [];
      let reviewAttempted = false;
      if (reviewIds.length > 0 && !positionsReviewInFlightRef.current) {
        reviewAttempted = true;
        positionsReviewInFlightRef.current = true;
        try {
          const reviewRes = await fetchWithTimeout("/api/positions/review", {
            method: "POST",
            headers: tradingDeskMutationHeaders("review_tracked_positions"),
            body: JSON.stringify({ position_ids: reviewIds }),
          }, "Tracked position review");
          const reviewData = await readJsonResponseOrThrow<{ positions?: TrackedPosition[] }>(
            reviewRes,
            "Tracked position review"
          );
          if (!isCurrentRequest()) return;
          const reviewedPositions = (reviewData.positions || []) as TrackedPosition[];
          const reviewedAt = Date.now();
          reviewIds.forEach((id) => positionsLastReviewedAtRef.current.set(id, reviewedAt));
          reviewedPositions.forEach((position) => positionsLastReviewedAtRef.current.set(position.id, reviewedAt));
          applyReviewedPositions(reviewedPositions);
        } catch (reviewErr) {
          if (!isCurrentRequest()) return;
          reviewFailed = true;
          const message = reviewErr instanceof Error ? reviewErr.message : "Failed to review tracked positions.";
          setPositionsError(`Tracked positions loaded, but repricing failed: ${message}`);
          if (notify) {
            toast.error(`Tracked positions loaded, but repricing failed: ${message}`);
          }
        } finally {
          positionsReviewInFlightRef.current = false;
        }
      }
      if (notify && !reviewFailed) {
        toast.success(reviewAttempted ? "Tracked positions refreshed and repriced." : "Tracked positions refreshed.");
      }
    } catch (err) {
      if (!isCurrentRequest()) return;
      console.error("Failed to load tracked positions:", err);
      const message = err instanceof Error ? err.message : "Failed to load tracked positions.";
      setOpenPositions([]);
      if (includeClosed) {
        setClosedPositions([]);
        setClosedPositionsLoaded(false);
        setClosedPositionsHasMore(false);
      }
      setPositionsError(message);
      if (notify) {
        toast.error(message);
      }
    } finally {
      if (isCurrentRequest()) {
        setPositionsLoading(false);
      }
    }
  }, [applyReviewedPositions, toast]);

  const fetchClosedPositionsPage = useCallback(async (options: ClosedPageOptions = {}) => {
    const append = options.append === true;
    const notify = options.notify === true;
    const requestId = ++closedPositionsRequestIdRef.current;
    const isCurrentRequest = () => requestId === closedPositionsRequestIdRef.current;
    const offset = append ? closedPositions.length : 0;
    setClosedPositionsLoadingMore(true);
    try {
      const res = await fetchWithTimeout(
        `/api/positions?status=closed&limit=${CLOSED_POSITION_PAGE_SIZE}&offset=${offset}&compact=1`,
        undefined,
        "Tracked closed positions"
      );
      const data = await readJsonResponseOrThrow<{ positions?: TrackedPosition[] }>(
        res,
        "Tracked closed positions"
      );
      if (!isCurrentRequest()) return;
      const nextClosedPositions = (data.positions || []) as TrackedPosition[];
      setClosedPositions((prev) =>
        append ? dedupeById([...prev, ...nextClosedPositions]) : nextClosedPositions
      );
      setClosedPositionsLoaded(true);
      setClosedPositionsHasMore(hasMorePage(data, CLOSED_POSITION_PAGE_SIZE));
      if (notify) {
        toast.success(append ? "More closed trades loaded." : "Closed trades loaded.");
      }
    } catch (err) {
      if (!isCurrentRequest()) return;
      const message = err instanceof Error ? err.message : "Failed to load closed tracked positions.";
      setPositionsError(message);
      if (notify) {
        toast.error(message);
      }
    } finally {
      if (isCurrentRequest()) {
        setClosedPositionsLoadingMore(false);
      }
    }
  }, [closedPositions.length, toast]);

  const fetchSuggestedTrades = useCallback(async (options: PositionLoadOptions = {}) => {
    const notify = options.notify === true;
    const shouldReview = options.review === "force";
    const includeClosed = options.includeClosed === true;
    const requestId = ++suggestedTradesRequestIdRef.current;
    const isCurrentRequest = () => requestId === suggestedTradesRequestIdRef.current;
    setSuggestedTradesLoading(true);
    try {
      const [openRes, closedRes] = await Promise.all([
        fetchWithTimeout("/api/suggested-trades?status=open&compact=1", undefined, "Open suggested trades"),
        includeClosed
          ? fetchWithTimeout(
              `/api/suggested-trades?status=closed&limit=${CLOSED_SUGGESTED_TRADE_PAGE_SIZE}&offset=0&compact=1`,
              undefined,
              "Closed suggested trades"
            )
          : Promise.resolve(null),
      ]);
      const data = await readJsonResponseOrThrow<{ trades?: SuggestedTrade[] }>(
        openRes,
        "Open suggested trades"
      );
      if (!isCurrentRequest()) return;
      const nextOpenTrades = (data.trades || []) as SuggestedTrade[];
      setOpenSuggestedTrades(nextOpenTrades);
      if (closedRes) {
        const closedData = await readJsonResponseOrThrow<{ trades?: SuggestedTrade[] }>(
          closedRes,
          "Closed suggested trades"
        );
        if (!isCurrentRequest()) return;
        const nextClosedTrades = (closedData.trades || []) as SuggestedTrade[];
        setClosedSuggestedTrades(nextClosedTrades);
        setClosedSuggestedTradesLoaded(true);
        setClosedSuggestedTradesHasMore(hasMorePage(closedData, CLOSED_SUGGESTED_TRADE_PAGE_SIZE));
      }
      setSuggestedTradesLoaded(true);
      setSuggestedTradesError(null);
      let reviewFailed = false;
      const reviewIds = shouldReview
        ? idsNeedingAutoReview(
            nextOpenTrades,
            suggestedTradesLastReviewedAtRef.current,
            { force: true }
          )
        : [];
      let reviewAttempted = false;
      if (reviewIds.length > 0 && !suggestedTradesReviewInFlightRef.current) {
        reviewAttempted = true;
        suggestedTradesReviewInFlightRef.current = true;
        try {
          const reviewRes = await fetchWithTimeout("/api/suggested-trades/review", {
            method: "POST",
            headers: tradingDeskMutationHeaders("review_suggested_trades"),
            body: JSON.stringify({ position_ids: reviewIds }),
          }, "Suggested trade review");
          const reviewData = await readJsonResponseOrThrow<{ trades?: SuggestedTrade[] }>(
            reviewRes,
            "Suggested trade review"
          );
          if (!isCurrentRequest()) return;
          const reviewedTrades = (reviewData.trades || []) as SuggestedTrade[];
          const reviewedAt = Date.now();
          reviewIds.forEach((id) => suggestedTradesLastReviewedAtRef.current.set(id, reviewedAt));
          reviewedTrades.forEach((trade) => suggestedTradesLastReviewedAtRef.current.set(trade.id, reviewedAt));
          applyReviewedSuggestedTrades(reviewedTrades);
        } catch (reviewErr) {
          if (!isCurrentRequest()) return;
          reviewFailed = true;
          const message = reviewErr instanceof Error ? reviewErr.message : "Failed to review suggested trades.";
          setSuggestedTradesError(`Suggested trades loaded, but repricing failed: ${message}`);
          if (notify) {
            toast.error(`Suggested trades loaded, but repricing failed: ${message}`);
          }
        } finally {
          suggestedTradesReviewInFlightRef.current = false;
        }
      }
      if (notify && !reviewFailed) {
        toast.success(reviewAttempted ? "Suggested trades refreshed and repriced." : "Suggested trades refreshed.");
      }
    } catch (err) {
      if (!isCurrentRequest()) return;
      console.error("Failed to load suggested trades:", err);
      const message = err instanceof Error ? err.message : "Failed to load suggested trades.";
      setOpenSuggestedTrades([]);
      if (includeClosed) {
        setClosedSuggestedTrades([]);
        setClosedSuggestedTradesLoaded(false);
        setClosedSuggestedTradesHasMore(false);
      }
      setSuggestedTradesError(message);
      if (notify) {
        toast.error(message);
      }
    } finally {
      if (isCurrentRequest()) {
        setSuggestedTradesLoading(false);
      }
    }
  }, [applyReviewedSuggestedTrades, toast]);

  const fetchClosedSuggestedTradesPage = useCallback(async (options: ClosedPageOptions = {}) => {
    const append = options.append === true;
    const notify = options.notify === true;
    const requestId = ++closedSuggestedTradesRequestIdRef.current;
    const isCurrentRequest = () => requestId === closedSuggestedTradesRequestIdRef.current;
    const offset = append ? closedSuggestedTrades.length : 0;
    setClosedSuggestedTradesLoadingMore(true);
    try {
      const res = await fetchWithTimeout(
        `/api/suggested-trades?status=closed&limit=${CLOSED_SUGGESTED_TRADE_PAGE_SIZE}&offset=${offset}&compact=1`,
        undefined,
        "Closed suggested trades"
      );
      const data = await readJsonResponseOrThrow<{ trades?: SuggestedTrade[] }>(
        res,
        "Closed suggested trades"
      );
      if (!isCurrentRequest()) return;
      const nextClosedTrades = (data.trades || []) as SuggestedTrade[];
      setClosedSuggestedTrades((prev) =>
        append ? dedupeById([...prev, ...nextClosedTrades]) : nextClosedTrades
      );
      setClosedSuggestedTradesLoaded(true);
      setClosedSuggestedTradesHasMore(hasMorePage(data, CLOSED_SUGGESTED_TRADE_PAGE_SIZE));
      if (notify) {
        toast.success(append ? "More closed paper ideas loaded." : "Closed paper ideas loaded.");
      }
    } catch (err) {
      if (!isCurrentRequest()) return;
      const message = err instanceof Error ? err.message : "Failed to load closed suggested trades.";
      setSuggestedTradesError(message);
      if (notify) {
        toast.error(message);
      }
    } finally {
      if (isCurrentRequest()) {
        setClosedSuggestedTradesLoadingMore(false);
      }
    }
  }, [closedSuggestedTrades.length, toast]);

  const reviewSinglePosition = useCallback(async (positionId: number) => {
    setReviewingIds((prev) => [...prev, positionId]);
    try {
      const res = await fetchWithTimeout("/api/positions/review", {
        method: "POST",
        headers: tradingDeskMutationHeaders("review_tracked_positions"),
        body: JSON.stringify({ position_ids: [positionId] }),
      }, "Tracked position review");
      const data = await readJsonResponseOrThrow<{ positions?: TrackedPosition[] }>(
        res,
        "Tracked position review"
      );
      applyReviewedPositions((data.positions || []) as TrackedPosition[]);
      toast.success("Position reviewed.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to review position.");
    } finally {
      setReviewingIds((prev) => prev.filter((id) => id !== positionId));
    }
  }, [applyReviewedPositions, toast]);

  const reviewSingleSuggestedTrade = useCallback(async (positionId: number) => {
    setReviewingSuggestedTradeIds((prev) => [...prev, positionId]);
    try {
      const res = await fetchWithTimeout("/api/suggested-trades/review", {
        method: "POST",
        headers: tradingDeskMutationHeaders("review_suggested_trades"),
        body: JSON.stringify({ position_ids: [positionId] }),
      }, "Suggested trade review");
      const data = await readJsonResponseOrThrow<{ trades?: SuggestedTrade[] }>(
        res,
        "Suggested trade review"
      );
      applyReviewedSuggestedTrades((data.trades || []) as SuggestedTrade[]);
      toast.success("Suggested trade reviewed.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to review suggested trade.");
    } finally {
      setReviewingSuggestedTradeIds((prev) => prev.filter((id) => id !== positionId));
    }
  }, [applyReviewedSuggestedTrades, toast]);

  return {
    openPositions,
    closedPositions,
    openSuggestedTrades,
    closedSuggestedTrades,
    closedPositionsLoaded,
    closedPositionsHasMore,
    closedPositionsLoadingMore,
    closedSuggestedTradesLoaded,
    closedSuggestedTradesHasMore,
    closedSuggestedTradesLoadingMore,
    positionsLoaded,
    positionsLoading,
    positionsError,
    suggestedTradesLoaded,
    suggestedTradesLoading,
    suggestedTradesError,
    reviewingIds,
    reviewingSuggestedTradeIds,
    fetchPositions,
    fetchClosedPositionsPage,
    fetchSuggestedTrades,
    fetchClosedSuggestedTradesPage,
    reviewSinglePosition,
    reviewSingleSuggestedTrade,
    mergeTrackedPosition,
    mergeSuggestedTrade,
  };
}
