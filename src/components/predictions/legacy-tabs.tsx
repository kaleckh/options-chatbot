"use client";

import { useMemo, useState } from "react";
import MetricCard from "@/components/ui/MetricCard";
import FinTable from "@/components/ui/FinTable";
import SentimentBadge from "@/components/ui/SentimentBadge";
import type { Prediction, SectorSentiment } from "@/lib/types";

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

const PENDING_MOBILE_PRIORITY_COLS = [
  "Trade",
  "Dir. Score",
  "Quality",
  "Stock %",
  "Premium",
  "Strike",
  "Target Date",
];
const GRADED_MOBILE_PRIORITY_COLS = [
  "Trade",
  "Date",
  "Options P&L",
  "Stock %",
  "Dir. Score",
  "Target Date",
];
const BREAKDOWN_TICKER_MOBILE_PRIORITY_COLS = [
  "Picks",
  "Hit %",
  "Call/Put",
  "Avg Score",
  "Avg Move",
];
const SIM_MOBILE_PRIORITY_COLS = [
  "Outcome",
  "Direction",
  "Date",
  "P&L $",
  "Cost Basis",
  "Dir Score",
];

export function PendingTab({ predictions }: { predictions: Prediction[] }) {
  if (predictions.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-bg-2 p-6 text-center text-sm text-text-3">
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
          <div key={date} className="overflow-hidden rounded-lg border border-border bg-bg-2">
            <div className="flex items-center justify-between border-b border-border bg-bg-3 px-4 py-2.5">
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
              mobileTitleCol="Ticker"
              mobileSubtitleCol="Options P&L"
              mobilePriorityCols={PENDING_MOBILE_PRIORITY_COLS}
              mobileHiddenCols={["Tech", "Stock Price"]}
            />
          </div>
        );
      })}
    </div>
  );
}

export function GradedTab({ predictions }: { predictions: Prediction[] }) {
  if (predictions.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-bg-2 p-6 text-center text-sm text-text-3">
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
      Outcome:
        prediction.outcome === "hit"
          ? "\u2705 Hit"
          : prediction.outcome === "directional"
            ? "\uD83D\uDFE1 Directional"
            : "\u274C Miss",
      "Target Date": fmtDate(prediction.target_date),
    }));

  return (
    <FinTable
      data={rows}
      pnlCols={["Stock %", "Options P&L"]}
      badgeCol="Trade"
      monoCols={["Dir. Score"]}
      maxHeight="600px"
      mobileTitleCol="Ticker"
      mobileSubtitleCol="Outcome"
      mobilePriorityCols={GRADED_MOBILE_PRIORITY_COLS}
    />
  );
}

export function BreakdownTab({ predictions }: { predictions: Prediction[] }) {
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
          "Avg Move":
            avgMoveValues.length > 0
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
        "Directional %":
          subset.length > 0 ? `${((directional.length / (subset.length || 1)) * 100).toFixed(1)}%` : "\u2014",
      };
    });
  }, [predictions]);

  if (predictions.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-bg-2 p-6 text-center text-sm text-text-3">
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
          mobileTitleCol="Ticker"
          mobileSubtitleCol="Dir %"
          mobilePriorityCols={BREAKDOWN_TICKER_MOBILE_PRIORITY_COLS}
        />
      </div>
      <div>
        <div className="section-header">Direction Score vs Accuracy</div>
        <FinTable
          data={bucketRows}
          rateCols={["Directional %"]}
          monoCols={["Picks"]}
          mobileTitleCol="Score Band"
          mobileSubtitleCol="Directional %"
          mobilePriorityCols={["Picks"]}
        />
      </div>
    </div>
  );
}

export function SimTab({ predictions }: { predictions: Prediction[] }) {
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
      <div className="rounded-lg border border-border bg-bg-2 p-4">
        <div className="section-header mt-0">Account Settings</div>
        <div className="flex items-center gap-3">
          <label className="text-xs text-text-2">Starting Account:</label>
          <input
            type="number"
            value={accountSize}
            onChange={(e) => setAccountSize(Number(e.target.value) || 10000)}
            className="w-32 rounded border border-border bg-bg-3 px-3 py-1.5 font-mono text-sm text-text-0"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-2 lg:grid-cols-4">
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

      {graded.length > 0 ? (
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
                Outcome:
                  prediction.outcome === "hit"
                    ? "\u2705 Hit"
                    : prediction.outcome === "directional"
                      ? "\uD83D\uDFE1 Dir"
                      : "\u274C Miss",
              };
            })}
            pnlCols={["P&L $", "P&L %"]}
            badgeCol="Direction"
            maxHeight="500px"
            mobileTitleCol="Ticker"
            mobileSubtitleCol="P&L %"
            mobilePriorityCols={SIM_MOBILE_PRIORITY_COLS}
          />
        </div>
      ) : null}
    </div>
  );
}

export function SectorsTab({
  sectors,
  loading = false,
  error,
}: {
  sectors: SectorSentiment[];
  loading?: boolean;
  error?: string | null;
}) {
  if (error) {
    return (
      <div className="rounded-lg border border-red/30 bg-red-dim p-6 text-center text-sm text-red">
        {error}
      </div>
    );
  }

  if (sectors.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-bg-2 p-6 text-center text-sm text-text-3">
        {loading ? "Loading sector data..." : "No sector data returned."}
      </div>
    );
  }

  const availableSectors = sectors.filter((sector) => sector.data_status !== "unavailable" && sector.near_sent !== "Unavailable");
  const unavailableCount = sectors.length - availableSectors.length;
  const bullCount = availableSectors.filter((sector) => sector.near_sent.includes("Bullish")).length;
  const bearCount = availableSectors.filter((sector) => sector.near_sent.includes("Bearish")).length;
  const neutralCount = availableSectors.length - bullCount - bearCount;

  const biasLabel = bullCount > bearCount ? "Bullish Bias" : bearCount > bullCount ? "Bearish Bias" : "Mixed/Neutral";
  const biasColor = bullCount > bearCount ? "text-green" : bearCount > bullCount ? "text-red" : "text-text-3";

  return (
    <div>
      <div className="section-header">Sector Sentiment Dashboard</div>
      <p className="mb-4 text-xs text-text-3">
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
                  <span className="ml-1.5 text-xs text-text-3">{sector.etf}</span>
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
        {unavailableCount > 0 ? (
          <>
            &middot;{" "}
            <span className="text-amber">
              {unavailableCount} unavailable
            </span>{" "}
          </>
        ) : null}
        &mdash; <strong className={biasColor}>{biasLabel}</strong>
      </div>
    </div>
  );
}
