"use client";

import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import dynamic from "next/dynamic";
import { RefreshCw, Timer, CheckCircle, BarChart3, DollarSign, Map, BriefcaseBusiness, Clipboard, LineChart, type LucideIcon } from "lucide-react";
import MetricCard from "@/components/ui/MetricCard";
import Button from "@/components/ui/Button";
import { MetricGridSkeleton, TableSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useSubmitGuard } from "@/lib/hooks";
import { fetchWithTimeout, readJsonResponseOrThrow } from "@/lib/client-json";
import {
  BreakdownTab,
  GradedTab,
  PendingTab,
  SectorsTab,
  SimTab,
} from "@/components/predictions/legacy-tabs";
import {
  buildTrackedStockSummaries,
  TrackedStocksTab,
} from "@/components/predictions/TrackedStocksTab";
import {
  TrackedPaperPositionsTab,
  isAlpacaPaperTrackedPosition,
} from "@/components/predictions/TrackedPaperPositionsTab";
import { TrackedPositionsTab } from "@/components/predictions/TrackedPositionsTab";
import { CloseTradeModal } from "@/components/predictions/CloseTradeModal";
import {
  buildContractSignature,
} from "@/components/predictions/trackedPositionUtils";
import { useTradingDeskCloseDialogs } from "@/components/predictions/useTradingDeskCloseDialogs";
import { useScannerSurface } from "@/components/predictions/useScannerSurface";
import { useTradingDeskRecords } from "@/components/predictions/useTradingDeskRecords";
import type {
  Prediction,
  ScanPick,
  SectorSentiment,
  SuggestedTrade,
  TrackedPosition,
} from "@/lib/types";
import type {
  CreateSuggestedTradeRequest,
  CreateSuggestedTradeResponse,
  CreateTrackedPositionRequest,
  CreateTrackedPositionResponse,
} from "@/lib/trading-desk/apiContracts";
import { tradingDeskMutationHeaders } from "@/lib/trading-desk/mutationIntent";
import {
  isLegacyPredictionTabId,
  resolveTradingDeskVisibleTab,
  toTradingDeskVisibleTabId,
  type TradingDeskPositionsView,
  type TradingDeskSubTabId,
  type TradingDeskVisibleTabId,
} from "@/components/predictions/tradingDeskTabs";

const INDEX_TICKERS = new Set(["QQQ", "SPY", "IWM", "DIA", "XLK"]);
const POSITION_SYNC_INTERVAL_MS = 60000;

type TradingDeskTabButton = {
  id: TradingDeskVisibleTabId;
  label: string;
  icon: LucideIcon;
};

const SuggestedTradesTab = dynamic(
  () => import("@/components/predictions/SuggestedTradesTab").then((mod) => mod.SuggestedTradesTab),
  { loading: () => <TableSkeleton rows={6} /> }
);

const ScannerTab = dynamic(
  () => import("@/components/predictions/ScannerTab").then((mod) => mod.ScannerTab),
  { loading: () => <TableSkeleton rows={6} /> }
);

