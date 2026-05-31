"use client";

import { Play } from "lucide-react";
import { useMemo } from "react";
import Button from "@/components/ui/Button";
import FinTable from "@/components/ui/FinTable";
import MetricCard from "@/components/ui/MetricCard";
import type {
  BacktestPricingLane,
  BacktestReplayReport,
  BacktestResult,
  MetricTruthReport,
  TruthLane,
  TruthLaneComparisonReport,
  TruthLaneSummary,
} from "@/lib/types";
import { fmtTruthSource } from "@/components/strategy/shared";

function fmtCount(value?: number | null): string {
  return value == null || Number.isNaN(value) ? "\u2014" : value.toLocaleString();
}

function fmtNumber(value?: number | null, digits: number = 1): string {
  return value == null || Number.isNaN(value) ? "\u2014" : value.toFixed(digits);
}

function fmtPct(value?: number | null, digits: number = 1, signed: boolean = false): string {
  if (value == null || Number.isNaN(value)) return "\u2014";
  const prefix = signed && value >= 0 ? "+" : "";
  return `${prefix}${value.toFixed(digits)}%`;
}

function fmtMoney(value?: number | null, digits: number = 2): string {
  return value == null || Number.isNaN(value) ? "\u2014" : `$${value.toFixed(digits)}`;
}

type OptimizerTabProps = {
  backtestYears: number;
  setBacktestYears: (v: number) => void;
  ivAdj: number;
  setIvAdj: (v: number) => void;
  truthLane: TruthLane;
  setTruthLane: (v: TruthLane) => void;
  pricingLane: BacktestPricingLane;
  setPricingLane: (v: BacktestPricingLane) => void;
  running: boolean;
  onRun: () => void;
  result: BacktestResult | null;
  report: BacktestReplayReport | null;
  metricTruthReport: MetricTruthReport | null;
  comparisonReport: TruthLaneComparisonReport | null;
  artifactNotice: string | null;
};

