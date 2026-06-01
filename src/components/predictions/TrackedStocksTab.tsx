"use client";

import { memo } from "react";
import { RefreshCw } from "lucide-react";
import Button from "@/components/ui/Button";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { fmtDate, fmtPct, metricToneClass } from "@/components/predictions/tradingDeskFormat";

export type TrackedStockSummary = {
  ticker: string;
  totalRows: number;
  openRows: number;
  closedRows: number;
  liveExactRows: number;
  researchRows: number;
  realizedRows: number;
  unpricedClosedRows: number;
  closeNowCount: number;
  holdCount: number;
  waitingCount: number;
  openPnlPct: number | null;
  realizedPnlPct: number | null;
  avgPnlPct: number | null;
  latestSignalDate: string | null;
  latestTradeDate: string | null;
  statusLabel: string;
  laneLabels: string[];
};

type TrackedStocksTabProps = {
  summaries: TrackedStockSummary[];
  openPositionCount: number;
  closedPositionCount: number;
  loading: boolean;
  error: string | null;
  closedRowsLoaded: boolean;
  closedRowsHasMore: boolean;
  onRefresh: () => void;
};

function average(values: Array<number | null>): number | null {
  const valid = values.filter((value): value is number => value != null && !Number.isNaN(value));
  return valid.length > 0 ? valid.reduce((sum, value) => sum + value, 0) / valid.length : null;
}

function SummaryPill({
  label,
  value,
  detail,
  toneClass = "text-text-0",
}: {
  label: string;
  value: string;
  detail: string;
  toneClass?: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-border-subtle bg-bg-1 px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-3">{label}</div>
      <div className={`mt-1 truncate font-mono text-sm font-semibold ${toneClass}`}>{value}</div>
      <div className="mt-0.5 truncate text-xs text-text-2">{detail}</div>
    </div>
  );
}