export default function PredictionsView() {
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [sectors, setSectors] = useState<SectorSentiment[]>([]);
  const [activeSubTab, setActiveSubTab] = useState<TradingDeskSubTabId>("positions");
  const [loading, setLoading] = useState(true);
  const [grading, setGrading] = useState(false);
  const [predictionsLoaded, setPredictionsLoaded] = useState(false);
  const [sectorsLoaded, setSectorsLoaded] = useState(false);
  const [predictionsError, setPredictionsError] = useState<string | null>(null);
  const [sectorsError, setSectorsError] = useState<string | null>(null);
  const [selectedPick, setSelectedPick] = useState<ScanPick | null>(null);
  const [fillPrice, setFillPrice] = useState("");
  const [contracts, setContracts] = useState("1");
  const [takeNotes, setTakeNotes] = useState("");
  const [takingTrade, setTakingTrade] = useState(false);
  const [savingSuggestedTrade, setSavingSuggestedTrade] = useState(false);
  const [submittingAlpacaPaperOrder, setSubmittingAlpacaPaperOrder] = useState(false);
  const [showLegacyTabs, setShowLegacyTabs] = useState(false);
  const [positionsView, setPositionsView] = useState<TradingDeskPositionsView>("open");
  const [suggestedTradesView, setSuggestedTradesView] = useState<TradingDeskPositionsView>("open");
  const toast = useToast();
  const { guard } = useSubmitGuard();
  const {
    scanPicks,
    scanPolicy,
    scanPolicyError,
    scanDecisionCounts,
    guardrailDecisionCounts,
    scanExitAudit,
    scanCandidateCount,
    forwardEvidence,
    optionsProfitStatus,
    truthHealthError,
    useRecommendedPolicy,
    setUseRecommendedPolicy,
    scanPlaybook,
    setScanPlaybook,
    showBlockedIdeas,
    setShowBlockedIdeas,
    availablePlaybooks,
    exposureSnapshot,
    scanLoading,
    refreshScannerSurface,
  } = useScannerSurface();
  const {
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
  } = useTradingDeskRecords();
  const {
    openCloseForm,
    openCloseSuggestedTradeForm,
    trackedCloseModalProps,
    suggestedCloseModalProps,
  } = useTradingDeskCloseDialogs({
    guard,
    toast,
    mergeTrackedPosition,
    mergeSuggestedTrade,
    fetchPositions,
    fetchSuggestedTrades,
  });
  const predictionDataRequestIdRef = useRef(0);

  const fetchPredictionsData = useCallback(async ({
    includePredictions = true,
    includeSectors = false,
    showToast = false,
  }: {
    includePredictions?: boolean;
    includeSectors?: boolean;
    showToast?: boolean;
  } = {}) => {
    const requestId = ++predictionDataRequestIdRef.current;
    const isCurrentRequest = () => requestId === predictionDataRequestIdRef.current;
    const errors: string[] = [];

    if (includePredictions) {
      try {
        const predRes = await fetchWithTimeout("/api/predictions", undefined, "Prediction history");
        const predData = await readJsonResponseOrThrow(predRes, "Prediction history");
        if (!Array.isArray(predData)) {
          throw new Error("Prediction history response was not a list.");
        }
        if (!isCurrentRequest()) return;
        setPredictions(predData as Prediction[]);
        setPredictionsLoaded(true);
        setPredictionsError(null);
      } catch (err) {
        if (!isCurrentRequest()) return;
        const message = err instanceof Error ? err.message : "Failed to load prediction history.";
        console.error("Failed to load prediction history:", err);
        setPredictions([]);
        setPredictionsLoaded(false);
        setPredictionsError(message);
        errors.push(message);
      }
    }

    if (includeSectors) {
      try {
        const sectorRes = await fetchWithTimeout("/api/sectors", undefined, "Sector data");
        const sectorData = await readJsonResponseOrThrow(sectorRes, "Sector data");
        if (!Array.isArray(sectorData)) {
          throw new Error("Sector data response was not a list.");
        }
        if (!isCurrentRequest()) return;
        setSectors(sectorData as SectorSentiment[]);
        setSectorsLoaded(true);
        setSectorsError(null);
      } catch (err) {
        if (!isCurrentRequest()) return;
        const message = err instanceof Error ? err.message : "Failed to load sector data.";
        console.error("Failed to load sector data:", err);
        setSectors([]);
        setSectorsLoaded(false);
        setSectorsError(message);
        errors.push(message);
      }
    }

    if (showToast && errors.length > 0) {
      toast.error(errors.join(" "));
    }
  }, [toast]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        await fetchPositions();
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };
    void load();
    return () => {
      mounted = false;
    };
  }, [fetchPositions]);

  useEffect(() => {
    if (!isLegacyPredictionTabId(activeSubTab)) return;
    const includePredictions = !predictionsLoaded;
    const includeSectors = activeSubTab === "sectors" && !sectorsLoaded;
    if (!includePredictions && !includeSectors) return;
    void fetchPredictionsData({ includePredictions, includeSectors });
  }, [activeSubTab, fetchPredictionsData, predictionsLoaded, sectorsLoaded]);

  useEffect(() => {
    if (activeSubTab !== "scanner") return;
    void refreshScannerSurface(false);
  }, [activeSubTab, refreshScannerSurface]);

  useEffect(() => {
    if (loading || !["positions", "tracked-stocks", "paper-track"].includes(activeSubTab) || positionsLoaded) return;
    void fetchPositions();
  }, [activeSubTab, fetchPositions, loading, positionsLoaded]);

  useEffect(() => {
    const needsClosedPositions =
      (activeSubTab === "positions" && positionsView === "closed") ||
      activeSubTab === "tracked-stocks" ||
      activeSubTab === "paper-track";
    if (!needsClosedPositions || closedPositionsLoaded) return;
    void fetchClosedPositionsPage();
  }, [activeSubTab, closedPositionsLoaded, fetchClosedPositionsPage, positionsView]);

  useEffect(() => {
    if (activeSubTab !== "suggestions" || suggestedTradesLoaded) return;
    void fetchSuggestedTrades();
  }, [activeSubTab, fetchSuggestedTrades, suggestedTradesLoaded]);

  useEffect(() => {
    if (activeSubTab !== "suggestions" || suggestedTradesView !== "closed" || closedSuggestedTradesLoaded) return;
    void fetchClosedSuggestedTradesPage();
  }, [activeSubTab, closedSuggestedTradesLoaded, fetchClosedSuggestedTradesPage, suggestedTradesView]);

  useEffect(() => {
    if (!showLegacyTabs && (isLegacyPredictionTabId(activeSubTab) || activeSubTab === "suggestions" || activeSubTab === "scanner")) {
      setPositionsView("open");
      setActiveSubTab("positions");
    }
  }, [activeSubTab, showLegacyTabs]);

  useEffect(() => {
    if (!["positions", "tracked-stocks", "paper-track"].includes(activeSubTab)) return;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      void fetchPositions();
    }, POSITION_SYNC_INTERVAL_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [activeSubTab, fetchPositions]);

  useEffect(() => {
    if (activeSubTab !== "suggestions") return;
    const intervalId = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      void fetchSuggestedTrades();
    }, POSITION_SYNC_INTERVAL_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [activeSubTab, fetchSuggestedTrades]);

  const openTakeTrade = useCallback((pick: ScanPick) => {
    setSelectedPick(pick);
    const premium = pick.premium ?? pick.est_premium ?? 0;
    setFillPrice(premium > 0 ? premium.toFixed(2) : "");
    setContracts("1");
    const defaultReasons = [
      ...(pick.policy_fit_reasons || []),
      ...(pick.guardrail_reasons || []),
    ];
    const defaultNote = pick.policy_decision === "watch" || pick.guardrail_decision === "caution"
      ? `Cautious entry: ${defaultReasons.join(" | ") || "manual review"}`
      : "";
    setTakeNotes(defaultNote);
  }, []);

  const cancelTakeTrade = useCallback(() => {
    setSelectedPick(null);
    setFillPrice("");
    setContracts("1");
    setTakeNotes("");
  }, []);

  const submitTakeTrade = async () => {
    if (!selectedPick) return;
    const nextSignature = buildContractSignature({
      ...selectedPick,
      source_pick_snapshot: selectedPick,
    });
    const existingOpenPosition = openPositions.find((position) => buildContractSignature(position) === nextSignature);
    if (existingOpenPosition) {
      setActiveSubTab("positions");
      setPositionsView("open");
      toast.error("That contract is already open in tracked positions.");
      return;
    }
    await guard(async () => {
      setTakingTrade(true);
      try {
        const payload: CreateTrackedPositionRequest = {
          scan_pick: selectedPick,
          fill_price: Number(fillPrice),
          contracts: Number(contracts),
          notes: takeNotes || undefined,
        };
        const res = await fetchWithTimeout("/api/positions", {
          method: "POST",
          headers: tradingDeskMutationHeaders("create_tracked_position"),
          body: JSON.stringify(payload),
        }, "Create tracked position");
        const data = await readJsonResponseOrThrow<CreateTrackedPositionResponse>(res, "Create tracked position");
        if (data.position) {
          mergeTrackedPosition(data.position as TrackedPosition);
        }
        cancelTakeTrade();
        setPositionsView("open");
        setActiveSubTab("positions");
        toast.success(data.duplicate ? "Open tracked position already exists." : "Tracked position saved.");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to track position.");
      } finally {
        setTakingTrade(false);
      }
    });
  };

  const submitAlpacaPaperTrade = async () => {
    if (!selectedPick) return;
    if (Number(contracts) !== 1) {
      toast.error("Alpaca paper orders are capped at exactly 1 contract.");
      return;
    }
    const nextSignature = buildContractSignature({
      ...selectedPick,
      source_pick_snapshot: selectedPick,
    });
    const existingOpenPosition = openPositions.find((position) => buildContractSignature(position) === nextSignature);
    if (existingOpenPosition) {
      setActiveSubTab(isAlpacaPaperTrackedPosition(existingOpenPosition) ? "paper-track" : "positions");
      setPositionsView("open");
      toast.error("That contract is already open in tracked positions.");
      return;
    }
    await guard(async () => {
      setSubmittingAlpacaPaperOrder(true);
      try {
        const payload: CreateTrackedPositionRequest = {
          scan_pick: selectedPick,
          fill_price: Number(fillPrice),
          contracts: 1,
          notes: takeNotes || undefined,
          creation_mode: "scanner",
          execute_alpaca_paper: true,
        };
        const res = await fetchWithTimeout("/api/positions", {
          method: "POST",
          headers: tradingDeskMutationHeaders("create_tracked_position"),
          body: JSON.stringify(payload),
        }, "Submit Alpaca paper order");
        const data = await readJsonResponseOrThrow<CreateTrackedPositionResponse>(res, "Submit Alpaca paper order");
        if (data.position) {
          mergeTrackedPosition(data.position as TrackedPosition);
        }
        cancelTakeTrade();
        setPositionsView("open");
        setActiveSubTab("paper-track");
        const orderStatus = String(data.position?.source_pick_snapshot?.alpaca_paper_order?.status || "submitted").replaceAll("_", " ");
        toast.success(data.duplicate ? "Open tracked position already exists." : `Alpaca paper order ${orderStatus}.`);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to submit Alpaca paper order.");
      } finally {
        setSubmittingAlpacaPaperOrder(false);
      }
    });
  };

  const submitSuggestedTrade = async () => {
    if (!selectedPick) return;
    const nextSignature = buildContractSignature({
      ...selectedPick,
      source_pick_snapshot: selectedPick,
    });
    const existingSuggestedTrade = openSuggestedTrades.find((trade) => buildContractSignature(trade) === nextSignature);
    if (existingSuggestedTrade) {
      setShowLegacyTabs(true);
      setActiveSubTab("suggestions");
      setSuggestedTradesView("open");
      toast.error("That contract is already open in suggested trades.");
      return;
    }
    await guard(async () => {
      setSavingSuggestedTrade(true);
      try {
        const payload: CreateSuggestedTradeRequest = {
          scan_pick: selectedPick,
          fill_price: Number(fillPrice),
          contracts: Number(contracts),
          notes: takeNotes || undefined,
        };
        const res = await fetchWithTimeout("/api/suggested-trades", {
          method: "POST",
          headers: tradingDeskMutationHeaders("create_suggested_trade"),
          body: JSON.stringify(payload),
        }, "Create suggested trade");
        const data = await readJsonResponseOrThrow<CreateSuggestedTradeResponse>(res, "Create suggested trade");
        if (data.trade) {
          mergeSuggestedTrade(data.trade as SuggestedTrade);
        }
        cancelTakeTrade();
        setShowLegacyTabs(true);
        setSuggestedTradesView("open");
        setActiveSubTab("suggestions");
        toast.success(data.duplicate ? "Open suggested trade already exists." : "Suggested trade saved.");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to save suggested trade.");
      } finally {
        setSavingSuggestedTrade(false);
      }
    });
  };

  const scanPreds = useMemo(
    () => predictions.filter((p) => p.type === "daily_scan"),
    [predictions]
  );
  const graded = useMemo(
    () => scanPreds.filter((p) => p.outcome),
    [scanPreds]
  );
  const pending = useMemo(
    () => scanPreds.filter((p) => !p.outcome),
    [scanPreds]
  );
  const hits = useMemo(
    () => graded.filter((p) => p.outcome === "hit"),
    [graded]
  );
  const dirOk = useMemo(
    () => graded.filter((p) => p.outcome === "hit" || p.outcome === "directional"),
    [graded]
  );
  const callAcc = useMemo(() => {
    const callGraded = graded.filter((p) => p.direction === "call");
    return callGraded.length > 0
      ? ((callGraded.filter((p) => p.outcome === "hit" || p.outcome === "directional").length / (callGraded.length || 1)) * 100).toFixed(1)
      : "\u2014";
  }, [graded]);
  const putAcc = useMemo(() => {
    const putGraded = graded.filter((p) => p.direction === "put");
    return putGraded.length > 0
      ? ((putGraded.filter((p) => p.outcome === "hit" || p.outcome === "directional").length / (putGraded.length || 1)) * 100).toFixed(1)
      : "\u2014";
  }, [graded]);
  const trackedStockSummaries = useMemo(
    () => buildTrackedStockSummaries(openPositions, closedPositions),
    [closedPositions, openPositions]
  );
  const paperTrackedPositions = useMemo(
    () => [...openPositions, ...closedPositions].filter(isAlpacaPaperTrackedPosition),
    [closedPositions, openPositions]
  );
  const trackedStockCount = trackedStockSummaries.length;
  const closedPositionCountLabel = closedPositionsLoaded
    ? `Closed (${closedPositions.length}${closedPositionsHasMore ? "+" : ""})`
    : "Closed";
  const trackedStockCountLabel =
    closedPositionsLoaded && closedPositionsHasMore
      ? `Tracked Stocks (${trackedStockCount}+)`
      : `Tracked Stocks (${trackedStockCount})`;
  const paperTrackedCountLabel =
    closedPositionsLoaded && closedPositionsHasMore
      ? `Paper Track (${paperTrackedPositions.length}+)`
      : `Paper Track (${paperTrackedPositions.length})`;

  const PRIMARY_SUB_TABS = [
    { id: "positions", label: `Open (${openPositions.length})`, icon: BriefcaseBusiness },
    { id: "closed-trades", label: closedPositionCountLabel, icon: CheckCircle },
    { id: "paper-track", label: paperTrackedCountLabel, icon: LineChart },
    { id: "tracked-stocks", label: trackedStockCountLabel, icon: Map },
  ] as const satisfies readonly TradingDeskTabButton[];
  const LEGACY_SUB_TABS = [
    { id: "scanner", label: `Live Scan (${scanPicks.length})`, icon: RefreshCw },
    { id: "suggestions", label: `Paper (${openSuggestedTrades.length})`, icon: Clipboard },
    { id: "pending", label: `Archive Active (${pending.length})`, icon: Timer },
    { id: "graded", label: `Archive Graded (${graded.length})`, icon: CheckCircle },
    { id: "breakdown", label: "Breakdown", icon: BarChart3 },
    { id: "sim", label: "Portfolio Sim", icon: DollarSign },
    { id: "sectors", label: "Sectors", icon: Map },
  ] as const satisfies readonly TradingDeskTabButton[];
  const SUB_TABS: readonly TradingDeskTabButton[] = showLegacyTabs
    ? [...PRIMARY_SUB_TABS, ...LEGACY_SUB_TABS]
    : PRIMARY_SUB_TABS;
  const activeSubTabId = toTradingDeskVisibleTabId(activeSubTab, positionsView);
  const activateVisibleTab = (tabId: TradingDeskVisibleTabId) => {
    const nextTab = resolveTradingDeskVisibleTab(tabId);
    if (nextTab.positionsView) setPositionsView(nextTab.positionsView);
    setActiveSubTab(nextTab.activeSubTab);
  };
  const legacyDataError = isLegacyPredictionTabId(activeSubTab)
    ? predictionsError || (activeSubTab === "sectors" ? sectorsError : null)
    : null;

  if (loading) {
    return (
      <div className="px-4 md:px-6 xl:px-8 py-5 max-w-[96vw] xl:max-w-[1800px] mx-auto space-y-5">
        <MetricGridSkeleton count={5} />
        <TableSkeleton rows={6} />
      </div>
    );
  }

  return (
    <div className="px-4 md:px-6 xl:px-8 py-5 max-w-[96vw] xl:max-w-[1800px] mx-auto">
      {isLegacyPredictionTabId(activeSubTab) && (
        <div className="space-y-6 mb-6">
          <div className="bg-bg-2 border border-border rounded-lg px-4 py-3 text-sm text-text-2">
            These legacy prediction analytics are archival scanner research, not the current supervised tracked-position workflow.
          </div>
          {legacyDataError ? (
            <div className="bg-red-dim border border-red/30 rounded-lg px-4 py-3 text-sm text-red">
              {legacyDataError}
            </div>
          ) : null}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <MetricCard label="Total Picks" value={String(scanPreds.length)} />
            <MetricCard label="Active Trades" value={String(pending.length)} />
            <MetricCard
              label="Hit Rate"
              value={graded.length > 0 ? `${((hits.length / (graded.length || 1)) * 100).toFixed(1)}%` : "\u2014"}
              help="Direction correct AND magnitude >= 50% of target"
            />
            <MetricCard
              label="Directional"
              value={graded.length > 0 ? `${((dirOk.length / (graded.length || 1)) * 100).toFixed(1)}%` : "\u2014"}
              help="% where direction was correct regardless of magnitude"
            />
            <MetricCard
              label="Call/Put Acc"
              value={`${callAcc}% / ${putAcc}%`}
              help="Directional accuracy for call vs put picks"
            />
          </div>
        </div>
      )}

      {graded.length > 0 && isLegacyPredictionTabId(activeSubTab) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          {["index", "equity"].map((assetClass) => {
            const subset = graded.filter((p) =>
              assetClass === "index"
                ? INDEX_TICKERS.has(p.ticker?.toUpperCase())
                : !INDEX_TICKERS.has(p.ticker?.toUpperCase())
            );
            const wins = subset.filter((p) => p.outcome === "hit" || p.outcome === "directional");
            const pnls = subset
              .map((p) => p.option_gain_pct)
              .filter((v): v is number => v != null);
            const avgPnl = pnls.length > 0
              ? (pnls.reduce((a, b) => a + b, 0) / (pnls.length || 1)).toFixed(1)
              : "\u2014";
            const iconChar = assetClass === "index" ? "\uD83D\uDCCA" : "\uD83D\uDCC8";
            const label = assetClass === "index" ? "Index picks" : "Equity picks";
            return (
              <div key={assetClass} className="bg-bg-2 border border-border rounded-lg p-4">
                <div className="text-sm font-semibold text-text-0 mb-2">
                  <span aria-hidden="true">{iconChar}</span>
                  <span className="sr-only">{label}</span>{" "}
                  {label}
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <MetricCard
                    label="Win Rate"
                    value={subset.length > 0 ? `${((wins.length / (subset.length || 1)) * 100).toFixed(1)}%` : "\u2014"}
                  />
                  <MetricCard
                    label="Avg Option P&L"
                    value={avgPnl === "\u2014" ? "\u2014" : `${avgPnl}%`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      <div className="mb-4 flex flex-col gap-3 border-b border-border pb-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-text-0">Trading Desk</h1>
          <p className="mt-1 text-sm text-text-2">
            Review open risk first, then monitor the tracked stock list.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowLegacyTabs((prev) => !prev)}
          >
            {showLegacyTabs ? "Hide Archive" : "Archive"}
          </Button>
          {isLegacyPredictionTabId(activeSubTab) && (
            <Button
              variant="secondary"
              size="sm"
              loading={grading}
              icon={<RefreshCw size={12} />}
              onClick={async () => {
                await guard(async () => {
                  setGrading(true);
                  try {
                    const response = await fetchWithTimeout("/api/predictions/grade", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({}),
                    }, "Grade predictions");
                    await readJsonResponseOrThrow(response, "Grade predictions");
                    await fetchPredictionsData({
                      includePredictions: true,
                      includeSectors: activeSubTab === "sectors" && !sectorsLoaded,
                    });
                    toast.success("Predictions graded successfully.");
                  } catch (err) {
                    console.error("Failed to grade predictions:", err);
                    toast.error("Failed to grade predictions. Please try again.");
                  } finally {
                    setGrading(false);
                  }
                });
              }}
              aria-label="Grade all predictions"
            >
              {grading ? "Grading..." : "Grade All"}
            </Button>
          )}
        </div>
      </div>

      <div className="mb-4 flex items-center gap-1 overflow-x-auto rounded-lg border border-border bg-bg-2 p-1" role="tablist" aria-label="Trading desk views">
        {SUB_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive =
            tab.id === "positions"
              ? activeSubTab === "positions" && positionsView === "open"
              : tab.id === "closed-trades"
                ? activeSubTab === "positions" && positionsView === "closed"
                : activeSubTab === tab.id;
          return (
            <button
              key={tab.id}
              id={`${tab.id}-tab`}
              type="button"
              role="tab"
              aria-selected={isActive}
              aria-controls={`${tab.id}-panel`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => {
                activateVisibleTab(tab.id);
              }}
              onKeyDown={(event) => {
                const tabIds = SUB_TABS.map((item) => item.id);
                const currentIndex = tabIds.indexOf(activeSubTabId as (typeof tabIds)[number]);
                let nextIndex: number | null = null;
                if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabIds.length;
                if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabIds.length) % tabIds.length;
                if (event.key === "Home") nextIndex = 0;
                if (event.key === "End") nextIndex = tabIds.length - 1;
                if (nextIndex == null) return;
                event.preventDefault();
                const nextTab = SUB_TABS[nextIndex];
                activateVisibleTab(nextTab.id);
                const buttons = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
                buttons?.[nextIndex]?.focus();
              }}
              className={`flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-all whitespace-nowrap ${
                isActive
                  ? "bg-accent-dim text-accent"
                  : "text-text-2 hover:bg-bg-3 hover:text-text-0"
              }`}
            >
              <Icon size={14} aria-hidden="true" />
              {tab.label}
            </button>
          );
        })}
      </div>

      <div id={`${activeSubTabId}-panel`} role="tabpanel" aria-labelledby={`${activeSubTabId}-tab`}>
        {activeSubTab === "scanner" && (
          <ScannerTab
            picks={scanPicks}
            loading={scanLoading}
            useRecommendedPolicy={useRecommendedPolicy}
            policy={scanPolicy}
            policyError={scanPolicyError}
            exitAudit={scanExitAudit}
            decisionCounts={scanDecisionCounts}
            guardrailCounts={guardrailDecisionCounts}
            candidateCount={scanCandidateCount}
            forwardEvidence={forwardEvidence}
            optionsProfitStatus={optionsProfitStatus}
            truthHealthError={truthHealthError}
            playbook={scanPlaybook}
            playbooks={availablePlaybooks}
            exposureSnapshot={exposureSnapshot}
            showBlockedIdeas={showBlockedIdeas}
            selectedPick={selectedPick}
            fillPrice={fillPrice}
            contracts={contracts}
            notes={takeNotes}
            takingTrade={takingTrade}
            savingSuggestedTrade={savingSuggestedTrade}
            submittingAlpacaPaperOrder={submittingAlpacaPaperOrder}
            onRefresh={() => void refreshScannerSurface(true)}
            onPolicyModeChange={setUseRecommendedPolicy}
            onPlaybookChange={setScanPlaybook}
            onShowBlockedIdeasChange={setShowBlockedIdeas}
            onPick={openTakeTrade}
            onCancel={cancelTakeTrade}
            onFillPriceChange={setFillPrice}
            onContractsChange={setContracts}
            onNotesChange={setTakeNotes}
            onSubmit={() => void submitTakeTrade()}
            onSubmitSuggested={() => void submitSuggestedTrade()}
            onSubmitAlpacaPaper={() => void submitAlpacaPaperTrade()}
          />
        )}
        {activeSubTab === "suggestions" && (
          <SuggestedTradesTab
            openTrades={openSuggestedTrades}
            closedTrades={closedSuggestedTrades}
            loading={suggestedTradesLoading}
            error={suggestedTradesError}
            view={suggestedTradesView}
            reviewingIds={reviewingSuggestedTradeIds}
            closedRowsLoaded={closedSuggestedTradesLoaded}
            closedRowsHasMore={closedSuggestedTradesHasMore}
            closedRowsLoading={closedSuggestedTradesLoadingMore}
            onViewChange={setSuggestedTradesView}
            onRefresh={() => void fetchSuggestedTrades({
              notify: true,
              review: "force",
              includeClosed: suggestedTradesView === "closed",
            })}
            onLoadClosedRows={() => void fetchClosedSuggestedTradesPage({ append: true, notify: true })}
            onReviewTrade={(positionId) => void reviewSingleSuggestedTrade(positionId)}
            onOpenClose={openCloseSuggestedTradeForm}
          />
        )}
        {activeSubTab === "tracked-stocks" && (
          <TrackedStocksTab
            summaries={trackedStockSummaries}
            openPositionCount={openPositions.length}
            closedPositionCount={closedPositions.length}
            loading={positionsLoading}
            error={positionsError}
            closedRowsLoaded={closedPositionsLoaded}
            closedRowsHasMore={closedPositionsHasMore}
            onRefresh={() => void fetchPositions({ notify: true, review: "force" })}
          />
        )}
        {activeSubTab === "paper-track" && (
          <TrackedPaperPositionsTab
            openPositions={openPositions}
            closedPositions={closedPositions}
            loading={positionsLoading}
            error={positionsError}
            closedRowsLoaded={closedPositionsLoaded}
            closedRowsHasMore={closedPositionsHasMore}
            onRefresh={() => void fetchPositions({
              notify: true,
              review: "force",
              includeClosed: true,
            })}
          />
        )}
        {activeSubTab === "positions" && (
          <TrackedPositionsTab
            openPositions={openPositions}
            closedPositions={closedPositions}
            loading={positionsLoading}
            error={positionsError}
            view={positionsView}
            reviewingIds={reviewingIds}
            closedRowsLoaded={closedPositionsLoaded}
            closedRowsHasMore={closedPositionsHasMore}
            closedRowsLoading={closedPositionsLoadingMore}
            onRefresh={() => void fetchPositions({
              notify: true,
              review: "force",
              includeClosed: positionsView === "closed",
            })}
            onLoadClosedRows={(options) => void fetchClosedPositionsPage({
              append: true,
              notify: options?.notify === true,
            })}
            onReviewPosition={(positionId) => void reviewSinglePosition(positionId)}
            onOpenClose={openCloseForm}
          />
        )}
        {activeSubTab === "pending" && <PendingTab predictions={pending} />}
        {activeSubTab === "graded" && <GradedTab predictions={graded} />}
        {activeSubTab === "breakdown" && <BreakdownTab predictions={graded} />}
        {activeSubTab === "sim" && <SimTab predictions={scanPreds} />}
        {activeSubTab === "sectors" && (
          <SectorsTab
            sectors={sectors}
            loading={!sectorsLoaded && !sectorsError}
            error={sectorsError}
          />
        )}
      </div>

      <CloseTradeModal {...trackedCloseModalProps} />

      <CloseTradeModal {...suggestedCloseModalProps} />
    </div>
  );
}
