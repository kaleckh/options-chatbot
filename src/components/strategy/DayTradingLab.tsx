"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, BellRing, Loader2, Play, RefreshCw, ShieldCheck, Trophy } from "lucide-react";
import MetricCard from "@/components/ui/MetricCard";
import FinTable from "@/components/ui/FinTable";
import type {
  DayTradingReport,
  DayTradingSnapshot,
  DayTradingStrategySpec,
  DayTradingWatchlist,
} from "@/lib/types";

function pct(value: number | null | undefined, digits: number = 1): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `${(value * 100).toFixed(digits)}%`;
}

function money(value: number | null | undefined, digits: number = 0): string {
  if (value == null || Number.isNaN(value)) return "-";
  return `$${value.toFixed(digits)}`;
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
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bars, setBars] = useState(3120);
  const [startingCash, setStartingCash] = useState(10000);

  const fetchWatchlist = useCallback(async (requestedBars: number, requestedLimit: number = 4) => {
    setWatchlistLoading(true);
    try {
      const params = new URLSearchParams({
        bars: String(requestedBars),
        limit: String(requestedLimit),
      });
      const res = await fetch(`/api/day-trading/watchlist?${params.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load morning watchlist");
      setWatchlist(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load morning watchlist");
    } finally {
      setWatchlistLoading(false);
    }
  }, []);

  const loadSnapshot = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/day-trading");
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to load day-trading lab");
      setSnapshot(data);
      const defaultBars = data.defaultConfig?.bars || 3120;
      const watchlistLimit = data.defaultConfig?.watchlistLimit || 4;
      setBars((current) => current || defaultBars);
      setStartingCash((current) => current || data.defaultConfig?.startingCash || 10000);
      await fetchWatchlist(defaultBars, watchlistLimit);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load day-trading lab");
    } finally {
      setLoading(false);
    }
  }, [fetchWatchlist]);

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
        body: JSON.stringify({ bars, startingCash }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Validation run failed");
      setSnapshot(data.snapshot);
      await fetchWatchlist(bars, data.snapshot?.defaultConfig?.watchlistLimit || 4);
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
    Source: item.marketDataSource,
    Warning: item.marketDataWarning || "-",
  })) || [];

  return (
    <div className="space-y-6">
      <div className="bg-bg-2 border border-border rounded-lg p-4">
        <div className="flex items-center justify-between gap-4 mb-4">
          <div>
            <div className="section-header mt-0 mb-1 border-0 pb-0">Day Trading Lab</div>
            <p className="text-sm text-text-3 max-w-3xl">
              Tracks a small set of ETF morning setups, ranks them by replay evidence, and checks whether they are live now.
              It fetches Yahoo intraday bars when available, blocks live notify decisions on untrusted fallback data,
              persists paper trades, and stages strategies through draft, paper, and review states.
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

        <div className="grid grid-cols-2 gap-4">
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

      {watchlist && (
        <div className="space-y-4">
          <div className="section-header flex items-center gap-2">
            <BellRing size={14} />
            Morning Watchlist
          </div>
          <div className="grid grid-cols-4 gap-3">
            <MetricCard
              label="Notify Now"
              value={String(watchlist.notifyNowCount)}
              delta={watchlist.morningWindow.activeNow ? "Morning window live" : "Outside morning window"}
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
              label="Alert Eligible"
              value={String(watchlist.items.filter((item) => item.alertEligible).length)}
              delta={watchlist.items.some((item) => item.alertEligible)
                ? "Replay-approved setup exists"
                : "No setup has earned alerts yet"}
            />
          </div>
          <FinTable
            data={watchlistRows}
            badgeCol="Status"
            rateCols={["Hit Rate"]}
            monoCols={["Trades", "Profit Factor", "Signal / Threshold", "Bar Age", "Triggered At"]}
            maxHeight="360px"
          />
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
