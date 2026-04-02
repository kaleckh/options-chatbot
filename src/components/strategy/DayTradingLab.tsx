"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, BellRing, Loader2, Play, RefreshCw, ShieldCheck, Trophy } from "lucide-react";
import MetricCard from "@/components/ui/MetricCard";
import FinTable from "@/components/ui/FinTable";
import type {
  DayTradingReport,
  DayTradingOperatingPlan,
  DayTradingPilotSummary,
  DayTradingSnapshot,
  DayTradingStrategySpec,
  DayTradingWatchlist,
} from "@/lib/types";

type DayTradingMarket = "crypto" | "equities_legacy";

const MARKET_OPTIONS: { value: DayTradingMarket; label: string; description: string }[] = [
  {
    value: "crypto",
    label: "Crypto",
    description: "Default research lane using free Binance-style spot data.",
  },
  {
    value: "equities_legacy",
    label: "Equities Legacy",
    description: "Previous Yahoo-based ETF morning lab kept for comparison.",
  },
];

function pct(value: number | null | undefined, digits: number = 1): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

function money(value: number | null | undefined, digits: number = 0): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `$${value.toFixed(digits)}`;
}

function ratio(value: number | null | undefined, digits: number = 1): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${value.toFixed(digits)}x`;
}

function phaseLabel(value: string | null | undefined): string {
  if (!value) return "-";
  return value.replace(/_/g, " ");
}

function statusTone(status: string): string {
  switch (status) {
    case "candidate_live":
      return "text-green";
    case "promotion_review":
      return "text-amber";
    case "paper_live":
      return "text-accent";
    case "backtest_failed":
    case "disabled":
      return "text-red";
    default:
      return "text-text-2";
  }
}

function watchStatusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

function marketCopy(market: DayTradingMarket) {
  if (market === "equities_legacy") {
    return {
      title: "Day Trading Lab",
      description:
        "Legacy ETF morning lab that tracks SPY/QQQ replay evidence and paper activity. This lane is still available for comparison, but crypto is now the default active research track.",
      watchlistTitle: "Morning Watchlist",
      windowActive: "Morning window live",
      windowInactive: "Outside morning window",
    };
  }
  return {
    title: "Crypto Day Trading Lab",
    description:
      "Profitability pilot for BTC-first crypto spot trading. The active live lane is a rules-first BTC range mean-reversion setup in one fixed session, while ETH stays locked until phase 1 passes and SOL remains paper-only.",
    watchlistTitle: "Fixed Session Watchlist",
    windowActive: "Core session live",
    windowInactive: "Outside fixed session",
  };
}

function StrategyCard({ strategy }: { strategy: DayTradingStrategySpec }) {
  return (
    <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-text-0">{strategy.name}</div>
          <div className="text-xs text-text-3 mt-1">
            {strategy.marketUniverse.symbols.join(", ")} - {strategy.evaluationWindow.timeframe} - {strategy.simulation.entrySignal}
          </div>
        </div>
        <div className={`text-xs font-semibold uppercase tracking-wide ${statusTone(strategy.status)}`}>
          {strategy.status.replace(/_/g, " ")}
        </div>
      </div>

      <p className="text-sm text-text-2 leading-relaxed">{strategy.hypothesisSummary}</p>

      {strategy.metadata?.unlockPhase && (
        <div className="text-xs text-text-3 uppercase tracking-wide">
          Unlock phase: {strategy.metadata.unlockPhase.replace(/_/g, " ")}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div className="bg-bg-3 border border-border rounded-md p-3">
          <div className="text-text-3 uppercase tracking-wide mb-1">Entry</div>
          <div className="text-text-1">Threshold: {strategy.simulation.useSignalStrengthThreshold?.toFixed(2) || "-"}</div>
          <div className="text-text-2 mt-1">Warmup: {strategy.evaluationWindow.warmupBars} bars</div>
          <div className="text-text-2 mt-1">Cooldown: {strategy.simulation.cooldownBars} bars</div>
        </div>
        <div className="bg-bg-3 border border-border rounded-md p-3">
          <div className="text-text-3 uppercase tracking-wide mb-1">Risk</div>
          <div className="text-text-1">TP / SL: {pct(strategy.simulation.takeProfitFraction)} / {pct(strategy.simulation.stopLossFraction)}</div>
          <div className="text-text-2 mt-1">Max DD: {pct(strategy.riskLimits.maxDrawdownFraction)}</div>
          <div className="text-text-2 mt-1">Min trades: {strategy.evaluationWindow.minimumTrades}</div>
        </div>
      </div>

      <div className="text-xs text-text-3">
        <div>Entry rule: {strategy.entryRules[0]}</div>
        <div className="mt-1">Exit rule: {strategy.exitRules[0]}</div>
      </div>
    </div>
  );
}

export default function DayTradingLab() {
  const [snapshot, setSnapshot] = useState<DayTradingSnapshot | null>(null);
  const [watchlist, setWatchlist] = useState<DayTradingWatchlist | null>(null);
  const [market, setMarket] = useState<DayTradingMarket>("crypto");
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bars, setBars] = useState(3120);
  const [startingCash, setStartingCash] = useState(10000);
  const snapshotRequestRef = useRef(0);
  const watchlistRequestRef = useRef(0);

  const fetchWatchlist = useCallback(async (requestedBars: number, requestedLimit: number = 4) => {
    const requestId = ++watchlistRequestRef.current;
    setWatchlistLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        bars: String(requestedBars),
        limit: String(requestedLimit),
        market,
      });
      const res = await fetch(`/api/day-trading/watchlist?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load day-trading watchlist");
      if (requestId === watchlistRequestRef.current) {
        setWatchlist(data);
      }
    } catch (err) {
      if (requestId === watchlistRequestRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load day-trading watchlist");
      }
    } finally {
      if (requestId === watchlistRequestRef.current) {
        setWatchlistLoading(false);
      }
    }
  }, [market]);

  const loadSnapshot = useCallback(async () => {
    const requestId = ++snapshotRequestRef.current;
    setLoading(true);
    setError(null);
    watchlistRequestRef.current += 1;
    setWatchlist(null);
    setWatchlistLoading(false);
    try {
      const params = new URLSearchParams({ market });
      const res = await fetch(`/api/day-trading?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load day-trading lab");
      if (requestId !== snapshotRequestRef.current) {
        return;
      }
      setSnapshot(data);
      const defaultBars = data.defaultConfig?.bars || 3120;
      const watchlistLimit = data.defaultConfig?.watchlistLimit || 4;
      setBars((current) => current || defaultBars);
      setStartingCash((current) => current || data.defaultConfig?.startingCash || 10000);
      void fetchWatchlist(defaultBars, watchlistLimit);
    } catch (err) {
      if (requestId === snapshotRequestRef.current) {
        setError(err instanceof Error ? err.message : "Failed to load day-trading lab");
      }
    } finally {
      if (requestId === snapshotRequestRef.current) {
        setLoading(false);
      }
    }
  }, [fetchWatchlist, market]);

  useEffect(() => {
    loadSnapshot();
  }, [loadSnapshot]);

  const runValidation = async () => {
    setRunning(true);
    setError(null);
    try {
      const res = await fetch("/api/day-trading", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ market, bars, startingCash }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Validation run failed");
      setSnapshot(data.snapshot);
      setWatchlist(null);
      void fetchWatchlist(bars, data.snapshot?.defaultConfig?.watchlistLimit || 4);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Validation run failed");
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-text-3">
        Loading day-trading lab...
      </div>
    );
  }

  if (!snapshot) {
    return (
      <div className="bg-bg-2 border border-border rounded-lg p-6 text-sm text-text-3">
        {error || "Unable to load day-trading lab."}
      </div>
    );
  }

  const report: DayTradingReport | null = snapshot.lastReport;
  const selectedMarket = (snapshot.market || market) as DayTradingMarket;
  const copy = marketCopy(selectedMarket);
  const operatingPlan: DayTradingOperatingPlan | null = snapshot.operatingPlan || null;
  const pilotSummary: DayTradingPilotSummary | null = snapshot.pilotSummary || null;
  const scoreboardRows = snapshot.scoreboard.items.map((item) => ({
    Strategy: item.strategyName,
    Status: item.status.replace(/_/g, " "),
    Score: item.score.toFixed(1),
    "Backtest Return": item.backtest ? pct(item.backtest.totalNetReturnFraction) : "-",
    "Drawdown": item.backtest ? pct(item.backtest.maxDrawdownFraction) : "-",
    "Win Rate": item.backtest ? pct(item.backtest.winRate) : "-",
    "Paper PnL": item.paper ? money(item.paper.realizedPnl) : "-",
    Vetoes: item.vetoReasons.length > 0 ? item.vetoReasons.join(", ") : "-",
  }));

  const validationRows = report?.results.map((result) => ({
    Strategy: result.strategyId,
    Source: result.marketDataSource,
    "Backtest Return": pct(result.backtestSummary.totalNetReturnFraction),
    "Trades": String(result.backtestSummary.tradeCount),
    "Profit Factor": result.backtestSummary.profitFactor?.toFixed(2) || "-",
    "Hit Rate": pct(result.backtestSummary.winRate),
    "Paper Action": result.paperAction.action,
    Promotion: result.promotionDecision?.nextStatus?.replace(/_/g, " ") || "-",
    Warning: result.marketDataWarning || "-",
  })) || [];

  const watchlistRows = watchlist?.items.map((item) => ({
    Strategy: item.strategyName,
    Symbol: item.symbol || "-",
    Status: item.notifyNow ? "notify now" : watchStatusLabel(item.liveStatus),
    "Replay Ready": item.alertEligible ? "yes" : "no",
    "Data Trust": item.currentDataTrusted ? "trusted" : "untrusted",
    "Hit Rate": item.replayEvidence ? pct(item.replayEvidence.winRate) : "-",
    "Profit Factor": item.replayEvidence?.profitFactor?.toFixed(2) || "-",
    Trades: item.replayEvidence?.tradeCount?.toString() || "-",
    "Signal / Threshold": item.currentSignalValue != null && item.signalThreshold != null
      ? `${item.currentSignalValue.toFixed(2)} / ${item.signalThreshold.toFixed(2)}`
      : "-",
    "Bar Age": item.barAgeMinutes != null ? `${item.barAgeMinutes.toFixed(1)}m` : "-",
    "Triggered At": item.latestSignalTimestamp
      ? item.latestSignalTimestamp.slice(11, 16)
      : "-",
    Window: item.sessionWindowLabel || "-",
    Source: item.marketDataSource,
    Warning: item.marketDataWarning || "-",
  })) || [];
  const pilotGateRows = pilotSummary?.gates.map((gate) => ({
    Gate: gate.label,
    Target: gate.target,
    Actual: gate.actual,
    Status: gate.passed ? "passed" : "pending",
  })) || [];
  const regimeRows = operatingPlan ? [
    {
      Mode: "Range",
      Checklist: operatingPlan.regimeChecklist.range.join(" "),
    },
    {
      Mode: "Trend",
      Checklist: operatingPlan.regimeChecklist.trend.join(" "),
    },
    {
      Mode: "Event",
      Checklist: operatingPlan.regimeChecklist.event.join(" "),
    },
  ] : [];
  const regimeBreakdownRows = pilotSummary?.breakdownByRegime.map((row) => ({
    Regime: row.label,
    Trades: String(row.trades),
    "Win Rate": pct(row.winRate),
    "Expectancy (R)": row.expectancyR.toFixed(2),
    "Net PnL": money(row.netPnlUsd, 2),
  })) || [];
  const setupBreakdownRows = pilotSummary?.breakdownBySetup.map((row) => ({
    Setup: row.label,
    Trades: String(row.trades),
    "Win Rate": pct(row.winRate),
    "Expectancy (R)": row.expectancyR.toFixed(2),
    "Net PnL": money(row.netPnlUsd, 2),
  })) || [];

  return (
    <div className="space-y-6">
      <div className="bg-bg-2 border border-border rounded-lg p-4">
        <div className="flex items-center justify-between gap-4 mb-4">
          <div>
            <div className="section-header mt-0 mb-1 border-0 pb-0">{copy.title}</div>
            <p className="text-sm text-text-3 max-w-3xl">
              {copy.description}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchWatchlist(bars, snapshot?.defaultConfig?.watchlistLimit || 4)}
              disabled={watchlistLoading}
              className="flex items-center gap-2 px-4 py-2.5 rounded-md border border-border bg-bg-3 text-text-1 text-sm font-medium hover:bg-bg-4 disabled:opacity-50 transition-all"
            >
              {watchlistLoading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
              {watchlistLoading ? "Refreshing..." : "Refresh Watchlist"}
            </button>
            <button
              onClick={runValidation}
              disabled={running}
              className="flex items-center gap-2 px-5 py-2.5 rounded-md bg-gradient-to-r from-accent to-blue-600 text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-all"
            >
              {running ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
              {running ? "Running..." : "Run Validation Cycle"}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <div>
            <label className="text-xs text-text-2 block mb-1">Active market</label>
            <select
              value={market}
              onChange={(e) => setMarket(e.target.value as DayTradingMarket)}
              className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
            >
              {MARKET_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <div className="mt-1 text-xs text-text-3">
              {MARKET_OPTIONS.find((option) => option.value === market)?.description}
            </div>
          </div>
          <div>
            <label className="text-xs text-text-2 block mb-1">Bars of intraday history</label>
            <input
              type="number"
              min={48}
              max={3900}
              step={78}
              value={bars}
              onChange={(e) => setBars(Math.max(48, Math.min(3900, Number(e.target.value) || 3120)))}
              className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
            />
          </div>
          <div>
            <label className="text-xs text-text-2 block mb-1">Paper account starting cash</label>
            <input
              type="number"
              min={1000}
              step={500}
              value={startingCash}
              onChange={(e) => setStartingCash(Math.max(1000, Number(e.target.value) || 10000))}
              className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
            />
          </div>
        </div>

        {error && (
          <div className="mt-4 text-sm text-red bg-red/10 border border-red/20 rounded-md px-3 py-2">
            {error}
          </div>
        )}
      </div>

      <div className="grid grid-cols-4 gap-3">
        <MetricCard
          label="Strategies"
          value={String(snapshot.scoreboard.totals.strategies)}
          delta={`${snapshot.strategies.length} loaded`}
        />
        <MetricCard
          label="Paper Equity"
          value={money(snapshot.paperAccount.equity)}
          delta={snapshot.paperAccount.totalUnrealizedPnl >= 0
            ? `+${snapshot.paperAccount.totalUnrealizedPnl.toFixed(2)} unrealized`
            : `${snapshot.paperAccount.totalUnrealizedPnl.toFixed(2)} unrealized`}
        />
        <MetricCard
          label="Candidate Live"
          value={String(snapshot.scoreboard.totals.candidateLive)}
          delta={`${snapshot.scoreboard.totals.withPaperActivity} with paper activity`}
        />
        <MetricCard
          label="Blocked"
          value={String(snapshot.scoreboard.totals.blocked)}
          delta={report ? `Last run ${report.generatedAt.slice(0, 16).replace("T", " ")}` : "No run yet"}
        />
      </div>

      {operatingPlan && pilotSummary && (
        <div className="space-y-4">
          <div className="section-header flex items-center gap-2">
            <ShieldCheck size={14} />
            Profitability Pilot
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-3">
            <MetricCard
              label="Pilot Phase"
              value={phaseLabel(pilotSummary.phase)}
              delta={operatingPlan.defaultRegimeBias}
            />
            <MetricCard
              label="Phase 1 Progress"
              value={`${pilotSummary.progress.completedTrades}/${pilotSummary.progress.targetTrades}`}
              delta={`${pilotSummary.progress.remainingTrades} trades remaining`}
            />
            <MetricCard
              label="Expectancy"
              value={pilotSummary.journalStats.expectancyR == null ? "-" : `${pilotSummary.journalStats.expectancyR.toFixed(2)}R`}
              delta="Net after fees/slippage"
            />
            <MetricCard
              label="Profit Factor"
              value={ratio(pilotSummary.journalStats.profitFactor, 2)}
              delta="Phase 1 gate >= 1.20x"
            />
            <MetricCard
              label="Rule Adherence"
              value={pct(pilotSummary.journalStats.ruleAdherenceRate)}
              delta="Phase 1 gate >= 90%"
            />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-3">
              <div>
                <div className="section-header mt-0">Operating Plan</div>
                <p className="text-sm text-text-2">{operatingPlan.objective}</p>
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="bg-bg-3 border border-border rounded-md p-3">
                  <div className="text-text-3 uppercase tracking-wide mb-1">Session</div>
                  <div className="text-text-1">{operatingPlan.session.localWindow}</div>
                  <div className="text-text-2 mt-1">{operatingPlan.session.etWindow}</div>
                </div>
                <div className="bg-bg-3 border border-border rounded-md p-3">
                  <div className="text-text-3 uppercase tracking-wide mb-1">Instruments</div>
                  <div className="text-text-1">Live now: {operatingPlan.instruments.liveNow.join(", ")}</div>
                  <div className="text-text-2 mt-1">Next: {operatingPlan.instruments.nextPhase.join(", ")}</div>
                </div>
                <div className="bg-bg-3 border border-border rounded-md p-3">
                  <div className="text-text-3 uppercase tracking-wide mb-1">Execution</div>
                  <div className="text-text-1">{operatingPlan.execution.venues.join(" / ")}</div>
                  <div className="text-text-2 mt-1">{operatingPlan.execution.orderStyle}</div>
                </div>
                <div className="bg-bg-3 border border-border rounded-md p-3">
                  <div className="text-text-3 uppercase tracking-wide mb-1">Risk</div>
                  <div className="text-text-1">Per trade: {pct(operatingPlan.risk.riskPerTradeFraction, 2)}</div>
                  <div className="text-text-2 mt-1">Daily / Weekly: {pct(operatingPlan.risk.maxDailyLossFraction)} / {pct(operatingPlan.risk.maxWeeklyLossFraction)}</div>
                </div>
              </div>
              <div className="text-xs text-text-3">
                Journal path: {snapshot.profitabilityJournal?.path || "-"}
              </div>
            </div>

            <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
              <div>
                <div className="section-header mt-0">Validation Gates</div>
                <p className="text-sm text-text-2">
                  Phase 1 stays BTC-only until all acceptance gates pass. ETH remains locked until this panel is green.
                </p>
              </div>
              <FinTable
                data={pilotGateRows}
                badgeCol="Status"
                monoCols={["Target", "Actual"]}
                maxHeight="320px"
              />
              <div className="text-xs text-text-3">
                Next unlock: {pilotSummary.nextUnlock}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {regimeRows.map((row) => (
              <div key={row.Mode} className="bg-bg-2 border border-border rounded-lg p-4">
                <div className="section-header mt-0">{row.Mode}</div>
                <p className="text-sm text-text-2 leading-relaxed">{row.Checklist}</p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Journal By Regime</div>
              <FinTable
                data={regimeBreakdownRows}
                pnlCols={["Net PnL"]}
                rateCols={["Win Rate"]}
                monoCols={["Trades", "Expectancy (R)"]}
                maxHeight="280px"
              />
            </div>
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Journal By Setup</div>
              <FinTable
                data={setupBreakdownRows}
                pnlCols={["Net PnL"]}
                rateCols={["Win Rate"]}
                monoCols={["Trades", "Expectancy (R)"]}
                maxHeight="280px"
              />
            </div>
          </div>

          <div className="bg-bg-2 border border-border rounded-lg p-4">
            <div className="section-header mt-0">Journal Template</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3 text-xs">
              {(snapshot.profitabilityJournal?.schema || []).map((field) => (
                <div key={field.key} className="bg-bg-3 border border-border rounded-md px-3 py-2 text-text-2">
                  <span className="text-text-1">{field.label}</span>
                  {field.required ? " · required" : ""}
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {(watchlistLoading || watchlist) && (
        <div className="space-y-4">
          <div className="section-header flex items-center gap-2">
            <BellRing size={14} />
            {copy.watchlistTitle}
          </div>
          {watchlist ? (
            <>
              <div className="grid grid-cols-4 gap-3">
                <MetricCard
                  label="Notify Now"
                  value={String(watchlist.notifyNowCount)}
                  delta={(watchlist.sessionWindow?.activeNow || watchlist.morningWindow.activeNow) ? copy.windowActive : copy.windowInactive}
                />
                <MetricCard
                  label="Strategies Checked"
                  value={String(watchlist.selectedStrategies)}
                  delta={watchlist.rankingBasis}
                />
                <MetricCard
                  label="Top Hit Rate"
                  value={watchlist.items[0]?.replayEvidence ? pct(watchlist.items[0].replayEvidence.winRate) : "-"}
                  delta={watchlist.items[0]?.strategyName || "No ranked strategy yet"}
                />
                <MetricCard
                  label={selectedMarket === "crypto" ? "Trusted Data" : "Alert Eligible"}
                  value={String(selectedMarket === "crypto"
                    ? watchlist.items.filter((item) => item.currentDataTrusted).length
                    : watchlist.items.filter((item) => item.alertEligible).length)}
                  delta={selectedMarket === "crypto"
                    ? `${watchlist.sessionWindow?.windows.length || 0} scheduled windows`
                    : (watchlist.items.some((item) => item.alertEligible)
                      ? "Replay-approved setup exists"
                      : "No setup has earned alerts yet")}
                />
              </div>
              {selectedMarket === "crypto" && watchlist.sessionWindow && (
                <div className="bg-bg-2 border border-border rounded-lg px-4 py-3 text-sm text-text-2">
                  Windows: {watchlist.sessionWindow.windows.map((window) => `${window.label} ${window.startEt}-${window.endEt} ET`).join(" | ")}
                </div>
              )}
              <FinTable
                data={watchlistRows}
                badgeCol="Status"
                rateCols={["Hit Rate"]}
                monoCols={["Trades", "Profit Factor", "Signal / Threshold", "Bar Age", "Triggered At", "Window"]}
                maxHeight="360px"
              />
            </>
          ) : (
            <div className="bg-bg-2 border border-border rounded-lg px-4 py-4 text-sm text-text-2 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" />
              Loading watchlist...
            </div>
          )}
        </div>
      )}

      <div>
        <div className="section-header flex items-center gap-2">
          <Activity size={14} />
          Imported Strategies
        </div>
        <div className="grid grid-cols-2 gap-4">
          {snapshot.strategies.map((strategy) => (
            <StrategyCard key={strategy.strategyId} strategy={strategy} />
          ))}
        </div>
      </div>

      <div>
        <div className="section-header flex items-center gap-2">
          <Trophy size={14} />
          Scoreboard
        </div>
        <FinTable
          data={scoreboardRows}
          pnlCols={["Paper PnL"]}
          rateCols={["Win Rate"]}
          monoCols={["Score", "Trades"]}
          maxHeight="420px"
        />
      </div>

      {report && (
        <div className="space-y-4">
          <div className="section-header flex items-center gap-2">
            <ShieldCheck size={14} />
            Latest Validation Run
          </div>
          <div className="grid grid-cols-3 gap-3">
            <MetricCard
              label="Run Time"
              value={report.generatedAt.slice(0, 16).replace("T", " ")}
            />
            <MetricCard
              label="Strategies Scanned"
              value={String(report.strategiesScanned)}
            />
            <MetricCard
              label="Open Paper Positions"
              value={String(report.paperAccount.positions.length)}
            />
          </div>
          {selectedMarket === "crypto" && snapshot.lastImport && (
            <div className="bg-bg-2 border border-border rounded-lg px-4 py-3 text-sm text-text-2">
              Latest import: {snapshot.lastImport.results.map((item) => `${item.symbol} ${item.totalBars} x 1m bars`).join(" | ")}
            </div>
          )}
          <FinTable
            data={validationRows}
            pnlCols={["Backtest Return"]}
            rateCols={["Hit Rate"]}
            monoCols={["Trades", "Profit Factor"]}
            maxHeight="420px"
          />
        </div>
      )}
    </div>
  );
}