export const TrackedStocksTab = memo(function TrackedStocksTab({
  summaries,
  openPositionCount,
  closedPositionCount,
  loading,
  error,
  closedRowsLoaded,
  closedRowsHasMore,
  onRefresh,
}: TrackedStocksTabProps) {
  const openStockCount = summaries.filter((summary) => summary.openRows > 0).length;
  const closeNowStockCount = summaries.filter((summary) => summary.closeNowCount > 0).length;
  const realizedRowCount = summaries.reduce((sum, summary) => sum + summary.realizedRows, 0);
  const missingPnlCount = summaries.reduce((sum, summary) => sum + summary.unpricedClosedRows, 0);
  const avgOpenPnl = average(summaries.map((summary) => summary.openPnlPct));
  const avgRealizedPnl = average(summaries.map((summary) => summary.realizedPnlPct));

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 border-b border-border-subtle pb-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <div className="text-lg font-semibold text-text-0">Tracked Stocks</div>
          <div className="mt-1 text-sm text-text-2">
            {openStockCount} live tickers, {openPositionCount} open rows, {closedRowsLoaded ? `${closedPositionCount}${closedRowsHasMore ? "+" : ""} closed rows loaded` : "closed rows load on demand"}
          </div>
        </div>
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

      {error ? (
        <div className="rounded-lg border border-red/30 bg-red-dim px-4 py-3 text-sm text-red">
          {error}
        </div>
      ) : null}

      {!error && summaries.length > 0 ? (
        <div className="grid grid-cols-2 gap-2 xl:grid-cols-5">
          <SummaryPill
            label="Needs Action"
            value={closeNowStockCount > 0 ? `${closeNowStockCount} ticker${closeNowStockCount === 1 ? "" : "s"}` : "None"}
            detail="open SELL reviews"
            toneClass={closeNowStockCount > 0 ? "text-red" : "text-green"}
          />
          <SummaryPill
            label="Open P&L"
            value={fmtPct(avgOpenPnl)}
            detail={`${openPositionCount} open rows`}
            toneClass={metricToneClass(avgOpenPnl)}
          />
          <SummaryPill
            label="Realized P&L"
            value={fmtPct(avgRealizedPnl)}
            detail={`${realizedRowCount}${closedRowsHasMore ? "+" : ""} priced exits`}
            toneClass={metricToneClass(avgRealizedPnl)}
          />
          <SummaryPill
            label="Missing P&L"
            value={missingPnlCount > 0 ? String(missingPnlCount) : "0"}
            detail="closed rows without exit proof"
            toneClass={missingPnlCount > 0 ? "text-amber" : "text-text-1"}
          />
          <SummaryPill
            label="Universe"
            value={String(summaries.length)}
            detail={`${openStockCount} with open trades`}
          />
        </div>
      ) : null}

      {loading && summaries.length === 0 && !error ? (
        <TableSkeleton rows={6} />
      ) : summaries.length === 0 && !error ? (
        <div className="rounded-lg border border-border bg-bg-2 p-6 text-center text-sm text-text-3">
          No tracked stocks yet.
        </div>
      ) : !error ? (
        <div className="overflow-hidden rounded-lg border border-border bg-bg-2" role="region" aria-label="Tracked stocks">
          <div className="hidden grid-cols-[minmax(9rem,0.9fr)_minmax(8rem,0.8fr)_minmax(8rem,0.8fr)_minmax(8rem,0.75fr)_minmax(0,1.25fr)] gap-3 border-b border-border-subtle bg-bg-3 px-3 py-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2 lg:grid">
            <div>Ticker</div>
            <div>Open</div>
            <div>Realized</div>
            <div>Data</div>
            <div>Context</div>
          </div>
          <div className="max-h-[min(calc(100vh-18rem),820px)] overflow-auto">
            {summaries.map((summary) => (
              <TrackedStockRow key={summary.ticker} summary={summary} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
});

function MetricBlock({
  label,
  value,
  detail,
  valueClassName = "text-text-0",
}: {
  label: string;
  value: string;
  detail: string;
  valueClassName?: string;
}) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-text-3">{label}</div>
      <div className={`mt-1 truncate font-mono text-base font-semibold leading-none ${valueClassName}`}>{value}</div>
      <div className="mt-1 truncate text-xs text-text-2">{detail}</div>
    </div>
  );
}

const TrackedStockRow = memo(function TrackedStockRow({ summary }: { summary: TrackedStockSummary }) {
  const visibleLanes = summary.laneLabels.slice(0, 2);
  const hiddenLaneCount = Math.max(summary.laneLabels.length - visibleLanes.length, 0);
  const isActionable = summary.closeNowCount > 0;
  const hasOpenRisk = summary.openRows > 0 && (summary.openPnlPct ?? 0) < -40;
  const statusTone = isActionable
    ? "border-red/40 bg-red-dim text-red"
    : hasOpenRisk
      ? "border-amber/35 bg-amber-dim text-amber"
      : summary.openRows > 0
        ? "border-accent/30 bg-accent-dim text-accent"
        : "border-border bg-bg-3 text-text-2";
  const statusText = isActionable
    ? `${summary.closeNowCount} close now`
    : summary.holdCount > 0
      ? `${summary.holdCount} hold`
      : summary.waitingCount > 0
        ? `${summary.waitingCount} waiting`
        : "Closed only";
  const dataValue = summary.closedRows === 0
    ? "No closes"
    : summary.unpricedClosedRows > 0
      ? `${summary.unpricedClosedRows} missing`
      : "Priced";
  const dataTone = summary.unpricedClosedRows > 0 ? "text-amber" : "text-text-1";

  return (
    <div
      className={`grid gap-3 border-b border-border-subtle px-3 py-3 last:border-b-0 lg:grid-cols-[minmax(9rem,0.9fr)_minmax(8rem,0.8fr)_minmax(8rem,0.8fr)_minmax(8rem,0.75fr)_minmax(0,1.25fr)] lg:items-center ${isActionable ? "bg-red-dim" : "hover:bg-bg-3"}`}
    >
      <div className="flex items-start justify-between gap-3 lg:block">
        <div className="min-w-0">
          <div className="font-mono text-lg font-bold leading-none text-text-0 lg:text-base">{summary.ticker}</div>
          <div className={`mt-2 inline-flex rounded border px-2 py-0.5 text-[11px] font-semibold ${statusTone}`}>
            {statusText}
          </div>
        </div>
        <div className={`font-mono text-sm font-semibold lg:hidden ${metricToneClass(summary.openPnlPct)}`}>
          {fmtPct(summary.openPnlPct)}
        </div>
      </div>

      <MetricBlock
        label="Open"
        value={summary.openRows > 0 ? `${summary.openRows} row${summary.openRows === 1 ? "" : "s"}` : "0 rows"}
        detail={`${fmtPct(summary.openPnlPct)} live P&L`}
        valueClassName={summary.openRows > 0 ? "text-text-0" : "text-text-2"}
      />

      <MetricBlock
        label="Realized"
        value={fmtPct(summary.realizedPnlPct)}
        detail={`${summary.realizedRows}/${summary.closedRows} exits priced`}
        valueClassName={metricToneClass(summary.realizedPnlPct)}
      />

      <MetricBlock
        label="Data"
        value={dataValue}
        detail={`${summary.liveExactRows} proof / ${summary.researchRows} research`}
        valueClassName={dataTone}
      />

      <div className="min-w-0 space-y-2">
        <div className="flex min-w-0 flex-wrap gap-1.5">
          {visibleLanes.length > 0 ? visibleLanes.map((label) => (
            <span
              key={label}
              className="max-w-full truncate rounded border border-border bg-bg-1 px-2 py-1 text-[11px] text-text-1"
              title={label}
            >
              {label}
            </span>
          )) : (
            <span className="text-xs text-text-3">No lane</span>
          )}
          {hiddenLaneCount > 0 ? (
            <span
              className="rounded border border-border bg-bg-3 px-2 py-1 text-[11px] text-text-2"
              title={summary.laneLabels.join(", ")}
            >
              +{hiddenLaneCount}
            </span>
          ) : null}
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs text-text-2">
          <div>
            <span className="text-text-3">Signal </span>
            <span className="font-mono text-text-1">{fmtDate(summary.latestSignalDate)}</span>
          </div>
          <div>
            <span className="text-text-3">Trade </span>
            <span className="font-mono text-text-1">{fmtDate(summary.latestTradeDate)}</span>
          </div>
        </div>
      </div>
    </div>
  );
});
