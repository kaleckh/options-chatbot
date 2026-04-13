"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { RefreshCw, Timer, CheckCircle, BarChart3, DollarSign, Map, Search, BriefcaseBusiness, Clipboard } from "lucide-react";
import MetricCard from "@/components/ui/MetricCard";
import FinTable from "@/components/ui/FinTable";
import SentimentBadge from "@/components/ui/SentimentBadge";
import Button from "@/components/ui/Button";
import { MetricGridSkeleton, TableSkeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { useSubmitGuard } from "@/lib/hooks";
import type {
  CloseSuggestedTradeRequest,
  CloseTrackedPositionRequest,
  CreateSuggestedTradeRequest,
  CreateTrackedPositionRequest,
  ExposureSnapshot,
  ForwardEvidenceReport,
  LiveTradePolicy,
  OptionsProfitStatus,
  PlaybookExitAudit,
  Prediction,
  ScanPick,
  ScanPlaybook,
  SectorSentiment,
  SuggestedTrade,
  TrackedPosition,
} from "@/lib/types";

const INDEX_TICKERS = new Set(["QQQ", "SPY", "IWM", "DIA", "XLK"]);
const LEGACY_PREDICTION_TABS = new Set(["pending", "graded", "breakdown", "sim", "sectors"]);
const REQUEST_TIMEOUT_MS = 30000;
const POSITION_SYNC_INTERVAL_MS = 60000;

function buildTimeoutError(label: string, timeoutMs: number): Error {
  return new Error(`${label} timed out after ${Math.round(timeoutMs / 1000)}s.`);
}

async function fetchWithTimeout(
  input: RequestInfo | URL,
  init: RequestInit | undefined,
  label: string,
  timeoutMs: number = REQUEST_TIMEOUT_MS
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw buildTimeoutError(label, timeoutMs);
    }
    throw error;
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function fmtMoney(value?: number | null, digits: number = 2): string {
  if (value == null || Number.isNaN(value)) return "\u2014";
  return `$${value.toFixed(digits)}`;
}

function fmtPct(value?: number | null, digits: number = 1): string {
  if (value == null || Number.isNaN(value)) return "\u2014";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

function fmtDate(value?: string | null): string {
  return value ? value.slice(0, 10) : "\u2014";
}

function fmtContractLabel(position: {
  ticker: string;
  direction: "call" | "put";
  strike?: number | null;
  expiry?: string | null;
  contract_symbol?: string | null;
}): string {
  if (position.contract_symbol) return position.contract_symbol;
  const strike = position.strike != null ? fmtMoney(position.strike, 0) : "\u2014";
  return `${position.ticker} ${fmtDate(position.expiry)} ${strike} ${position.direction.toUpperCase()}`;
}

function fmtPricingSource(value?: string | null): string {
  if (!value) return "\u2014";
  if (value === "mid") return "Bid/ask midpoint";
  if (value === "last_price") return "Last trade only";
  if (value === "expired") return "Expired";
  if (value === "unavailable") return "Unpriced";
  return value;
}

function fmtTruthSource(value?: string | null): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "historical_imported_daily") return "Imported daily validation";
  if (normalized === "historical_imported") return "Imported historical validation";
  if (normalized === "synthetic" || normalized === "synthetic_only") return "Synthetic research-only";
  return value ? `Unknown truth source (${value})` : "Unknown truth source";
}

function fmtCompactLabel(value?: string | null): string {
  const normalized = String(value || "").trim();
  if (!normalized) return "\u2014";
  return normalized.replaceAll("_", " ");
}

function fmtUpperLabel(value?: string | null): string {
  const normalized = String(value || "").trim();
  if (!normalized) return "\u2014";
  return normalized.replaceAll("_", " ").toUpperCase();
}

function contractQualityLabel(pick?: Partial<ScanPick> | null): string {
  const selectionSource = String(pick?.selection_source || "").trim().toLowerCase();
  const promotionClass = String(pick?.promotion_class || "").trim().toLowerCase();
  if (String(pick?.contract_symbol || "").trim()) {
    if (selectionSource.includes("archived_exact") || selectionSource.includes("exact_contract")) {
      return "Exact contract";
    }
    if (selectionSource.includes("model_target") || promotionClass.includes("bootstrap") || promotionClass.includes("sparse")) {
      return "Model exact fallback";
    }
    if (selectionSource.includes("nearest") || promotionClass.includes("nearest")) {
      return "Nearest listed";
    }
    return "Exact symbol recorded";
  }
  if (selectionSource.includes("nearest") || promotionClass.includes("nearest")) {
    return "Nearest listed";
  }
  return "Contract missing";
}

function quoteContextLabel(pick?: Partial<ScanPick> | null): string {
  const basis = fmtCompactLabel(pick?.quote_basis);
  const freshness = fmtCompactLabel(pick?.quote_freshness_status);
  if (basis === "\u2014" && freshness === "\u2014") return "\u2014";
  if (basis === "\u2014") return freshness;
  if (freshness === "\u2014") return basis;
  return `${basis} / ${freshness}`;
}

function calcOptionPnlPct(entryPrice?: number | null, exitPrice?: number | null): number | null {
  if (entryPrice == null || exitPrice == null || entryPrice <= 0) return null;
  return ((exitPrice / entryPrice) - 1) * 100;
}