export function OptimizerTab({
  backtestYears,
  setBacktestYears,
  ivAdj,
  setIvAdj,
  truthLane,
  setTruthLane,
  pricingLane,
  setPricingLane,
  running,
  onRun,
  result,
  report,
  metricTruthReport,
  comparisonReport,
  artifactNotice,
}: OptimizerTabProps) {
  const yearsInputId = "backtest-years";
  const ivAdjInputId = "iv-premium-adjustment";
  const summaryMetrics = useMemo(() => {
    if (!result) return null;
    return {
      totalTrades: fmtCount(result.total_trades),
      winRate: fmtPct(result.win_rate_pct),
      fullHitRate: fmtPct(result.full_hit_rate_pct),
      directionalAccuracy: fmtPct(result.directional_accuracy_pct),
      profitFactor: fmtNumber(result.profit_factor, 2),
      avgPnl: fmtPct(result.avg_pnl_pct),
      avgPicksPerDay: fmtNumber(result.avg_picks_per_day, 2),
      sharpe: fmtNumber(result.sharpe, 2),
      maxDrawdown: fmtPct(result.max_drawdown_pct),
      truthSource: fmtTruthSource(result.truth_source || result.source?.truth_source || report?.truth_source),
      quoteCoverage: result.quote_coverage_pct ?? report?.quote_coverage_pct ?? null,
      pricedTradeCount: result.priced_trade_count ?? report?.priced_trade_count ?? null,
      unpricedTradeCount: result.unpriced_trade_count ?? report?.unpriced_trade_count ?? null,
      entryQuoteTime: result.entry_quote_time_et ?? report?.entry_quote_time_et ?? null,
      exitQuoteTime: result.exit_quote_time_et ?? report?.exit_quote_time_et ?? null,
      promotionStatus: String(result.source?.promotion_status || report?.source?.promotion_status || "block").toUpperCase(),
    };
  }, [report, result]);

  const truthBandRows = useMemo(() => {
    if (!metricTruthReport?.metric_buckets?.direction_score) return [];
    return metricTruthReport.metric_buckets.direction_score
      .filter((bucket) => bucket.trades > 0)
      .map((bucket) => ({
        Band: bucket.label,
        Trades: bucket.trades.toLocaleString(),
        "Win Rate": `${bucket.win_rate_pct.toFixed(1)}%`,
        "Dir Accuracy": `${bucket.directional_accuracy_pct.toFixed(1)}%`,
        "Profit Factor": bucket.profit_factor.toFixed(2),
        "Avg P&L": `${bucket.avg_pnl_pct >= 0 ? "+" : ""}${bucket.avg_pnl_pct.toFixed(2)}%`,
        "Cal Gap":
          bucket.calibration_gap_pct == null
            ? "\u2014"
            : `${bucket.calibration_gap_pct >= 0 ? "+" : ""}${bucket.calibration_gap_pct.toFixed(1)} pts`,
      }));
  }, [metricTruthReport]);

  const tradeRows = useMemo(() => {
    if (!result?.trades) return [];
    return result.trades.map((trade) => ({
      Date: trade.date,
      Ticker: trade.ticker,
      Type: trade.type === "call" ? "\u25B2 CALL" : "\u25BC PUT",
      Sector: trade.sector || "\u2014",
      "Dir Score": fmtNumber(trade.direction_score, 0),
      Quality: fmtNumber(trade.quality_score, 0),
      Tech: fmtNumber(trade.tech_score, 0),
      EV: fmtPct(trade.ev, 0),
      "Target Move": fmtPct(trade.target_move_pct),
      Strike: fmtMoney(trade.strike, 0),
      "Entry $": fmtMoney(trade.entry_px),
      "Exit $": fmtMoney(trade.exit_px),
      "P&L %": fmtPct(trade.pnl_pct, 1, true),
      Outcome: trade.prediction_outcome || "\u2014",
      Exit: trade.exit_reason || "\u2014",
    }));
  }, [result]);

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border bg-bg-2 p-4">
        <div className="section-header mt-0">Replay Configuration</div>
        <div className="mb-4 grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_0.8fr]">
          <div>
            <label className="mb-1 block text-xs text-text-2">Validation lane</label>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant={truthLane === "historical_imported_daily" ? "primary" : "secondary"} onClick={() => setTruthLane("historical_imported_daily")}>
                Imported daily
              </Button>
              <Button size="sm" variant={truthLane === "historical_imported" ? "primary" : "secondary"} onClick={() => setTruthLane("historical_imported")}>
                Imported intraday
              </Button>
              <Button size="sm" variant={truthLane === "synthetic" ? "primary" : "secondary"} onClick={() => setTruthLane("synthetic")}>
                Synthetic research
              </Button>
            </div>
            <div className="mt-2 text-xs text-text-3">
              {truthLane === "historical_imported"
                ? "Higher-trust intraday validation lane. It prices model-targeted contracts with imported historical intraday quotes and leaves missing quotes unpriced."
                : truthLane === "historical_imported_daily"
                  ? "Free daily validation lane. It prices model-targeted contracts with imported end-of-day quotes, which is stronger than synthetic but still not morning-fill proof."
                  : "Fast research lane. Useful for ranking ideas, not for proving live options profitability."}
            </div>
          </div>
          <div>
            <label htmlFor={yearsInputId} className="mb-1 block text-xs text-text-2">Years of history</label>
            <input
              id={yearsInputId}
              type="range"
              min={2}
              max={7}
              step={1}
              value={backtestYears}
              onChange={(e) => setBacktestYears(Number(e.target.value))}
              className="w-full accent-accent"
            />
            <div className="mt-1 text-xs font-mono text-text-0">{backtestYears} years</div>
          </div>
        </div>

        <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs text-text-2">Synthetic pricing lane</label>
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant={pricingLane === "pessimistic" ? "primary" : "secondary"} onClick={() => setPricingLane("pessimistic")}>
                Pessimistic
              </Button>
              <Button size="sm" variant={pricingLane === "mid" ? "primary" : "secondary"} onClick={() => setPricingLane("mid")}>
                Mid
              </Button>
            </div>
            <div className="mt-2 text-xs text-text-3">
              {truthLane === "synthetic"
                ? "Choose which synthetic replay lane to run for research-only comparisons."
                : "Synthetic pricing is ignored for imported validation runs."}
            </div>
          </div>
          <div>
            <label htmlFor={ivAdjInputId} className="mb-1 block text-xs text-text-2">IV premium adjustment</label>
            <input
              id={ivAdjInputId}
              type="range"
              min={1.0}
              max={1.5}
              step={0.05}
              value={ivAdj}
              onChange={(e) => setIvAdj(Number(e.target.value))}
              className="w-full accent-accent"
              disabled={truthLane !== "synthetic"}
            />
            <div className="mt-1 text-xs font-mono text-text-0">{ivAdj.toFixed(2)}x</div>
          </div>
        </div>

        <Button variant="primary" onClick={onRun} loading={running} icon={running ? undefined : <Play size={14} />}>
          {running ? "Running Backtest..." : "Run Historical Backtest"}
        </Button>
      </div>

      {!summaryMetrics && artifactNotice ? (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-100">
          {artifactNotice}
        </div>
      ) : null}

      {summaryMetrics ? (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
            <MetricCard label="Total Trades" value={summaryMetrics.totalTrades} />
            <MetricCard label="Profit Factor" value={summaryMetrics.profitFactor} />
            <MetricCard label="Avg P&L/Trade" value={summaryMetrics.avgPnl} />
            <MetricCard label="Quote Coverage" value={summaryMetrics.quoteCoverage == null ? "\u2014" : `${summaryMetrics.quoteCoverage.toFixed(1)}%`} />
            <MetricCard label="Promotion" value={summaryMetrics.promotionStatus} />
            <MetricCard
              label="Priced / Unpriced"
              value={
                summaryMetrics.pricedTradeCount != null || summaryMetrics.unpricedTradeCount != null
                  ? `${summaryMetrics.pricedTradeCount ?? 0} / ${summaryMetrics.unpricedTradeCount ?? 0}`
                : "\u2014"
              }
            />
          </div>

          <details className="rounded-lg border border-border bg-bg-2 px-4 py-3">
            <summary className="cursor-pointer text-sm font-semibold text-text-0">Secondary replay metrics</summary>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
              <MetricCard label="Win Rate" value={summaryMetrics.winRate} />
              <MetricCard label="Full Hit Rate" value={summaryMetrics.fullHitRate} />
              <MetricCard label="Directional Accuracy" value={summaryMetrics.directionalAccuracy} />
              <MetricCard label="Avg Picks/Day" value={summaryMetrics.avgPicksPerDay} />
              <MetricCard label="Sharpe" value={summaryMetrics.sharpe} />
              <MetricCard label="Max Drawdown" value={summaryMetrics.maxDrawdown} />
              <MetricCard label="Truth Source" value={summaryMetrics.truthSource} />
            </div>
          </details>

          <div className="space-y-2 rounded-lg border border-border bg-bg-2 p-4">
            <div className="section-header mt-0">Validation Lane</div>
            <div className="text-sm text-text-2">
              {summaryMetrics.truthSource === "Imported historical validation"
                ? "This replay uses imported intraday historical option quotes for pricing. It is the strongest lane in the app today, but contract targeting is still replay-model-derived rather than a perfect reconstruction of archived live picks."
                : summaryMetrics.truthSource === "Imported daily validation"
                  ? "This replay uses imported daily end-of-day option quotes for pricing. It is materially better than synthetic, but still not a proof of morning entry quality."
                  : "This replay is synthetic research-only. It is useful for ranking hypotheses, but not for proving profitability."}
            </div>
            <div className="text-xs uppercase tracking-wide text-text-3">
              {result?.truth_source || report?.truth_source ? `Truth ${summaryMetrics.truthSource}` : "Truth Synthetic research-only"}
              {summaryMetrics.quoteCoverage != null ? ` | Coverage ${summaryMetrics.quoteCoverage.toFixed(1)}%` : ""}
              {result?.priced_trade_count != null || result?.unpriced_trade_count != null
                ? ` | Priced ${result?.priced_trade_count ?? 0} / Unpriced ${result?.unpriced_trade_count ?? 0}`
                : ""}
            </div>
            {summaryMetrics.entryQuoteTime || summaryMetrics.exitQuoteTime ? (
              <div className="text-xs text-text-3">
                Entry window {summaryMetrics.entryQuoteTime || "\u2014"}
                {summaryMetrics.exitQuoteTime ? ` | Exit mark ${summaryMetrics.exitQuoteTime}` : ""}
              </div>
            ) : null}
          </div>

          {metricTruthReport ? (
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.1fr_0.9fr]">
              <div className="space-y-4 rounded-lg border border-border bg-bg-2 p-4">
                <div>
                  <div className="section-header mt-0">Metric Truth Audit</div>
                  <p className="text-sm text-text-2">
                    This checks whether the current score stack is actually aligned with profitable outcomes.
                    Synthetic research helps us rank ideas, but imported validation is what should carry the strongest truth claim.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                  <MetricCard label="Truth Trades" value={fmtCount(metricTruthReport.source.total_trades)} />
                  <MetricCard label="Bucket Size" value={`${metricTruthReport.quality_bar.bucket_size} pts`} />
                  <MetricCard label="Min Trades" value={metricTruthReport.quality_bar.min_trades.toLocaleString()} />
                  <MetricCard
                    label="Best Dir Floor"
                    value={
                      metricTruthReport.metric_health?.direction_score?.best_floor
                        ? `>=${metricTruthReport.metric_health.direction_score.best_floor.floor}`
                        : "None"
                    }
                  />
                  <MetricCard label="Truth Source" value={fmtTruthSource(metricTruthReport.source.truth_source)} />
                </div>

                <div className="text-xs uppercase tracking-wide text-text-3">
                  {metricTruthReport.source.truth_source ? fmtTruthSource(metricTruthReport.source.truth_source) : "Synthetic research-only"}
                  {metricTruthReport.source.quote_coverage_pct != null ? ` | Coverage ${metricTruthReport.source.quote_coverage_pct.toFixed(1)}%` : ""}
                  {metricTruthReport.source.priced_trade_count != null || metricTruthReport.source.unpriced_trade_count != null
                    ? ` | Priced ${metricTruthReport.source.priced_trade_count ?? 0} / Unpriced ${metricTruthReport.source.unpriced_trade_count ?? 0}`
                    : ""}
                </div>
                {metricTruthReport.source.entry_quote_time_et || metricTruthReport.source.exit_quote_time_et ? (
                  <div className="text-xs text-text-3">
                    Entry window {metricTruthReport.source.entry_quote_time_et || "\u2014"}
                    {metricTruthReport.source.exit_quote_time_et ? ` | Exit mark ${metricTruthReport.source.exit_quote_time_et}` : ""}
                  </div>
                ) : null}
                {truthBandRows.length > 0 ? (
                  <div>
                    <div className="section-header">Direction Score Bands</div>
                    <FinTable
                      data={truthBandRows}
                      pnlCols={["Avg P&L"]}
                      monoCols={["Trades", "Win Rate", "Dir Accuracy", "Profit Factor", "Avg P&L", "Cal Gap"]}
                      maxHeight="320px"
                    />
                  </div>
                ) : null}
              </div>

              <div className="space-y-4">
                <div className="rounded-lg border border-border bg-bg-2 p-4">
                  <div className="section-header mt-0">Risk Flags</div>
                  {metricTruthReport.risk_flags.length > 0 ? (
                    <ul className="space-y-2 text-sm text-rose-300">
                      {metricTruthReport.risk_flags.map((flag) => (
                        <li key={flag} className="rounded-md border border-rose-500/30 bg-rose-500/10 px-3 py-2">
                          {flag}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-text-2">No audit flags on the current replay.</p>
                  )}
                </div>

                <div className="rounded-lg border border-border bg-bg-2 p-4">
                  <div className="section-header mt-0">Recommendations</div>
                  <ul className="space-y-2 text-sm text-text-1">
                    {metricTruthReport.recommendations.map((item) => (
                      <li key={item} className="rounded-md border border-border bg-bg-3/40 px-3 py-2">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          ) : null}

          {report ? (
            <div className="space-y-4 rounded-lg border border-border bg-bg-2 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="section-header mt-0">Replay Report</div>
                  <p className="text-sm text-text-2">
                    A grouped replay view of the current options lane. Truth-source, coverage, and pricing metadata are shown here explicitly so we do not over-read synthetic research as validated profitability.
                  </p>
                </div>
                <div className="text-right text-xs uppercase tracking-wide text-text-3">
                  {fmtTruthSource(report.truth_source || report.source?.truth_source)}
                  {report.quote_coverage_pct != null ? ` | Coverage ${report.quote_coverage_pct.toFixed(1)}%` : ""}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <MetricCard label="Grouped Trades" value={fmtCount(report.source.total_trades)} />
                <MetricCard label="Truth Source" value={fmtTruthSource(report.truth_source || report.source?.truth_source)} />
                <MetricCard
                  label="Priced / Unpriced"
                  value={
                    report.priced_trade_count != null || report.unpriced_trade_count != null
                      ? `${report.priced_trade_count ?? 0} / ${report.unpriced_trade_count ?? 0}`
                      : "\u2014"
                  }
                />
                <MetricCard label="Coverage" value={report.quote_coverage_pct != null ? `${report.quote_coverage_pct.toFixed(1)}%` : "\u2014"} />
              </div>
              {report.entry_quote_time_et || report.exit_quote_time_et ? (
                <div className="text-xs text-text-3">
                  Entry window {report.entry_quote_time_et || "\u2014"}
                  {report.exit_quote_time_et ? ` | Exit mark ${report.exit_quote_time_et}` : ""}
                </div>
              ) : null}
            </div>
          ) : null}

          {comparisonReport ? (
            <div className="space-y-4 rounded-lg border border-border bg-bg-2 p-4">
              <div>
                <div className="section-header mt-0">Synthetic vs Imported Comparison</div>
                <p className="text-sm text-text-2">
                  This disagreement view compares the latest synthetic research run with the selected imported quote-validation lane so we can see how much the research lane drifts once real option quotes are used.
                </p>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {([
                  ["Synthetic", comparisonReport.synthetic],
                  ["Imported", comparisonReport.imported],
                ] as Array<[string, TruthLaneSummary | null | undefined]>).map(([label, lane]) => (
                  <div key={label} className="space-y-1 rounded-lg border border-border bg-bg-3 p-3">
                    <div className="text-xs uppercase tracking-wide text-text-3">{label}</div>
                    <div className="text-sm text-text-1">{lane ? fmtTruthSource(lane.truth_source) : "\u2014"}</div>
                    <div className="text-xs text-text-3">
                      Trades {fmtCount(lane?.total_trades)}
                      {lane?.profit_factor != null ? ` | PF ${fmtNumber(lane.profit_factor, 2)}` : ""}
                      {lane?.avg_pnl_pct != null ? ` | Avg ${fmtPct(lane.avg_pnl_pct, 2)}` : ""}
                      {lane?.directional_accuracy_pct != null ? ` | Dir ${fmtPct(lane.directional_accuracy_pct)}` : ""}
                    </div>
                    <div className="text-xs text-text-3">
                      Coverage {lane?.quote_coverage_pct != null ? `${lane.quote_coverage_pct.toFixed(1)}%` : "\u2014"}
                      {lane?.promotion_status ? ` | Policy ${String(lane.promotion_status).toUpperCase()}` : ""}
                    </div>
                  </div>
                ))}
              </div>

              {comparisonReport.deltas ? (
                <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
                  <MetricCard label="Trade Delta" value={String(comparisonReport.deltas.total_trades)} />
                  <MetricCard label="PF Delta" value={fmtNumber(comparisonReport.deltas.profit_factor, 2)} />
                  <MetricCard label="Avg P&L Delta" value={fmtPct(comparisonReport.deltas.avg_pnl_pct, 2)} />
                  <MetricCard label="Dir Delta" value={fmtPct(comparisonReport.deltas.directional_accuracy_pct)} />
                  <MetricCard label="Coverage Delta" value={fmtPct(comparisonReport.deltas.quote_coverage_pct)} />
                </div>
              ) : null}

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div className="rounded-lg border border-border bg-bg-3 p-3">
                  <div className="text-[11px] uppercase tracking-wide text-text-3">Coverage Notes</div>
                  <div className="mt-1 text-sm text-text-1">
                    Matching priced trades {comparisonReport.matching_priced_trade_count ?? 0} | Unsupported by imported lane {comparisonReport.unsupported_by_import_count ?? 0}
                  </div>
                </div>
                <div className="rounded-lg border border-border bg-bg-3 p-3">
                  <div className="text-[11px] uppercase tracking-wide text-text-3">Warnings</div>
                  <div className="mt-1 text-sm text-text-1">
                    {(comparisonReport.warnings?.length ? comparisonReport.warnings : comparisonReport.notes || ["No comparison warnings."]).join(" ")}
                  </div>
                </div>
              </div>
            </div>
          ) : null}

          {tradeRows.length > 0 ? (
            <div>
              <div className="section-header">All Trades ({tradeRows.length})</div>
              <FinTable
                data={tradeRows}
                pnlCols={["P&L %"]}
                badgeCol="Type"
                monoCols={["Dir Score", "Quality", "Tech", "Target Move", "Strike", "Entry $", "Exit $"]}
                maxHeight="600px"
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