export default function PredictionsView() {
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [sectors, setSectors] = useState<SectorSentiment[]>([]);
  const [scanPicks, setScanPicks] = useState<ScanPick[]>([]);
  const [scanPolicy, setScanPolicy] = useState<LiveTradePolicy | null>(null);
  const [scanPolicyError, setScanPolicyError] = useState<string | null>(null);
  const [scanDecisionCounts, setScanDecisionCounts] = useState<Record<string, number> | null>(null);
  const [guardrailDecisionCounts, setGuardrailDecisionCounts] = useState<Record<string, number> | null>(null);
  const [scanExitAudit, setScanExitAudit] = useState<PlaybookExitAudit | null>(null);
  const [scanCandidateCount, setScanCandidateCount] = useState(0);
  const [forwardEvidence, setForwardEvidence] = useState<ForwardEvidenceReport | null>(null);
  const [optionsProfitStatus, setOptionsProfitStatus] = useState<OptionsProfitStatus | null>(null);
  const [truthHealthError, setTruthHealthError] = useState<string | null>(null);
  const [useRecommendedPolicy, setUseRecommendedPolicy] = useState(true);
  const [scanPlaybook, setScanPlaybook] = useState<string>("short_term");
  const [showBlockedIdeas, setShowBlockedIdeas] = useState(false);
  const [availablePlaybooks, setAvailablePlaybooks] = useState<ScanPlaybook[]>([]);
  const [exposureSnapshot, setExposureSnapshot] = useState<ExposureSnapshot | null>(null);
  const [openPositions, setOpenPositions] = useState<TrackedPosition[]>([]);
  const [closedPositions, setClosedPositions] = useState<TrackedPosition[]>([]);
  const [openSuggestedTrades, setOpenSuggestedTrades] = useState<SuggestedTrade[]>([]);
  const [closedSuggestedTrades, setClosedSuggestedTrades] = useState<SuggestedTrade[]>([]);
  const [activeSubTab, setActiveSubTab] = useState("scanner");
  const [loading, setLoading] = useState(true);
  const [grading, setGrading] = useState(false);
  const [scanLoading, setScanLoading] = useState(false);
  const [predictionsLoaded, setPredictionsLoaded] = useState(false);
  const [sectorsLoaded, setSectorsLoaded] = useState(false);
  const [positionsLoaded, setPositionsLoaded] = useState(false);
  const [positionsLoading, setPositionsLoading] = useState(false);
  const [positionsError, setPositionsError] = useState<string | null>(null);
  const [suggestedTradesLoaded, setSuggestedTradesLoaded] = useState(false);
  const [suggestedTradesLoading, setSuggestedTradesLoading] = useState(false);
  const [suggestedTradesError, setSuggestedTradesError] = useState<string | null>(null);
  const [selectedPick, setSelectedPick] = useState<ScanPick | null>(null);
  const [fillPrice, setFillPrice] = useState("");
  const [contracts, setContracts] = useState("1");
  const [takeNotes, setTakeNotes] = useState("");
  const [takingTrade, setTakingTrade] = useState(false);
  const [savingSuggestedTrade, setSavingSuggestedTrade] = useState(false);
  const [showLegacyTabs, setShowLegacyTabs] = useState(false);
  const [positionsView, setPositionsView] = useState<"open" | "closed">("open");
  const [reviewingIds, setReviewingIds] = useState<number[]>([]);
  const [closingPosition, setClosingPosition] = useState<TrackedPosition | null>(null);
  const [exitPrice, setExitPrice] = useState("");
  const [closeNotes, setCloseNotes] = useState("");
  const [closingId, setClosingId] = useState<number | null>(null);
  const [suggestedTradesView, setSuggestedTradesView] = useState<"open" | "closed">("open");
  const [reviewingSuggestedTradeIds, setReviewingSuggestedTradeIds] = useState<number[]>([]);
  const [closingSuggestedTrade, setClosingSuggestedTrade] = useState<SuggestedTrade | null>(null);
  const [suggestedExitPrice, setSuggestedExitPrice] = useState("");
  const [suggestedCloseNotes, setSuggestedCloseNotes] = useState("");
  const [closingSuggestedTradeId, setClosingSuggestedTradeId] = useState<number | null>(null);
  const toast = useToast();
  const { guard } = useSubmitGuard();

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
    setOpenPositions((prev) => prev.map((position) => reviewedById.get(position.id) ?? position));
  }, []);

  const applyReviewedSuggestedTrades = useCallback((reviewed: SuggestedTrade[]) => {
    const reviewedById = new globalThis.Map<number, SuggestedTrade>(
      reviewed.map((trade) => [trade.id, trade])
    );
    setOpenSuggestedTrades((prev) => prev.map((trade) => reviewedById.get(trade.id) ?? trade));
  }, []);

  const fetchPredictionsData = useCallback(async ({
    includePredictions = true,
    includeSectors = false,
    showToast = false,
  }: {
    includePredictions?: boolean;
    includeSectors?: boolean;
    showToast?: boolean;
  } = {}) => {
    try {
      const predRequest = includePredictions
        ? fetchWithTimeout("/api/predictions/history", undefined, "Prediction history")
        : null;
      const sectorRequest = includeSectors
        ? fetchWithTimeout("/api/sectors", undefined, "Sector data").catch(() => null)
        : null;

      const [predRes, sectorRes] = await Promise.all([predRequest, sectorRequest]);

      if (includePredictions && predRes) {
        const predData = await predRes.json();
        setPredictions(Array.isArray(predData) ? predData : []);
        setPredictionsLoaded(true);
      }

      if (includeSectors && sectorRes && sectorRes.ok) {
        setSectors(await sectorRes.json());
        setSectorsLoaded(true);
      }
    } catch (err) {
      console.error("Failed to load predictions:", err);
      if (showToast) {
        toast.error("Failed to load predictions. Please try again.");
      }
    }
  }, [toast]);

  const fetchScanner = useCallback(async (showToast = false) => {
    setScanLoading(true);
    try {
      const res = await fetchWithTimeout("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          n_picks: 2,
          use_recommended_policy: useRecommendedPolicy,
          playbook: scanPlaybook,
          include_blocked_policy_picks: showBlockedIdeas,
          include_blocked_guardrail_picks: showBlockedIdeas,
        }),
      }, "Live scan");
      const data = await res.json();
      if (!res.ok || data.error) {
        console.warn("Scan returned error:", data.error || res.status);
      }
      setScanPicks(data.picks || []);
      setScanPolicy(data.policy || null);
      setScanPolicyError(data.policy_error || null);
      setScanExitAudit(data.playbook_exit_audit || null);
      setScanDecisionCounts(data.policy_decision_counts || null);
      setGuardrailDecisionCounts(data.guardrail_decision_counts || null);
      setScanCandidateCount(Number(data.candidate_count || (data.picks || []).length || 0));
      setAvailablePlaybooks(data.playbooks || []);
      setExposureSnapshot(data.exposure_snapshot || null);
    } catch (err) {
      console.error("Failed to load scan picks:", err);
      const message = err instanceof Error ? err.message : "Failed to load scan picks.";
      setScanPicks([]);
      setScanPolicy(null);
      setScanPolicyError(message);
      setScanExitAudit(null);
      setScanDecisionCounts(null);
      setGuardrailDecisionCounts(null);
      setScanCandidateCount(0);
      setAvailablePlaybooks([]);
      setExposureSnapshot(null);
      if (showToast) {
        toast.error(message);
      }
    } finally {
      setScanLoading(false);
    }
  }, [showBlockedIdeas, toast, scanPlaybook, useRecommendedPolicy]);

  const fetchTruthHealth = useCallback(async (showToast = false) => {
    try {
      const [forwardRes, statusRes] = await Promise.all([
        fetchWithTimeout("/api/backtest/forward-evidence", undefined, "Forward evidence report"),
        fetchWithTimeout("/api/options-profit/status", undefined, "Options profit status"),
      ]);
      const forwardData = await forwardRes.json();
      const statusData = await statusRes.json();
      if (!forwardRes.ok || forwardData.error) {
        console.warn("Forward evidence not available:", forwardData.error || forwardRes.status);
      }
      if (!statusRes.ok || statusData.error) {
        console.warn("Options profit status not available:", statusData.error || statusRes.status);
      }
      setForwardEvidence((forwardData || null) as ForwardEvidenceReport | null);
      setOptionsProfitStatus((statusData || null) as OptionsProfitStatus | null);
      setTruthHealthError(null);
    } catch (err) {
      console.error("Failed to load truth health:", err);
      const message = err instanceof Error ? err.message : "Failed to load truth health.";
      setTruthHealthError(message);
      if (showToast) {
        toast.error(message);
      }
    }
  }, [toast]);

  const refreshScannerSurface = useCallback(async (showToast = false) => {
    await Promise.all([
      fetchScanner(showToast),
      fetchTruthHealth(showToast),
    ]);
  }, [fetchScanner, fetchTruthHealth]);

  const fetchPositions = useCallback(async (showToast = false) => {
    setPositionsLoading(true);
    try {
      const res = await fetchWithTimeout("/api/positions?status=all&grouped=1", undefined, "Tracked positions");
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error || "Failed to load tracked positions");
      }
      const nextOpenPositions = (data.open || []) as TrackedPosition[];
      setOpenPositions(nextOpenPositions);
      setClosedPositions((data.closed || []) as TrackedPosition[]);
      setPositionsLoaded(true);
      setPositionsError(null);
      if (nextOpenPositions.length > 0) {
        const reviewRes = await fetchWithTimeout("/api/positions/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ position_ids: nextOpenPositions.map((position) => position.id) }),
        }, "Tracked position review");
        const reviewData = await reviewRes.json();
        if (!reviewRes.ok || reviewData.error) {
          throw new Error(reviewData.error || "Failed to review tracked positions");
        }
        applyReviewedPositions((reviewData.positions || []) as TrackedPosition[]);
      }
      if (showToast) {
        toast.success(nextOpenPositions.length > 0 ? "Tracked positions refreshed and repriced." : "Tracked positions refreshed.");
      }
    } catch (err) {
      console.error("Failed to load tracked positions:", err);
      const message = err instanceof Error ? err.message : "Failed to load tracked positions.";
      setOpenPositions([]);
      setClosedPositions([]);
      setPositionsError(message);
      if (showToast) {
        toast.error(message);
      }
    } finally {
      setPositionsLoading(false);
    }
  }, [applyReviewedPositions, toast]);

  const fetchSuggestedTrades = useCallback(async (showToast = false) => {
    setSuggestedTradesLoading(true);
    try {
      const res = await fetchWithTimeout("/api/suggested-trades?status=all&grouped=1", undefined, "Suggested trades");
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error || "Failed to load suggested trades");
      }
      const nextOpenTrades = (data.open || []) as SuggestedTrade[];
      setOpenSuggestedTrades(nextOpenTrades);
      setClosedSuggestedTrades((data.closed || []) as SuggestedTrade[]);
      setSuggestedTradesLoaded(true);
      setSuggestedTradesError(null);
      if (nextOpenTrades.length > 0) {
        const reviewRes = await fetchWithTimeout("/api/suggested-trades/review", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ position_ids: nextOpenTrades.map((trade) => trade.id) }),
        }, "Suggested trade review");
        const reviewData = await reviewRes.json();
        if (!reviewRes.ok || reviewData.error) {
          throw new Error(reviewData.error || "Failed to review suggested trades");
        }
        applyReviewedSuggestedTrades((reviewData.trades || []) as SuggestedTrade[]);
      }
      if (showToast) {
        toast.success(nextOpenTrades.length > 0 ? "Suggested trades refreshed and repriced." : "Suggested trades refreshed.");
      }
    } catch (err) {
      console.error("Failed to load suggested trades:", err);
      const message = err instanceof Error ? err.message : "Failed to load suggested trades.";
      setOpenSuggestedTrades([]);
      setClosedSuggestedTrades([]);
      setSuggestedTradesError(message);
      if (showToast) {
        toast.error(message);
      }
    } finally {
      setSuggestedTradesLoading(false);
    }
  }, [applyReviewedSuggestedTrades, toast]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      setLoading(true);
      try {
        await refreshScannerSurface(false);
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
  }, [refreshScannerSurface]);

  useEffect(() => {
    if (!LEGACY_PREDICTION_TABS.has(activeSubTab)) return;
    const includePredictions = !predictionsLoaded;
    const includeSectors = activeSubTab === "sectors" && !sectorsLoaded;
    if (!includePredictions && !includeSectors) return;
    void fetchPredictionsData({ includePredictions, includeSectors });
  }, [activeSubTab, fetchPredictionsData, predictionsLoaded, sectorsLoaded]);

  useEffect(() => {
    if (activeSubTab !== "positions" || positionsLoaded) return;
    void fetchPositions(false);
  }, [activeSubTab, fetchPositions, positionsLoaded]);

  useEffect(() => {
    if (activeSubTab !== "suggestions" || suggestedTradesLoaded) return;
    void fetchSuggestedTrades(false);
  }, [activeSubTab, fetchSuggestedTrades, suggestedTradesLoaded]);

  useEffect(() => {
    if (!showLegacyTabs && LEGACY_PREDICTION_TABS.has(activeSubTab)) {
      setActiveSubTab("scanner");
    }
  }, [activeSubTab, showLegacyTabs]);

  useEffect(() => {
    if (activeSubTab !== "positions") return;
    const intervalId = window.setInterval(() => {
      void fetchPositions(false);
    }, POSITION_SYNC_INTERVAL_MS);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [activeSubTab, fetchPositions]);

  useEffect(() => {
    if (activeSubTab !== "suggestions") return;
    const intervalId = window.setInterval(() => {
      void fetchSuggestedTrades(false);
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
    await guard(async () => {
      setTakingTrade(true);
      try {
        const payload: CreateTrackedPositionRequest = {
          scan_pick: selectedPick,
          fill_price: Number(fillPrice),
          contracts: Number(contracts),
          notes: takeNotes || undefined,
        };
        const res = await fetch("/api/positions", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.error || "Failed to track position");
        }
        if (data.position) {
          mergeTrackedPosition(data.position as TrackedPosition);
        }
        cancelTakeTrade();
        setPositionsView("open");
        setActiveSubTab("positions");
        toast.success("Tracked position saved.");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to track position.");
      } finally {
        setTakingTrade(false);
      }
    });
  };

  const submitSuggestedTrade = async () => {
    if (!selectedPick) return;
    await guard(async () => {
      setSavingSuggestedTrade(true);
      try {
        const payload: CreateSuggestedTradeRequest = {
          scan_pick: selectedPick,
          fill_price: Number(fillPrice),
          contracts: Number(contracts),
          notes: takeNotes || undefined,
        };
        const res = await fetch("/api/suggested-trades", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.error || "Failed to save suggested trade");
        }
        if (data.trade) {
          mergeSuggestedTrade(data.trade as SuggestedTrade);
        }
        cancelTakeTrade();
        setSuggestedTradesView("open");
        setActiveSubTab("suggestions");
        toast.success("Suggested trade saved.");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to save suggested trade.");
      } finally {
        setSavingSuggestedTrade(false);
      }
    });
  };

  const reviewSinglePosition = async (positionId: number) => {
    setReviewingIds((prev) => [...prev, positionId]);
    try {
      const res = await fetchWithTimeout("/api/positions/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position_ids: [positionId] }),
      }, "Tracked position review");
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error || "Failed to review position");
      }
      applyReviewedPositions((data.positions || []) as TrackedPosition[]);
      toast.success("Position reviewed.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to review position.");
    } finally {
      setReviewingIds((prev) => prev.filter((id) => id !== positionId));
    }
  };

  const reviewSingleSuggestedTrade = async (positionId: number) => {
    setReviewingSuggestedTradeIds((prev) => [...prev, positionId]);
    try {
      const res = await fetchWithTimeout("/api/suggested-trades/review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ position_ids: [positionId] }),
      }, "Suggested trade review");
      const data = await res.json();
      if (!res.ok || data.error) {
        throw new Error(data.error || "Failed to review suggested trade");
      }
      applyReviewedSuggestedTrades((data.trades || []) as SuggestedTrade[]);
      toast.success("Suggested trade reviewed.");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to review suggested trade.");
    } finally {
      setReviewingSuggestedTradeIds((prev) => prev.filter((id) => id !== positionId));
    }
  };

  const openCloseForm = useCallback((position: TrackedPosition) => {
    setClosingPosition(position);
    setExitPrice(position.last_option_price != null ? position.last_option_price.toFixed(2) : "");
    setCloseNotes("");
  }, []);

  const cancelCloseForm = useCallback(() => {
    setClosingPosition(null);
    setExitPrice("");
    setCloseNotes("");
    setClosingId(null);
  }, []);

  const openCloseSuggestedTradeForm = useCallback((trade: SuggestedTrade) => {
    setClosingSuggestedTrade(trade);
    setSuggestedExitPrice(trade.last_option_price != null ? trade.last_option_price.toFixed(2) : "");
    setSuggestedCloseNotes("");
  }, []);

  const cancelCloseSuggestedTradeForm = useCallback(() => {
    setClosingSuggestedTrade(null);
    setSuggestedExitPrice("");
    setSuggestedCloseNotes("");
    setClosingSuggestedTradeId(null);
  }, []);

  const submitClosePosition = async () => {
    if (!closingPosition) return;
    await guard(async () => {
      setClosingId(closingPosition.id);
      try {
        const payload: CloseTrackedPositionRequest = {
          exit_price: Number(exitPrice),
          notes: closeNotes || undefined,
        };
        const res = await fetch(`/api/positions/${closingPosition.id}/close`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.error || "Failed to close tracked position");
        }
        if (data.position) {
          mergeTrackedPosition(data.position as TrackedPosition);
        }
        cancelCloseForm();
        toast.success("Tracked position closed.");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to close tracked position.");
      } finally {
        setClosingId(null);
      }
    });
  };

  const submitCloseSuggestedTrade = async () => {
    if (!closingSuggestedTrade) return;
    await guard(async () => {
      setClosingSuggestedTradeId(closingSuggestedTrade.id);
      try {
        const payload: CloseSuggestedTradeRequest = {
          exit_price: Number(suggestedExitPrice),
          notes: suggestedCloseNotes || undefined,
        };
        const res = await fetch(`/api/suggested-trades/${closingSuggestedTrade.id}/close`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || data.error) {
          throw new Error(data.error || "Failed to close suggested trade");
        }
        if (data.trade) {
          mergeSuggestedTrade(data.trade as SuggestedTrade);
        }
        cancelCloseSuggestedTradeForm();
        toast.success("Suggested trade closed.");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to close suggested trade.");
      } finally {
        setClosingSuggestedTradeId(null);
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

  const PRIMARY_SUB_TABS = [
    { id: "scanner", label: `Scanner (${scanPicks.length})`, icon: Search },
    { id: "positions", label: `Tracked Positions (${openPositions.length})`, icon: BriefcaseBusiness },
    { id: "suggestions", label: `Suggested Trades (${openSuggestedTrades.length})`, icon: Clipboard },
  ] as const;
  const LEGACY_SUB_TABS = [
    { id: "pending", label: `Legacy Active (${pending.length})`, icon: Timer },
    { id: "graded", label: `Legacy Graded (${graded.length})`, icon: CheckCircle },
    { id: "breakdown", label: "Legacy Breakdown", icon: BarChart3 },
    { id: "sim", label: "Legacy Portfolio Sim", icon: DollarSign },
    { id: "sectors", label: "Legacy Sectors", icon: Map },
  ] as const;
  const SUB_TABS = showLegacyTabs ? [...PRIMARY_SUB_TABS, ...LEGACY_SUB_TABS] : PRIMARY_SUB_TABS;

  if (loading) {
    return (
      <div className="px-4 md:px-8 py-6 max-w-7xl mx-auto space-y-6">
        <MetricGridSkeleton count={5} />
        <TableSkeleton rows={6} />
      </div>
    );
  }

  return (
    <div className="px-4 md:px-8 py-6 max-w-7xl mx-auto">
      {LEGACY_PREDICTION_TABS.has(activeSubTab) && (
        <div className="space-y-6 mb-6">
          <div className="bg-bg-2 border border-border rounded-lg px-4 py-3 text-sm text-text-2">
            These legacy prediction analytics are archival scanner research, not the current supervised tracked-position workflow.
          </div>
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

      {graded.length > 0 && LEGACY_PREDICTION_TABS.has(activeSubTab) && (
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

      <div className="flex items-center gap-0 border-b border-border mb-4 overflow-x-auto" role="tablist">
        {SUB_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeSubTab === tab.id;
          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveSubTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium uppercase tracking-wide transition-all border-b-2 whitespace-nowrap ${
                isActive
                  ? "text-text-0 border-accent"
                  : "text-text-2 border-transparent hover:text-text-1"
              }`}
            >
              <Icon size={14} />
              {tab.label}
            </button>
          );
        })}
        <div className="flex-1" />
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowLegacyTabs((prev) => !prev)}
        >
          {showLegacyTabs ? "Hide Legacy" : "Show Legacy Research"}
        </Button>
        {LEGACY_PREDICTION_TABS.has(activeSubTab) && (
          <Button
            variant="secondary"
            size="sm"
            loading={grading}
            icon={<RefreshCw size={12} />}
            onClick={async () => {
              await guard(async () => {
                setGrading(true);
                try {
                  const response = await fetch("/api/predictions/grade", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({}),
                  });
                  const data = await response.json().catch(() => ({}));
                  if (!response.ok || data.error) {
                    throw new Error(data.error || "Failed to grade predictions");
                  }
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

      <div role="tabpanel">
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
            closingTrade={closingSuggestedTrade}
            exitPrice={suggestedExitPrice}
            closeNotes={suggestedCloseNotes}
            closingId={closingSuggestedTradeId}
            onViewChange={setSuggestedTradesView}
            onRefresh={() => void fetchSuggestedTrades(true)}
            onReviewTrade={(positionId) => void reviewSingleSuggestedTrade(positionId)}
            onOpenClose={openCloseSuggestedTradeForm}
            onCancelClose={cancelCloseSuggestedTradeForm}
            onExitPriceChange={setSuggestedExitPrice}
            onCloseNotesChange={setSuggestedCloseNotes}
            onSubmitClose={() => void submitCloseSuggestedTrade()}
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
            closingPosition={closingPosition}
            exitPrice={exitPrice}
            closeNotes={closeNotes}
            closingId={closingId}
            onViewChange={setPositionsView}
            onRefresh={() => void fetchPositions(true)}
            onReviewPosition={(positionId) => void reviewSinglePosition(positionId)}
            onOpenClose={openCloseForm}
            onCancelClose={cancelCloseForm}
            onExitPriceChange={setExitPrice}
            onCloseNotesChange={setCloseNotes}
            onSubmitClose={() => void submitClosePosition()}
          />
        )}
        {activeSubTab === "pending" && <PendingTab predictions={pending} />}
        {activeSubTab === "graded" && <GradedTab predictions={graded} />}
        {activeSubTab === "breakdown" && <BreakdownTab predictions={graded} />}
        {activeSubTab === "sim" && <SimTab predictions={scanPreds} />}
        {activeSubTab === "sectors" && <SectorsTab sectors={sectors} />}
      </div>
    </div>
  );
}

function ScannerTab({
  picks,
  loading,
  useRecommendedPolicy,
  policy,
  policyError,
  exitAudit,
  decisionCounts,
  guardrailCounts,
  candidateCount,
  forwardEvidence,
  optionsProfitStatus,
  truthHealthError,
  playbook,
  playbooks,
  exposureSnapshot,
  showBlockedIdeas,
  selectedPick,
  fillPrice,
  contracts,
  notes,
  takingTrade,
  savingSuggestedTrade,
  onRefresh,
  onPolicyModeChange,
  onPlaybookChange,
  onShowBlockedIdeasChange,
  onPick,
  onCancel,
  onFillPriceChange,
  onContractsChange,
  onNotesChange,
  onSubmit,
  onSubmitSuggested,
}: {
  picks: ScanPick[];
  loading: boolean;
  useRecommendedPolicy: boolean;
  policy: LiveTradePolicy | null;
  policyError: string | null;
  exitAudit: PlaybookExitAudit | null;
  decisionCounts: Record<string, number> | null;
  guardrailCounts: Record<string, number> | null;
  candidateCount: number;
  forwardEvidence: ForwardEvidenceReport | null;
  optionsProfitStatus: OptionsProfitStatus | null;
  truthHealthError: string | null;
  playbook: string;
  playbooks: ScanPlaybook[];
  exposureSnapshot: ExposureSnapshot | null;
  showBlockedIdeas: boolean;
  selectedPick: ScanPick | null;
  fillPrice: string;
  contracts: string;
  notes: string;
  takingTrade: boolean;
  savingSuggestedTrade: boolean;
  onRefresh: () => void;
  onPolicyModeChange: (value: boolean) => void;
  onPlaybookChange: (value: string) => void;
  onShowBlockedIdeasChange: (value: boolean) => void;
  onPick: (pick: ScanPick) => void;
  onCancel: () => void;
  onFillPriceChange: (value: string) => void;
  onContractsChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onSubmit: () => void;
  onSubmitSuggested: () => void;
}) {
  const hardFilters = policy?.scan_policy.hard_filters;
  const preferred = policy?.scan_policy.preferred_filters;
  const promotionStatus = String(policy?.scan_policy.promotion_status || policy?.promotion_status || "watch").toLowerCase();
  const policyIsPromoted = promotionStatus === "promote";
  const truthSource = String(policy?.source?.truth_source || policy?.truth_source || "").toLowerCase();
  const truthSourceLabel = fmtTruthSource(truthSource);
  const quoteCoverage = policy?.source?.quote_coverage_pct ?? policy?.quote_coverage_pct ?? null;
  const sourceLabel = [
    policy?.source_run_at ? fmtDate(policy.source_run_at) : null,
    policy?.lookback_years != null ? `${policy.lookback_years}y` : null,
    policy?.pricing_lane ? String(policy.pricing_lane).toUpperCase() : null,
    policy?.playbook ? String(policy.playbook).replaceAll("_", " ") : null,
  ].filter(Boolean).join(" \u00b7 ");
  const approvedCount = decisionCounts?.approved || 0;
  const watchCount = decisionCounts?.watch || 0;
  const blockedCount = decisionCounts?.blocked || 0;
  const approvedReplayTrades = exitAudit?.approved?.trades ?? null;
  const clearCount = guardrailCounts?.clear || 0;
  const cautionCount = guardrailCounts?.caution || 0;
  const guardrailBlockedCount = guardrailCounts?.blocked || 0;
  const activePlaybook = playbooks.find((item) => item.id === playbook) || null;
  const measurementGate = optionsProfitStatus?.measurement_gate;
  const gateState = String(measurementGate?.state || "unknown").toLowerCase();
  const importedDailyCheck = measurementGate?.checks?.imported_daily_artifact || null;
  const forwardGateCheck = measurementGate?.checks?.forward_evidence || null;
  const trackedPositionsCheck = measurementGate?.checks?.tracked_positions || null;
  const dailyTruthRefresh = optionsProfitStatus?.daily_truth_refresh || null;
  const exactContractCount = Number(forwardEvidence?.exact_contract_capture_counts?.with_contract_count || 0);
  const totalForwardCaptures = Number(forwardEvidence?.scan_pick_count || 0);
  const exactContractCoveragePct = totalForwardCaptures > 0
    ? (exactContractCount / totalForwardCaptures) * 100
    : null;
  const contractResolutionOverview = forwardEvidence?.archived_forward_artifact?.contract_resolution_overview || null;
  const trackedDbStatus = trackedPositionsCheck?.available
    ? "READY"
    : trackedPositionsCheck?.database_url_configured
      ? "DOWN"
      : "MISSING";
  const blockerMessages = (measurementGate?.blockers || [])
    .map((item) => {
      if (typeof item === "string") return item;
      return String(item?.message || item?.code || "").trim();
    })
    .filter(Boolean)
    .slice(0, 3);

  const rows = picks.map((pick) => ({
    Ticker: pick.ticker,
    Trade: pick.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
    Contract: pick.contract_symbol || contractQualityLabel(pick),
    Quote: quoteContextLabel(pick),
    "Dir. Score": pick.direction_score.toFixed(0),
    Quality: pick.quality_score.toFixed(0),
    Decision: pick.policy_decision
      ? pick.policy_decision === "approved"
        ? "Approved"
        : pick.policy_decision === "watch"
        ? "Watch"
        : "Blocked"
      : "\u2014",
    Guardrails: pick.guardrail_decision
      ? pick.guardrail_decision === "clear"
        ? "Clear"
        : pick.guardrail_decision === "caution"
        ? "Caution"
        : "Blocked"
      : "\u2014",
    Size: pick.suggested_size_tier ? pick.suggested_size_tier.toUpperCase() : "\u2014",
    Regime: pick.market_regime ? pick.market_regime.toUpperCase() : "\u2014",
    Sector: pick.sector || "\u2014",
    Stock: fmtMoney(pick.stock_price),
    Premium: fmtMoney(pick.premium ?? pick.est_premium),
    Strike: fmtMoney(pick.strike ?? pick.strike_est, 0),
    Expiry: fmtDate(pick.expiry),
    "Target Move": pick.target_move_pct != null ? `${pick.target_move_pct.toFixed(2)}%` : "\u2014",
    Action: (
      <Button size="sm" variant="secondary" onClick={() => onPick(pick)}>
        {pick.guardrail_decision === "blocked"
          ? "Inspect"
          : pick.guardrail_decision === "caution"
          ? "Take Smaller"
          : pick.policy_decision === "approved"
          ? "Take Approved"
          : pick.policy_decision === "watch"
          ? "Take Watch"
          : "Take Trade"}
      </Button>
    ),
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="section-header mt-0">Live Options Scanner</div>
          <p className="text-xs text-text-3">
            Supervised decision support for live options ideas. Start from a current scan pick, then either save the trade you actually took or log a clearly hypothetical paper idea.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {(playbooks.length ? playbooks : [
            { id: "short_term", label: "Short-Term" },
            { id: "swing", label: "Swing" },
            { id: "bearish_defensive", label: "Bearish Defensive" },
          ]).map((item) => (
            <Button
              key={item.id}
              size="sm"
              variant={playbook === item.id ? "secondary" : "ghost"}
              onClick={() => onPlaybookChange(item.id)}
            >
              {item.label}
            </Button>
          ))}
          <Button
            size="sm"
            variant={useRecommendedPolicy ? "secondary" : "ghost"}
            onClick={() => onPolicyModeChange(true)}
          >
            Replay-Backed Focus
          </Button>
          <Button
            size="sm"
            variant={!useRecommendedPolicy ? "secondary" : "ghost"}
            onClick={() => onPolicyModeChange(false)}
          >
            All Qualifying
          </Button>
          <Button
            variant="secondary"
            size="sm"
            loading={loading}
            icon={<RefreshCw size={12} />}
            onClick={onRefresh}
          >
            Refresh Scan
          </Button>
          <Button
            size="sm"
            variant={showBlockedIdeas ? "secondary" : "ghost"}
            onClick={() => onShowBlockedIdeasChange(!showBlockedIdeas)}
          >
            {showBlockedIdeas ? "Hide Blocked" : "Show Blocked"}
          </Button>
        </div>
      </div>

      {activePlaybook && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-text-0">{activePlaybook.label} Playbook</div>
              <p className="text-xs text-text-3 mt-1">{activePlaybook.description}</p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <MetricCard label="Target DTE" value={String(activePlaybook.target_dte)} />
              <MetricCard label="Day Cap" value={String(activePlaybook.max_new_positions_per_day)} />
              <MetricCard label="Sector Cap" value={String(activePlaybook.max_sector_open_positions)} />
              <MetricCard label="Regime Cap" value={String(activePlaybook.max_regime_open_positions)} />
            </div>
          </div>

          {exposureSnapshot && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <MetricCard label="Open Positions" value={String(exposureSnapshot.open_positions)} />
                <MetricCard label="Opened Today" value={String(exposureSnapshot.opened_today)} />
                <MetricCard label="Guardrail Clear" value={String(clearCount)} />
                <MetricCard label="Guardrail Caution" value={String(cautionCount)} />
                <MetricCard label="Guardrail Blocked" value={String(guardrailBlockedCount)} />
              </div>
              <div className="text-xs text-text-3">
                Opened today {exposureSnapshot.opened_today}/{activePlaybook.max_new_positions_per_day}
                {" "}&middot; Same-sector cap {activePlaybook.max_sector_open_positions}
                {" "}&middot; Same-regime cap {activePlaybook.max_regime_open_positions}
              </div>
              {(policy?.priced_trade_count != null || policy?.unpriced_trade_count != null || policy?.entry_quote_time_et || policy?.exit_quote_time_et) && (
                <div className="text-[11px] uppercase tracking-wide text-text-3 mt-1">
                  {policy?.priced_trade_count != null || policy?.unpriced_trade_count != null
                    ? `Priced ${policy?.priced_trade_count ?? 0} / Unpriced ${policy?.unpriced_trade_count ?? 0}`
                    : "Quote windows active"}
                  {policy.entry_quote_time_et ? ` Â· Entry ${policy.entry_quote_time_et}` : ""}
                  {policy.exit_quote_time_et ? ` Â· Exit ${policy.exit_quote_time_et}` : ""}
                </div>
              )}
            </div>
          )}

          {exposureSnapshot?.warnings?.length ? (
        <div className="space-y-1">
              {exposureSnapshot.warnings.map((line) => (
                <div key={line} className="text-xs text-text-3">
                  {line}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      )}

      {(forwardEvidence || optionsProfitStatus || truthHealthError) && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-text-0">Options Truth Health</div>
              <p className="text-xs text-text-3 mt-1">
                This surface summarizes whether current scanner evidence is fresh enough, exact enough, and operationally usable for supervised decisions.
              </p>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <MetricCard label="Gate" value={fmtUpperLabel(gateState)} />
              <MetricCard label="Truth Horizon" value={fmtDate(forwardGateCheck?.trusted_truth_horizon as string | null | undefined)} />
              <MetricCard label="Eligible Live" value={String(forwardGateCheck?.eligible_event_count ?? 0)} />
              <MetricCard label="Exact Coverage" value={exactContractCoveragePct != null ? `${exactContractCoveragePct.toFixed(0)}%` : "\u2014"} />
              <MetricCard label="Tracked DB" value={trackedDbStatus} />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Imported Daily</div>
              <div className="text-sm text-text-1">
                {importedDailyCheck?.present && importedDailyCheck?.matches_store
                  ? `Coverage ${Number(importedDailyCheck.quote_coverage_pct ?? 0).toFixed(1)}%`
                  : "Artifact missing or stale"}
              </div>
              <div className="text-xs text-text-3">
                Refresh {fmtCompactLabel(dailyTruthRefresh?.status as string | null | undefined)}
                {dailyTruthRefresh?.stage ? ` · ${fmtCompactLabel(dailyTruthRefresh.stage as string)}` : ""}
              </div>
            </div>
            <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Authoritative Forward</div>
              <div className="text-sm text-text-1">
                {String(forwardEvidence?.authoritative_session_count ?? 0)} sessions · {String(forwardEvidence?.scan_pick_count ?? 0)} picks
              </div>
              <div className="text-xs text-text-3">
                Pending truth {String(forwardGateCheck?.pending_truth_event_count ?? 0)}
                {" "}&middot; Artifact {forwardEvidence?.archived_forward_artifact?.available ? "ready" : "waiting"}
              </div>
            </div>
            <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Contract Quality</div>
              <div className="text-sm text-text-1">
                {exactContractCount}/{totalForwardCaptures || 0} captures kept exact
              </div>
              <div className="text-xs text-text-3">
                Fallback {forwardEvidence?.archived_forward_artifact?.primary_judge_fallback_used ? fmtCompactLabel(forwardEvidence.archived_forward_artifact.primary_judge_fallback_reason) : "none"}
              </div>
              {contractResolutionOverview && (
                <div className="text-xs text-text-3">
                  Archived {String(contractResolutionOverview.exact_archived_contract ?? 0)}
                  {" "}&middot; Model {String(contractResolutionOverview.exact_target_contract ?? 0)}
                  {" "}&middot; Nearest {String(contractResolutionOverview.nearest_listed_contract ?? 0)}
                  {" "}&middot; Pending {String(contractResolutionOverview.pending_truth_horizon ?? 0)}
                </div>
              )}
            </div>
          </div>

          {truthHealthError && (
            <div className="bg-red-dim border border-red/30 rounded-lg px-3 py-2 text-xs text-red">
              {truthHealthError}
            </div>
          )}

          {gateState !== "healthy" && blockerMessages.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
              {blockerMessages.map((line) => (
                <div key={line} className="text-xs text-amber-200">
                  {line}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {policy && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
            <div>
              <div className="text-sm font-semibold text-text-0">Replay-Backed Policy State</div>
              <p className="text-xs text-text-3 mt-1">
                This scanner gate follows the latest saved options truth artifacts. It is a truth layer, not a promise that the strategy is ready for trust-by-default.
              </p>
              {sourceLabel && (
                <div className="text-[11px] uppercase tracking-wide text-text-3 mt-2">
                  Source {sourceLabel}
                </div>
              )}
              <div className="text-[11px] uppercase tracking-wide text-text-3 mt-1">
                Truth {truthSourceLabel}
                {quoteCoverage != null ? ` | Coverage ${Number(quoteCoverage).toFixed(1)}%` : ""}
              </div>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
              <MetricCard label="Status" value={promotionStatus.toUpperCase()} />
              <MetricCard label="Scan Pool" value={String(candidateCount)} />
              <MetricCard label="Approved" value={String(approvedCount)} />
              <MetricCard label="Watch" value={String(watchCount)} />
              <MetricCard label="Blocked" value={String(blockedCount)} />
            </div>
          </div>

          {!useRecommendedPolicy && (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
              <div className="text-xs text-amber-200">
                Replay-Backed Focus is overridden. You are looking at all qualifying ideas, but the policy state above still describes the latest replay-backed truth and should be used as the risk context for any manual entry.
              </div>
            </div>
          )}

          {!policyIsPromoted && (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
              <div className="text-xs text-amber-200">
                Current policy state is <strong>{promotionStatus.toUpperCase()}</strong>, and the current truth lane is <strong>{truthSourceLabel.toUpperCase()}</strong>, so scanner ideas should be treated as watch-oriented and supervised paper-first unless you choose to override that manually.
              </div>
              {approvedReplayTrades === 0 && (
                <div className="text-xs text-amber-200">
                  The active {playbook.replaceAll("_", " ")} replay audit has zero approved trades in the latest saved artifact.
                </div>
              )}
              {approvedCount === 0 && (
                <div className="text-xs text-amber-200">
                  There are zero approved live picks in this scan right now.
                </div>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="bg-bg-3 border border-border rounded-lg p-3">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Hard Gate</div>
              <div className="text-sm text-text-1 mt-1">
                {hardFilters?.direction_score_min != null
                  ? `Direction score ${hardFilters.direction_score_min.toFixed(0)}${hardFilters.direction_score_max != null ? `-${hardFilters.direction_score_max.toFixed(0)}` : "+"}`
                  : "No score-band gate available yet"}
              </div>
            </div>
            <div className="bg-bg-3 border border-border rounded-lg p-3">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Preferred Context</div>
              <div className="text-sm text-text-1 mt-1">
                {[
                  preferred?.asset_class ? preferred.asset_class : null,
                  ...(preferred?.market_regimes || []),
                ].filter(Boolean).join(" / ") || "No broad asset-regime preference yet"}
              </div>
            </div>
            <div className="bg-bg-3 border border-border rounded-lg p-3">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Preferred Sectors</div>
              <div className="text-sm text-text-1 mt-1">
                {preferred?.sectors?.length ? preferred.sectors.join(", ") : "No broad sector preference yet"}
              </div>
            </div>
          </div>

          {policy.scan_policy.rationale.length > 0 && (
            <div className="space-y-1">
              {policy.scan_policy.rationale.map((line) => (
                <div key={line} className="text-xs text-text-2">
                  {line}
                </div>
              ))}
            </div>
          )}

          {policy.scan_policy.warnings.length > 0 && (
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
              {policy.scan_policy.warnings.map((line) => (
                <div key={line} className="text-xs text-amber-200">
                  {line}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {policyError && (
        <div className="bg-red-dim border border-red/30 rounded-lg px-4 py-3 text-sm text-red">
          {policyError}
        </div>
      )}

      {selectedPick && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div>
            <div className="text-sm font-semibold text-text-0">
              Record {selectedPick.ticker} {selectedPick.direction.toUpperCase()}
            </div>
            <div className="text-xs text-text-3 mt-1">
              {fmtContractLabel({
                ticker: selectedPick.ticker,
                direction: selectedPick.direction,
                strike: selectedPick.strike ?? selectedPick.strike_est,
                expiry: selectedPick.expiry,
                contract_symbol: selectedPick.contract_symbol,
              })}
              {" "}&middot; Scan premium {fmtMoney(selectedPick.premium ?? selectedPick.est_premium)}
            </div>
            {(!policyIsPromoted || selectedPick.policy_decision !== "approved") && (
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 mt-3 text-xs text-amber-200">
                {useRecommendedPolicy
                  ? "This setup is not replay-approved right now. Saving it as a tracked position is still allowed, but it should be treated as supervised paper-first decision support."
                  : "Replay-Backed Focus is overridden, and this setup is not replay-approved right now. Saving it as a tracked position is still allowed, but it should be treated as supervised paper-first decision support."}
              </div>
            )}
            {selectedPick.policy_decision && (
              <div className="text-xs text-text-2 mt-2 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Policy</div>
                <div>
                  Decision: <strong className="text-text-0">{selectedPick.policy_decision.toUpperCase()}</strong>
                </div>
                {selectedPick.policy_fit_reasons?.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
              </div>
            )}
            {selectedPick.guardrail_decision && (
              <div className="text-xs text-text-2 mt-2 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Portfolio Guardrails</div>
                <div>
                  Guardrails: <strong className="text-text-0">{selectedPick.guardrail_decision.toUpperCase()}</strong>
                  {" "}&middot; Size tier <strong className="text-text-0">{selectedPick.suggested_size_tier?.toUpperCase() || "\u2014"}</strong>
                </div>
                {selectedPick.guardrail_reasons?.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
                {selectedPick.suggested_size_reason && <div>{selectedPick.suggested_size_reason}</div>}
              </div>
            )}
            <div className="text-xs text-text-2 mt-2 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Contract And Quote Provenance</div>
              <div>
                Contract quality: <strong className="text-text-0">{contractQualityLabel(selectedPick)}</strong>
                {selectedPick.contract_symbol ? ` · ${selectedPick.contract_symbol}` : ""}
              </div>
              <div>
                Quote: <strong className="text-text-0">{quoteContextLabel(selectedPick)}</strong>
                {selectedPick.quote_time_et ? ` · ${selectedPick.quote_time_et}` : ""}
              </div>
              <div>
                Selection: <strong className="text-text-0">{fmtCompactLabel(selectedPick.selection_source)}</strong>
                {" "}&middot; Promotion <strong className="text-text-0">{fmtCompactLabel(selectedPick.promotion_class)}</strong>
              </div>
              <div>
                Entry execution: <strong className="text-text-0">{fmtCompactLabel(selectedPick.entry_execution_basis)}</strong>
                {" "}&middot; {fmtMoney(selectedPick.entry_execution_price ?? selectedPick.premium ?? selectedPick.est_premium)}
              </div>
              <div>
                Profitability: <strong className="text-text-0">{fmtUpperLabel(selectedPick.profitability_eligibility)}</strong>
                {selectedPick.profitability_blockers?.length
                  ? ` · ${selectedPick.profitability_blockers.join(", ")}`
                  : ""}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Entry price</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={fillPrice}
                onChange={(e) => onFillPriceChange(e.target.value)}
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0 font-mono"
              />
            </label>
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Contracts</span>
              <input
                type="number"
                min="1"
                step="1"
                value={contracts}
                onChange={(e) => onContractsChange(e.target.value)}
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0 font-mono"
              />
            </label>
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Notes</span>
              <input
                type="text"
                value={notes}
                onChange={(e) => onNotesChange(e.target.value)}
                placeholder="Optional note"
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
              />
            </label>
          </div>
          <div className="text-xs text-text-3">
            Nothing from the scanner is auto-tracked. Real tracked positions and hypothetical suggested trades stay separate on purpose.
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              loading={takingTrade}
              disabled={selectedPick.guardrail_decision === "blocked" || savingSuggestedTrade}
              onClick={onSubmit}
            >
              Save Real Tracked Position
            </Button>
            <Button
              variant="secondary"
              size="sm"
              loading={savingSuggestedTrade}
              disabled={takingTrade}
              onClick={onSubmitSuggested}
            >
              Save Hypothetical Suggested Trade
            </Button>
            <Button variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {picks.length === 0 && !loading ? (
        <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
          No qualifying options picks were returned by the live scan.
        </div>
      ) : (
        <FinTable
          data={rows}
          badgeCol="Trade"
          monoCols={["Contract", "Quote", "Dir. Score", "Quality", "Size", "Stock", "Premium", "Strike"]}
          label="Live options scanner picks"
          maxHeight="620px"
        />
      )}
    </div>
  );
}

function SuggestedTradesTab({
  openTrades,
  closedTrades,
  loading,
  error,
  view,
  reviewingIds,
  closingTrade,
  exitPrice,
  closeNotes,
  closingId,
  onViewChange,
  onRefresh,
  onReviewTrade,
  onOpenClose,
  onCancelClose,
  onExitPriceChange,
  onCloseNotesChange,
  onSubmitClose,
}: {
  openTrades: SuggestedTrade[];
  closedTrades: SuggestedTrade[];
  loading: boolean;
  error: string | null;
  view: "open" | "closed";
  reviewingIds: number[];
  closingTrade: SuggestedTrade | null;
  exitPrice: string;
  closeNotes: string;
  closingId: number | null;
  onViewChange: (value: "open" | "closed") => void;
  onRefresh: () => void;
  onReviewTrade: (positionId: number) => void;
  onOpenClose: (trade: SuggestedTrade) => void;
  onCancelClose: () => void;
  onExitPriceChange: (value: string) => void;
  onCloseNotesChange: (value: string) => void;
  onSubmitClose: () => void;
}) {
  const trades = view === "open" ? openTrades : closedTrades;
  const holdCount = openTrades.filter((trade) => trade.last_recommendation === "HOLD").length;
  const sellCount = openTrades.filter((trade) => trade.last_recommendation === "SELL").length;
  const openPnlValues = openTrades
    .map((trade) => trade.last_pnl_pct)
    .filter((value): value is number => value != null);
  const closedPnlValues = closedTrades
    .map((trade) => calcOptionPnlPct(trade.entry_option_price, trade.exit_option_price))
    .filter((value): value is number => value != null);
  const avgOpenPnl = openPnlValues.length > 0
    ? openPnlValues.reduce((sum, value) => sum + value, 0) / openPnlValues.length
    : null;
  const avgClosedPnl = closedPnlValues.length > 0
    ? closedPnlValues.reduce((sum, value) => sum + value, 0) / closedPnlValues.length
    : null;

  const rows = trades.map((trade) => {
    const displayPnl = view === "open"
      ? trade.last_pnl_pct
      : calcOptionPnlPct(trade.entry_option_price, trade.exit_option_price);

    return {
      Ticker: trade.ticker,
      Trade: trade.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
      Contract: fmtContractLabel(trade),
      "Contract Q": contractQualityLabel(trade.source_pick_snapshot),
      Source: fmtCompactLabel(trade.source_pick_snapshot?.selection_source || trade.source_pick_snapshot?.promotion_class),
      "Entry Basis": fmtCompactLabel(trade.entry_execution_basis || trade.source_pick_snapshot?.entry_execution_basis),
      Contracts: String(trade.contracts),
      Entry: fmtMoney(trade.entry_option_price),
      [view === "open" ? "Last Px" : "Exit Px"]: fmtMoney(view === "open" ? trade.last_option_price : trade.exit_option_price),
      [view === "open" ? "Hyp. P&L %" : "Realized P&L %"]: fmtPct(displayPnl),
      Recommendation: trade.last_recommendation || "\u2014",
      Reason: trade.last_recommendation_reason || trade.latest_review?.reason || "\u2014",
      [view === "open" ? "Logged" : "Closed"]: fmtDate(view === "open" ? trade.filled_at : trade.closed_at),
      Action: view === "open" ? (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            loading={reviewingIds.includes(trade.id)}
            onClick={() => onReviewTrade(trade.id)}
          >
            Review
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onOpenClose(trade)}
          >
            Mark Closed
          </Button>
        </div>
      ) : (
        <span className="text-xs text-text-3">{trade.exit_reason || "manual_hypothetical_close"}</span>
      ),
    };
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <div className="section-header mt-0">Suggested Trades (Hypothetical)</div>
          <p className="text-xs text-text-3">
            Manual paper-tracked ideas from the scanner. Open trades reprice automatically here, and stay separate from positions you actually took.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={view === "open" ? "secondary" : "ghost"}
            onClick={() => onViewChange("open")}
          >
            Open
          </Button>
          <Button
            size="sm"
            variant={view === "closed" ? "secondary" : "ghost"}
            onClick={() => onViewChange("closed")}
          >
            Closed
          </Button>
          <Button
            size="sm"
            variant="secondary"
            loading={loading}
            icon={<RefreshCw size={12} />}
            onClick={onRefresh}
          >
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-red-dim border border-red/30 rounded-lg px-4 py-3 text-sm text-red">
          {error}
        </div>
      )}

      {!error && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard label="Open Trades" value={String(openTrades.length)} />
          <MetricCard label="Closed Trades" value={String(closedTrades.length)} />
          <MetricCard label="Avg Open P&L" value={fmtPct(avgOpenPnl)} />
          <MetricCard label="Avg Closed P&L" value={fmtPct(avgClosedPnl)} help={`Last HOLD ${holdCount} / SELL ${sellCount}`} />
        </div>
      )}

      {closingTrade && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div>
            <div className="text-sm font-semibold text-text-0">
              Close suggested {closingTrade.ticker} {closingTrade.direction.toUpperCase()}
            </div>
            <div className="text-xs text-text-3 mt-1">
              Entry {fmtMoney(closingTrade.entry_option_price)} &middot; Last price {fmtMoney(closingTrade.last_option_price)} &middot; Current rec {closingTrade.last_recommendation || "\u2014"}
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Hypothetical exit price</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={exitPrice}
                onChange={(e) => onExitPriceChange(e.target.value)}
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0 font-mono"
              />
            </label>
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Notes</span>
              <input
                type="text"
                value={closeNotes}
                onChange={(e) => onCloseNotesChange(e.target.value)}
                placeholder="Optional close note"
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
              />
            </label>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="primary" size="sm" loading={closingId === closingTrade.id} onClick={onSubmitClose}>
              Confirm Close
            </Button>
            <Button variant="ghost" size="sm" onClick={onCancelClose}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {trades.length === 0 && !loading && !error ? (
        <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
          {view === "open" ? "No suggested trades yet. Save a scanner idea to start paper tracking it." : "No closed suggested trades yet."}
        </div>
      ) : (
        <FinTable
          data={rows}
          badgeCol="Trade"
          pnlCols={["Hyp. P&L %", "Realized P&L %"]}
          monoCols={["Contract", "Contract Q", "Entry Basis", "Contracts", "Entry", "Last Px", "Exit Px"]}
          label="Suggested trades"
          maxHeight="620px"
        />
      )}
    </div>
  );
}

function TrackedPositionsTab({
  openPositions,
  closedPositions,
  loading,
  error,
  view,
  reviewingIds,
  closingPosition,
  exitPrice,
  closeNotes,
  closingId,
  onViewChange,
  onRefresh,
  onReviewPosition,
  onOpenClose,
  onCancelClose,
  onExitPriceChange,
  onCloseNotesChange,
  onSubmitClose,
}: {
  openPositions: TrackedPosition[];
  closedPositions: TrackedPosition[];
  loading: boolean;
  error: string | null;
  view: "open" | "closed";
  reviewingIds: number[];
  closingPosition: TrackedPosition | null;
  exitPrice: string;
  closeNotes: string;
  closingId: number | null;
  onViewChange: (value: "open" | "closed") => void;
  onRefresh: () => void;
  onReviewPosition: (positionId: number) => void;
  onOpenClose: (position: TrackedPosition) => void;
  onCancelClose: () => void;
  onExitPriceChange: (value: string) => void;
  onCloseNotesChange: (value: string) => void;
  onSubmitClose: () => void;
}) {
  const positions = view === "open" ? openPositions : closedPositions;
  const holdCount = openPositions.filter((position) => position.last_recommendation === "HOLD").length;
  const sellCount = openPositions.filter((position) => position.last_recommendation === "SELL").length;
  const unpricedCount = openPositions.filter((position) => {
    const source = position.latest_review?.pricing_source || null;
    return source === "unavailable" || source === "expired" || source == null;
  }).length;

  const rows = positions.map((position) => {
    const targetPct = position.profit_target_pct;
    const stopPct = position.stop_loss_pct;
    const entryPrice = position.entry_option_price || 0;
    const targetPrice = targetPct ? entryPrice * (1 + targetPct / 100) : null;
    const stopPrice = stopPct ? entryPrice * (1 - stopPct / 100) : null;
    return {
    Ticker: position.ticker,
    Trade: position.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
    Contract: fmtContractLabel(position),
    Contracts: String(position.contracts),
    Entry: fmtMoney(position.entry_option_price),
    "Last Px": fmtMoney(position.last_option_price),
    "P&L %": fmtPct(position.last_pnl_pct),
    Target: targetPct ? `+${targetPct}% ($${targetPrice?.toFixed(2)})` : "\u2014",
    Stop: stopPct ? `-${stopPct}% ($${stopPrice?.toFixed(2)})` : "\u2014",
    Pricing: fmtPricingSource(position.latest_review?.pricing_source),
    Warnings: position.latest_review?.warnings?.[0] || "\u2014",
    Recommendation: position.last_recommendation || "\u2014",
    Filled: fmtDate(position.filled_at),
    Action: view === "open" ? (
      <div className="flex items-center gap-2">
        <Button
          size="sm"
          variant="secondary"
          loading={reviewingIds.includes(position.id)}
          onClick={() => onReviewPosition(position.id)}
        >
          Review
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => onOpenClose(position)}
        >
          Mark Closed
        </Button>
      </div>
    ) : (
      <span className="text-xs text-text-3">{position.exit_reason || "manual_close"}</span>
    ),
  };});

  return (
    <div className="space-y-4">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
        <div>
          <div className="section-header mt-0">Tracked Options Positions</div>
          <p className="text-xs text-text-3">
            These are the positions you actually took. Open positions refresh profit and HOLD/SELL guidance automatically while keeping exact contract identity when available.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={view === "open" ? "secondary" : "ghost"}
            onClick={() => onViewChange("open")}
          >
            Open
          </Button>
          <Button
            size="sm"
            variant={view === "closed" ? "secondary" : "ghost"}
            onClick={() => onViewChange("closed")}
          >
            Closed
          </Button>
          <Button
            size="sm"
            variant="secondary"
            loading={loading}
            icon={<RefreshCw size={12} />}
            onClick={onRefresh}
          >
            Refresh
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-red-dim border border-red/30 rounded-lg px-4 py-3 text-sm text-red">
          {error}
        </div>
      )}

      {!error && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <MetricCard label="Open Positions" value={String(openPositions.length)} />
          <MetricCard label="Closed Positions" value={String(closedPositions.length)} />
          <MetricCard label="Last HOLD" value={String(holdCount)} />
          <MetricCard label="Unpriced Reviews" value={String(unpricedCount)} help={`Last SELL ${sellCount}`} />
        </div>
      )}

      {closingPosition && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div>
            <div className="text-sm font-semibold text-text-0">
              Close {closingPosition.ticker} {closingPosition.direction.toUpperCase()}
            </div>
            <div className="text-xs text-text-3 mt-1">
              {fmtContractLabel(closingPosition)}
              {" "}&middot; Entry {fmtMoney(closingPosition.entry_option_price)}
              {" "}&middot; Last price {fmtMoney(closingPosition.last_option_price)}
              {" "}&middot; Pricing {fmtPricingSource(closingPosition.latest_review?.pricing_source)}
            </div>
            <div className="text-xs text-text-2 mt-2 space-y-1">
              <div>
                Contract quality: <strong className="text-text-0">{contractQualityLabel(closingPosition.source_pick_snapshot)}</strong>
              </div>
              <div>
                Source: <strong className="text-text-0">{fmtCompactLabel(closingPosition.source_pick_snapshot?.selection_source || closingPosition.source_pick_snapshot?.promotion_class)}</strong>
              </div>
              <div>
                Entry basis: <strong className="text-text-0">{fmtCompactLabel(closingPosition.entry_execution_basis || closingPosition.source_pick_snapshot?.entry_execution_basis)}</strong>
              </div>
            </div>
            {closingPosition.latest_review?.warnings?.length ? (
              <div className="text-xs text-amber-200 mt-2">
                {closingPosition.latest_review.warnings[0]}
              </div>
            ) : null}
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Actual exit price</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={exitPrice}
                onChange={(e) => onExitPriceChange(e.target.value)}
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0 font-mono"
              />
            </label>
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Notes</span>
              <input
                type="text"
                value={closeNotes}
                onChange={(e) => onCloseNotesChange(e.target.value)}
                placeholder="Optional close note"
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
              />
            </label>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="primary" size="sm" loading={closingId === closingPosition.id} onClick={onSubmitClose}>
              Confirm Close
            </Button>
            <Button variant="ghost" size="sm" onClick={onCancelClose}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {positions.length === 0 && !loading && !error ? (
        <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
          {view === "open" ? "No tracked positions yet. Take a live scan pick to start tracking it." : "No closed tracked positions yet."}
        </div>
      ) : (
        <FinTable
          data={rows}
          badgeCol="Trade"
          pnlCols={["P&L %"]}
          monoCols={["Contract", "Contracts", "Entry", "Last Px", "Target", "Stop"]}
          label="Tracked options positions"
          maxHeight="620px"
        />
      )}
    </div>
  );
}

function PendingTab({ predictions }: { predictions: Prediction[] }) {
  if (predictions.length === 0) {
    return (
      <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
        No active trades. Run a scan to generate picks.
      </div>
    );
  }

  const byDate: Record<string, Prediction[]> = {};
  for (const prediction of predictions) {
    const date = (prediction.last_rolled_date || prediction.entry_date || "").slice(0, 10);
    if (!byDate[date]) byDate[date] = [];
    byDate[date].push(prediction);
  }

  const sortedDates = Object.keys(byDate).sort().reverse();

  return (
    <div className="space-y-4">
      {sortedDates.map((date) => {
        const picks = byDate[date];
        const rows = picks
          .sort((a, b) => (b.direction_score || 0) - (a.direction_score || 0))
          .map((prediction) => ({
            Ticker: prediction.ticker,
            Trade: prediction.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
            "Dir. Score": (prediction.direction_score || 0).toFixed(0),
            Tech: (prediction.tech_score || 0).toFixed(0),
            Quality: (prediction.quality_score || 0).toFixed(0),
            "Stock Price": fmtMoney(prediction.stock_price),
            "Stock %": fmtPct(prediction.current_stock_pct, 2),
            "Options P&L": prediction.option_gain_pct != null ? fmtPct(prediction.option_gain_pct, 1) : "\u2014",
            Strike: prediction.strike_est ? fmtMoney(prediction.strike_est, 0) : "\u2014",
            Premium: prediction.est_premium ? fmtMoney(prediction.est_premium) : "\u2014",
            "Target Date": fmtDate(prediction.target_date),
          }));

        return (
          <div key={date} className="bg-bg-2 border border-border rounded-lg overflow-hidden">
            <div className="px-4 py-2.5 bg-bg-3 border-b border-border flex items-center justify-between">
              <span className="text-sm font-semibold text-text-0">
                <span aria-hidden="true">{"\uD83D\uDCC5"}</span>
                <span className="sr-only">Date:</span>{" "}
                {date} &middot; {picks.length} picks active
              </span>
            </div>
            <FinTable
              data={rows}
              pnlCols={["Stock %", "Options P&L"]}
              badgeCol="Trade"
              monoCols={["Dir. Score", "Tech", "Quality", "Stock Price", "Strike", "Premium"]}
            />
          </div>
        );
      })}
    </div>
  );
}

function GradedTab({ predictions }: { predictions: Prediction[] }) {
  if (predictions.length === 0) {
    return (
      <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
        No graded predictions yet.
      </div>
    );
  }

  const rows = [...predictions]
    .sort((a, b) => (b.entry_date || "").localeCompare(a.entry_date || ""))
    .map((prediction) => ({
      Date: fmtDate(prediction.entry_date),
      Ticker: prediction.ticker,
      Trade: prediction.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
      "Dir. Score": (prediction.direction_score || 0).toFixed(0),
      "Stock %": fmtPct(prediction.current_stock_pct, 2),
      "Options P&L": prediction.option_gain_pct != null ? fmtPct(prediction.option_gain_pct, 1) : "\u2014",
      Outcome: prediction.outcome === "hit" ? "\u2705 Hit" : prediction.outcome === "directional" ? "\uD83D\uDFE1 Directional" : "\u274C Miss",
      "Target Date": fmtDate(prediction.target_date),
    }));

  return (
    <FinTable
      data={rows}
      pnlCols={["Stock %", "Options P&L"]}
      badgeCol="Trade"
      monoCols={["Dir. Score"]}
      maxHeight="600px"
    />
  );
}

function BreakdownTab({ predictions }: { predictions: Prediction[] }) {
  const tickerRows = useMemo(() => {
    if (predictions.length === 0) return [];

    const byTicker: Record<string, Prediction[]> = {};
    for (const prediction of predictions) {
      const ticker = prediction.ticker || "?";
      if (!byTicker[ticker]) byTicker[ticker] = [];
      byTicker[ticker].push(prediction);
    }

    return Object.entries(byTicker)
      .map(([ticker, preds]) => {
        const dirHits = preds.filter((prediction) => prediction.outcome === "hit" || prediction.outcome === "directional");
        const fullHits = preds.filter((prediction) => prediction.outcome === "hit");
        const calls = preds.filter((prediction) => prediction.direction === "call").length;
        const puts = preds.filter((prediction) => prediction.direction === "put").length;
        const avgScore = preds.reduce((sum, prediction) => sum + (prediction.direction_score || 0), 0) / (preds.length || 1);
        const avgMoveValues = preds
          .map((prediction) => prediction.current_stock_pct)
          .filter((value): value is number => value != null);

        return {
          Ticker: ticker,
          Picks: preds.length,
          "Hit %": `${((fullHits.length / (preds.length || 1)) * 100).toFixed(1)}%`,
          "Dir %": `${((dirHits.length / (preds.length || 1)) * 100).toFixed(1)}%`,
          "Call/Put": `${calls}/${puts}`,
          "Avg Score": avgScore.toFixed(0),
          "Avg Move": avgMoveValues.length > 0
            ? `${(avgMoveValues.reduce((a, b) => a + b, 0) / (avgMoveValues.length || 1)).toFixed(1)}%`
            : "\u2014",
        };
      })
      .sort((a, b) => parseFloat(b["Dir %"]) - parseFloat(a["Dir %"]));
  }, [predictions]);

  const bucketRows = useMemo(() => {
    const buckets = [
      { label: "0\u201340%", min: 0, max: 40 },
      { label: "40\u201355%", min: 40, max: 55 },
      { label: "55\u201370%", min: 55, max: 70 },
      { label: "70%+", min: 70, max: 101 },
    ];

    return buckets.map((bucket) => {
      const subset = predictions.filter(
        (prediction) => (prediction.direction_score || 0) >= bucket.min && (prediction.direction_score || 0) < bucket.max
      );
      const directional = subset.filter((prediction) => prediction.outcome === "hit" || prediction.outcome === "directional");
      return {
        "Score Band": bucket.label,
        Picks: subset.length,
        "Directional %": subset.length > 0
          ? `${((directional.length / (subset.length || 1)) * 100).toFixed(1)}%`
          : "\u2014",
      };
    });
  }, [predictions]);

  if (predictions.length === 0) {
    return (
      <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
        No graded predictions for breakdown analysis.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="section-header">Per-Ticker Accuracy</div>
        <FinTable
          data={tickerRows}
          rateCols={["Hit %", "Dir %"]}
          monoCols={["Picks", "Avg Score"]}
        />
      </div>
      <div>
        <div className="section-header">Direction Score vs Accuracy</div>
        <FinTable
          data={bucketRows}
          rateCols={["Directional %"]}
          monoCols={["Picks"]}
        />
      </div>
    </div>
  );
}

function SimTab({ predictions }: { predictions: Prediction[] }) {
  const [accountSize, setAccountSize] = useState(10000);

  const graded = predictions.filter((prediction) => prediction.outcome && prediction.option_gain_pct != null);
  const totalPicks = predictions.length || 1;
  const perTrade = accountSize / totalPicks;

  let totalPnl = 0;
  let wins = 0;
  let losses = 0;
  let winTotal = 0;
  let lossTotal = 0;

  for (const prediction of graded) {
    const pnl = perTrade * ((prediction.option_gain_pct || 0) / 100);
    totalPnl += pnl;
    if (pnl >= 0) {
      wins += 1;
      winTotal += pnl;
    } else {
      losses += 1;
      lossTotal += Math.abs(pnl);
    }
  }

  const avgWin = wins > 0 ? winTotal / (wins || 1) : 0;
  const avgLoss = losses > 0 ? lossTotal / (losses || 1) : 0;

  return (
    <div className="space-y-6">
      <div className="bg-bg-2 border border-border rounded-lg p-4">
        <div className="section-header mt-0">Account Settings</div>
        <div className="flex items-center gap-3">
          <label className="text-xs text-text-2">Starting Account:</label>
          <input
            type="number"
            value={accountSize}
            onChange={(e) => setAccountSize(Number(e.target.value) || 10000)}
            className="bg-bg-3 border border-border rounded px-3 py-1.5 text-sm text-text-0 font-mono w-32"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard
          label="Portfolio P&L"
          value={`$${totalPnl.toFixed(0)}`}
          delta={`${((totalPnl / (accountSize || 1)) * 100).toFixed(1)}%`}
        />
        <MetricCard
          label="Win Rate"
          value={graded.length > 0 ? `${((wins / (graded.length || 1)) * 100).toFixed(1)}%` : "\u2014"}
          delta={`${wins}W / ${losses}L`}
        />
        <MetricCard label="Avg Win" value={wins > 0 ? `$${avgWin.toFixed(0)}` : "\u2014"} />
        <MetricCard label="Avg Loss" value={losses > 0 ? `-$${avgLoss.toFixed(0)}` : "\u2014"} />
      </div>

      {graded.length > 0 && (
        <div>
          <div className="section-header">Trade-by-Trade</div>
          <FinTable
            data={graded.map((prediction) => {
              const pnl = perTrade * ((prediction.option_gain_pct || 0) / 100);
              return {
                Date: fmtDate(prediction.entry_date),
                Ticker: prediction.ticker,
                Direction: prediction.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
                "Dir Score": (prediction.direction_score || 0).toFixed(0),
                "Cost Basis": `$${perTrade.toFixed(0)}`,
                "P&L $": `${pnl >= 0 ? "+" : ""}$${pnl.toFixed(0)}`,
                "P&L %": fmtPct(prediction.option_gain_pct, 1),
                Outcome: prediction.outcome === "hit" ? "\u2705 Hit" : prediction.outcome === "directional" ? "\uD83D\uDFE1 Dir" : "\u274C Miss",
              };
            })}
            pnlCols={["P&L $", "P&L %"]}
            badgeCol="Direction"
            maxHeight="500px"
          />
        </div>
      )}
    </div>
  );
}

function SectorsTab({ sectors }: { sectors: SectorSentiment[] }) {
  if (sectors.length === 0) {
    return (
      <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
        Loading sector data... Make sure the Python backend is running.
      </div>
    );
  }

  const bullCount = sectors.filter((sector) => sector.near_sent.includes("Bullish")).length;
  const bearCount = sectors.filter((sector) => sector.near_sent.includes("Bearish")).length;
  const neutralCount = sectors.length - bullCount - bearCount;

  const biasLabel =
    bullCount > bearCount
      ? "Bullish Bias"
      : bearCount > bullCount
      ? "Bearish Bias"
      : "Mixed/Neutral";
  const biasColor =
    bullCount > bearCount
      ? "text-green"
      : bearCount > bullCount
      ? "text-red"
      : "text-text-3";

  return (
    <div>
      <div className="section-header">Sector Sentiment Dashboard</div>
      <p className="text-xs text-text-3 mb-4">
        Refreshes daily at 10 AM ET &middot; Scores use price return, SMA position,
        and trend slope
      </p>

      <div className="ft-wrap mb-4" style={{ maxHeight: "500px" }}>
        <table className="ft-table">
          <thead>
            <tr>
              <th>Sector</th>
              <th>Near-Term (0-1 month)</th>
              <th>Medium-Term (1-12 months)</th>
              <th>Long-Term (12-36 months)</th>
            </tr>
          </thead>
          <tbody>
            {sectors.map((sector) => (
              <tr key={sector.sector}>
                <td>
                  <strong className="text-text-0">{sector.sector}</strong>
                  <span className="text-xs text-text-3 ml-1.5">{sector.etf}</span>
                </td>
                <td><SentimentBadge sentiment={sector.near_sent} returnPct={sector.near_ret} /></td>
                <td><SentimentBadge sentiment={sector.med_sent} returnPct={sector.med_ret} /></td>
                <td><SentimentBadge sentiment={sector.long_sent} returnPct={sector.long_ret} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="text-base text-text-2">
        Near-term breadth:{" "}
        <span className="text-green">
          <span aria-hidden="true">{"\u25B2"}</span> {bullCount} bullish
        </span>{" "}
        &middot;{" "}
        <span className="text-text-3">
          <span aria-hidden="true">{"\u2192"}</span> {neutralCount} neutral
        </span>{" "}
        &middot;{" "}
        <span className="text-red">
          <span aria-hidden="true">{"\u25BC"}</span> {bearCount} bearish
        </span>{" "}
        &mdash; <strong className={biasColor}>{biasLabel}</strong>
      </div>
    </div>
  );
}
