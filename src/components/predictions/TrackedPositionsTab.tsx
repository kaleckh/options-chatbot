"use client";

import { memo, useEffect, useMemo, useRef, useState } from "react";
import { CalendarDays, CheckCircle, RefreshCw } from "lucide-react";
import Button from "@/components/ui/Button";
import FinTable from "@/components/ui/FinTable";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { CompactStat } from "@/components/predictions/TradingDeskCompactStat";
import { fmtMoney, fmtPct, metricToneClass } from "@/components/predictions/tradingDeskFormat";
import {
  formatSignalLabel,
  getCollectionReviewSummary,
  isShareSafeLivePosition,
  renderClosedStatusCell,
  renderExpiryCell,
  renderOpenPnlCell,
  renderOpenPriceCell,
  renderPositionStatusCell,
  renderQuoteCell,
  renderRealizedPnlCell,
  SHARE_SAFE_REVIEW_MAX_AGE_MINUTES,
} from "@/components/predictions/tradingDeskCells";
import {
  ALL_POSITION_LANES,
  buildPositionLaneOptions,
  entryDateFilterLabel,
  fmtContractCoreLabel,
  fmtTakenDate,
  getPositionLaneDescriptor,
  getTradeDateFilterValue,
  isTakenWithinLast24Hours,
  laneMixSummary,
  matchesEntryDateFilter,
  matchesPositionLaneFilter,
  positionLaneFilterLabel,
  renderPositionLaneCell,
  renderTickerCell,
  type EntryDateFilterPreset,
  type PositionLaneOption,
} from "@/components/predictions/trackedPositionUtils";
import type { TrackedPosition } from "@/lib/types";
import {
  buildCurrentPolicyCohortHealth,
  calcAveragePositionPnlPct,
  closedDataViewLabel,
  getCloseNowPnlPct,
  getRealizedExitPrice,
  getRealizedPnlPct,
  isCurrentPolicyClosedPosition,
  isLearnedAwayClosedPosition,
  isProductionProofPosition,
  isRealizedPnlClosedPosition,
  isResearchLearningPosition,
  isTruthGradeClosedPosition,
  matchesClosedDataView,
  policyCohortHealthStatusLabel,
  summarizePositionOutcomes,
  type ClosedDataView,
  type PolicyCohortSummary,
} from "@/lib/trading-desk/positionEvidence";

type TrackedPositionsTabProps = {
  openPositions: TrackedPosition[];
  closedPositions: TrackedPosition[];
  loading: boolean;
  error: string | null;
  view: "open" | "closed";
  reviewingIds: number[];
  closedRowsLoaded: boolean;
  closedRowsHasMore: boolean;
  closedRowsLoading: boolean;
  onRefresh: () => void;
  onLoadClosedRows: (options?: { notify?: boolean }) => void;
  onReviewPosition: (positionId: number) => void;
  onOpenClose: (position: TrackedPosition) => void;
};

function fmtCohortAvg(summary?: PolicyCohortSummary | null): string {
  if (!summary) return "\u2014";
  return `${summary.key} ${fmtPct(summary.avgPnlPct)}`;
}

function isPickedToday(position: TrackedPosition): boolean {
  return matchesEntryDateFilter(getTradeDateFilterValue(position), "today", "");
}

function sortTodayPicks(items: TrackedPosition[]): TrackedPosition[] {
  return [...items].sort((a, b) => {
    const aTime = new Date(a.filled_at).getTime();
    const bTime = new Date(b.filled_at).getTime();
    const aSort = Number.isNaN(aTime) ? 0 : aTime;
    const bSort = Number.isNaN(bTime) ? 0 : bTime;
    return bSort - aSort || b.id - a.id;
  });
}

function TodayPicksStrip({
  positions,
  selectedLaneLabel,
  entryDatePreset,
  entryDateValue,
  onShowToday,
}: {
  positions: TrackedPosition[];
  selectedLaneLabel: string | null;
  entryDatePreset: EntryDateFilterPreset;
  entryDateValue: string;
  onShowToday: () => void;
}) {
  const dateLabel = entryDateFilterLabel(entryDatePreset, entryDateValue);
  const showingToday = entryDatePreset === "today";
  const sublabel = selectedLaneLabel
    ? `${selectedLaneLabel} / ${positions.length} picked today`
    : `${positions.length} picked today`;

  return (
    <section
      className="rounded-lg border border-green/30 bg-green-dim px-3 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.04)]"
      aria-label="Trades picked today"
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-green/40 bg-bg-1 text-green">
            <CalendarDays size={15} aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <div className="text-sm font-semibold text-text-0">Today&apos;s Picks</div>
            <div className="truncate text-xs text-text-2">{sublabel}</div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!showingToday && entryDatePreset !== "all" ? (
            <span className="rounded border border-border bg-bg-2 px-2 py-1 text-xs text-text-2">
              Table date: {dateLabel}
            </span>
          ) : null}
          <Button
            size="sm"
            variant={showingToday ? "secondary" : "ghost"}
            icon={<CalendarDays size={12} />}
            aria-pressed={showingToday}
            onClick={onShowToday}
          >
            Show Today
          </Button>
        </div>
      </div>

      {positions.length > 0 ? (
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1">
          {positions.map((position) => {
            const lane = getPositionLaneDescriptor(position);
            const pnlPct = getCloseNowPnlPct(position);
            const directionLabel = position.direction === "call" ? "CALL" : "PUT";
            return (
              <article
                key={position.id}
                className="min-w-[210px] max-w-[250px] flex-1 rounded-md border border-border bg-bg-1/80 px-3 py-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="truncate font-mono text-base font-semibold text-text-0">
                        {position.ticker}
                      </span>
                      <span className={position.direction === "call" ? "badge-call" : "badge-put"}>
                        {directionLabel}
                      </span>
                    </div>
                    <div className="truncate text-xs text-text-2">{lane.label}</div>
                  </div>
                  <div className={`shrink-0 font-mono text-sm font-semibold ${metricToneClass(pnlPct)}`}>
                    {fmtPct(pnlPct)}
                  </div>
                </div>
                <div className="mt-2 truncate text-xs text-text-3" title={fmtContractCoreLabel(position)}>
                  {fmtContractCoreLabel(position)}
                </div>
                <div className="mt-2 flex items-center justify-between gap-2 text-xs">
                  <span className="truncate text-text-2">
                    {formatSignalLabel(position.last_recommendation)}
                  </span>
                  <span className="shrink-0 font-mono text-text-3">{fmtTakenDate(position)}</span>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="mt-3 rounded-md border border-border bg-bg-1/70 px-3 py-2 text-sm text-text-2">
          No open trades picked today.
        </div>
      )}
    </section>
  );
}

function EntryDateFilterControls({
  preset,
  customDate,
  laneFilter,
  laneOptions,
  onPresetChange,
  onCustomDateChange,
  onLaneFilterChange,
}: {
  preset: EntryDateFilterPreset;
  customDate: string;
  laneFilter: string;
  laneOptions: PositionLaneOption[];
  onPresetChange: (value: EntryDateFilterPreset) => void;
  onCustomDateChange: (value: string) => void;
  onLaneFilterChange: (value: string) => void;
}) {
  const hasActiveFilter = preset !== "all" || laneFilter !== ALL_POSITION_LANES;

  return (
    <div className="rounded-lg border border-border bg-bg-2 px-3 py-2">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">
            Source
          </span>
          <Button
            size="sm"
            variant={laneFilter === ALL_POSITION_LANES ? "secondary" : "ghost"}
            aria-pressed={laneFilter === ALL_POSITION_LANES}
            onClick={() => onLaneFilterChange(ALL_POSITION_LANES)}
          >
            All
            <span className="font-mono text-[10px] text-text-3">
              {laneOptions.reduce((sum, option) => sum + option.count, 0)}
            </span>
          </Button>
          {laneOptions.map((option) => (
            <Button
              key={option.id}
              size="sm"
              variant={laneFilter === option.id ? "secondary" : "ghost"}
              aria-pressed={laneFilter === option.id}
              onClick={() => onLaneFilterChange(option.id)}
            >
              {option.label}
              <span className="font-mono text-[10px] text-text-3">{option.count}</span>
            </Button>
          ))}
        </div>

        <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">
              Entry Date
            </span>
            {([
              { id: "today", label: "Today" },
              { id: "yesterday", label: "Yesterday" },
              { id: "last7", label: "Last 7D" },
            ] as const).map((option) => (
              <Button
                key={option.id}
                size="sm"
                variant={preset === option.id ? "secondary" : "ghost"}
                onClick={() => onPresetChange(option.id)}
              >
                {option.label}
              </Button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <label className="flex items-center gap-2 text-xs text-text-2">
              <span className="whitespace-nowrap">Pick date</span>
              <input
                type="date"
                value={customDate}
                onChange={(event) => {
                  const value = event.target.value;
                  onCustomDateChange(value);
                  onPresetChange(value ? "custom" : "all");
                }}
                className="rounded border border-border bg-bg-3 px-2.5 py-1 text-xs text-text-0"
              />
            </label>
            {hasActiveFilter ? (
              <Button size="sm" variant="ghost" onClick={() => {
                onCustomDateChange("");
                onPresetChange("all");
                onLaneFilterChange(ALL_POSITION_LANES);
              }}>
                Clear
              </Button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export const TrackedPositionsTab = memo(function TrackedPositionsTab({
  openPositions,
  closedPositions,
  loading,
  error,
  view,
  reviewingIds,
  closedRowsLoaded,
  closedRowsHasMore,
  closedRowsLoading,
  onRefresh,
  onLoadClosedRows,
  onReviewPosition,
  onOpenClose,
}: TrackedPositionsTabProps) {
  const dedupedOpenPositions = openPositions;
  const [openFilter, setOpenFilter] = useState<"share-safe" | "all">("all");
  const [closedDataView, setClosedDataView] = useState<ClosedDataView>("current_policy");
  const [entryDatePreset, setEntryDatePreset] = useState<EntryDateFilterPreset>("all");
  const [entryDateValue, setEntryDateValue] = useState("");
  const [laneFilter, setLaneFilter] = useState(ALL_POSITION_LANES);
  const loadMoreSentinelRef = useRef<HTMLDivElement | null>(null);
  const shareSafeOpenPositions = dedupedOpenPositions.filter((position) => isShareSafeLivePosition(position));
  const hiddenOpenPositionCount = Math.max(dedupedOpenPositions.length - shareSafeOpenPositions.length, 0);
  const openBasePositions = openFilter === "share-safe" ? shareSafeOpenPositions : dedupedOpenPositions;
  const basePositions = view === "open" ? openBasePositions : closedPositions;
  const laneOptions = useMemo(
    () => buildPositionLaneOptions([...dedupedOpenPositions, ...closedPositions]),
    [closedPositions, dedupedOpenPositions]
  );
  const selectedLaneLabel = positionLaneFilterLabel(laneFilter, laneOptions);
  useEffect(() => {
    if (
      laneFilter !== ALL_POSITION_LANES &&
      !laneOptions.some((option) => option.id === laneFilter)
    ) {
      setLaneFilter(ALL_POSITION_LANES);
    }
  }, [laneFilter, laneOptions]);
  const filteredOpenPositions = openBasePositions.filter((position) =>
    matchesEntryDateFilter(getTradeDateFilterValue(position), entryDatePreset, entryDateValue) &&
    matchesPositionLaneFilter(position, laneFilter)
  );
  const dateLaneClosedPositions = closedPositions.filter((position) =>
    matchesEntryDateFilter(getTradeDateFilterValue(position), entryDatePreset, entryDateValue) &&
    matchesPositionLaneFilter(position, laneFilter)
  );
  const todayPickedPositions = useMemo(
    () => sortTodayPicks(dedupedOpenPositions.filter((position) =>
      isPickedToday(position) && matchesPositionLaneFilter(position, laneFilter)
    )),
    [dedupedOpenPositions, laneFilter]
  );
  const realizedPnlClosedPositions = dateLaneClosedPositions.filter(isRealizedPnlClosedPosition);
  const currentPolicyClosedPositions = dateLaneClosedPositions.filter(isCurrentPolicyClosedPosition);
  const learnedAwayClosedPositions = dateLaneClosedPositions.filter(isLearnedAwayClosedPosition);
  const truthGradeClosedPositions = dateLaneClosedPositions.filter(isTruthGradeClosedPosition);
  const filteredClosedPositions = dateLaneClosedPositions.filter((position) =>
    matchesClosedDataView(position, closedDataView)
  );
  const currentPolicyCohortHealth = useMemo(
    () => buildCurrentPolicyCohortHealth(currentPolicyClosedPositions),
    [currentPolicyClosedPositions]
  );
  const currentPolicyCohortState = closedRowsHasMore
    ? "Loading"
    : policyCohortHealthStatusLabel(currentPolicyCohortHealth.overallStatus);
  const positions = view === "open" ? filteredOpenPositions : filteredClosedPositions;
  const shouldOfferClosedPagination = view === "closed" && closedRowsHasMore && !error;
  const shouldAutoLoadNextClosedBatch = shouldOfferClosedPagination && positions.length > 0;
  useEffect(() => {
    if (!shouldAutoLoadNextClosedBatch || closedRowsLoading) return;
    const sentinel = loadMoreSentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        onLoadClosedRows();
      }
    }, {
      root: null,
      rootMargin: "320px 0px",
      threshold: 0,
    });

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [closedRowsLoading, onLoadClosedRows, shouldAutoLoadNextClosedBatch]);
  const recentVisiblePositionCount = positions.filter(isTakenWithinLast24Hours).length;
  const closedEvidenceHiddenCount = Math.max(dateLaneClosedPositions.length - filteredClosedPositions.length, 0);
  const hiddenByFilterCount = Math.max(
    (view === "open" ? basePositions.length : dateLaneClosedPositions.length) - positions.length,
    0
  );
  const productionOpenPositions = filteredOpenPositions.filter(isProductionProofPosition);
  const researchOpenPositions = filteredOpenPositions.filter(isResearchLearningPosition);
  const productionClosedPositions = filteredClosedPositions.filter(isProductionProofPosition);
  const truthGradeClosedSummary = summarizePositionOutcomes(truthGradeClosedPositions, getRealizedPnlPct);
  const visibleClosedSummary = summarizePositionOutcomes(filteredClosedPositions, getRealizedPnlPct);
  const productionOpenPnlPct = calcAveragePositionPnlPct(productionOpenPositions, getCloseNowPnlPct);
  const productionClosedSummary = summarizePositionOutcomes(productionClosedPositions, getRealizedPnlPct);
  const openReviewSummary = view === "open" ? getCollectionReviewSummary(positions) : null;
  const tableMaxHeight = view === "open"
    ? "min(calc(100vh - 18rem), 920px)"
    : "none";
  const buildRows = (items: TrackedPosition[]) =>
    items.map((position) => {
      const realizedPnl = getRealizedPnlPct(position);
      if (view === "open") {
        return {
          __rowKey: position.id,
          Ticker: renderTickerCell(position),
          Signal: renderPositionLaneCell(position),
          Trade: position.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
          Taken: fmtTakenDate(position),
          Entry: fmtMoney(position.entry_option_price),
          "Live Px": renderOpenPriceCell(position),
          "Live P&L": renderOpenPnlCell(position),
          Status: renderPositionStatusCell(position),
          Quote: renderQuoteCell(position),
          Expiry: renderExpiryCell(position),
          Action: (
            <div className="flex min-w-[126px] items-center gap-1.5">
              <Button
                size="sm"
                variant="secondary"
                icon={<RefreshCw size={12} />}
                loading={reviewingIds.includes(position.id)}
                onClick={() => onReviewPosition(position.id)}
              >
                Review
              </Button>
              <Button
                size="sm"
                variant="ghost"
                icon={<CheckCircle size={12} />}
                aria-label={`Mark ${position.ticker} trade closed`}
                title="Mark closed"
                onClick={() => onOpenClose(position)}
              >
                Close
              </Button>
            </div>
          ),
        };
      }

      return {
        __rowKey: position.id,
        Ticker: renderTickerCell(position),
        Signal: renderPositionLaneCell(position),
        Trade: position.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
        Taken: fmtTakenDate(position),
        Entry: fmtMoney(position.entry_option_price),
        "Exit Px": fmtMoney(getRealizedExitPrice(position)),
        "Realized P&L %": renderRealizedPnlCell(realizedPnl),
        Status: renderClosedStatusCell(position),
      };
    });

  const rows = buildRows(positions);

  return (
    <div className="space-y-2">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-2">
        <div className="max-w-3xl">
          <div className="text-lg font-semibold text-text-0">
            {view === "open" ? "Open Trades" : "Closed Trades"}
          </div>
          <p className="mt-1 text-sm text-text-2">
            {view === "open"
              ? "Open algorithm trades with live P&L, source signal dates, current status, and close actions."
              : "Closed algorithm trades for judging accuracy and average outcome."}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {view === "open" ? (
            <>
              <Button
                size="sm"
                variant={openFilter === "share-safe" ? "secondary" : "ghost"}
                aria-pressed={openFilter === "share-safe"}
                onClick={() => setOpenFilter("share-safe")}
              >
                Fresh Prices
              </Button>
              <Button
                size="sm"
                variant={openFilter === "all" ? "secondary" : "ghost"}
                aria-pressed={openFilter === "all"}
                onClick={() => setOpenFilter("all")}
              >
                All Trades
              </Button>
            </>
          ) : (
            <div className="inline-flex flex-wrap gap-1 rounded-md border border-border bg-bg-2 p-1">
              {([
                "current_policy",
                "learned_away",
                "realized_pnl",
                "truth_grade",
                "all",
                "historical_paper",
                "lifecycle_only",
                "unpriced",
                "legacy_unclassified",
              ] as ClosedDataView[]).map((item) => (
                <Button
                  key={item}
                  size="sm"
                  variant={closedDataView === item ? "secondary" : "ghost"}
                  aria-pressed={closedDataView === item}
                  onClick={() => setClosedDataView(item)}
                >
                  {closedDataViewLabel(item)}
                </Button>
              ))}
            </div>
          )}
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
        <EntryDateFilterControls
          preset={entryDatePreset}
          customDate={entryDateValue}
          laneFilter={laneFilter}
          laneOptions={laneOptions}
          onPresetChange={setEntryDatePreset}
          onCustomDateChange={setEntryDateValue}
          onLaneFilterChange={setLaneFilter}
        />
      )}

      {!error && view === "open" ? (
        <div className="grid grid-cols-2 gap-2 xl:grid-cols-6">
          <CompactStat label="Open Trades" value={String(filteredOpenPositions.length)} help="Open rows after the current filters" />
          <CompactStat label="Last 24h" value={String(recentVisiblePositionCount)} help="Visible trades taken in the last 24 hours" />
          <CompactStat label="Live Exact" value={String(productionOpenPositions.length)} help="Open production-proof rows after filters" />
          <CompactStat label="Research/Paper" value={String(researchOpenPositions.length)} help="Open research, historical paper, or proof-ineligible rows after filters" />
          <CompactStat label="Avg Live Exact P&L" value={fmtPct(productionOpenPnlPct)} help="Average executable P&L across open production-proof rows only" />
          <CompactStat label="Closed Proof Win" value={fmtPct(productionClosedSummary.winRatePct)} help="Closed win rate for production-proof rows only" />
        </div>
      ) : !error ? (
        <div className="grid grid-cols-2 gap-2 xl:grid-cols-6">
          {closedDataView === "current_policy" ? (
            <>
              <CompactStat label="Current Rows" value={`${currentPolicyClosedPositions.length}${closedRowsHasMore ? "+" : ""}`} help="Closed rows the current promoted entry policy would still take, with trusted realized P&L" />
              <CompactStat label="Current Avg" value={fmtPct(currentPolicyCohortHealth.overall.avgPnlPct)} help="Average realized P&L across current-policy rows after filters" />
              <CompactStat label="Showcase Month" value={fmtCohortAvg(currentPolicyCohortHealth.showcaseMonth)} help="Best sufficiently priced current-policy monthly cohort after filters" />
              <CompactStat label="Recent Month" value={fmtCohortAvg(currentPolicyCohortHealth.recentMonth)} help="Most recent current-policy monthly cohort after filters" />
              <CompactStat label="Recent Median" value={fmtPct(currentPolicyCohortHealth.recentMonth?.medianPnlPct)} help="Median realized P&L for the most recent current-policy monthly cohort" />
              <CompactStat label="Cohort State" value={currentPolicyCohortState} help="Recent cohort health state; paper-only means the recent cohort broke despite older showcase strength" />
            </>
          ) : (
            <>
              <CompactStat label="Current Rows" value={String(currentPolicyClosedPositions.length)} help="Closed rows the current promoted entry policy would still take, with trusted realized P&L" />
              <CompactStat label="Learned Away" value={String(learnedAwayClosedPositions.length)} help="Closed rows the current promoted entry policy would now block or flag" />
              <CompactStat label="Shown Rows" value={`${filteredClosedPositions.length}${closedRowsHasMore ? "+" : ""}`} help="Closed rows shown after evidence, date, and lane filters" />
              <CompactStat label="Shown Win Rate" value={fmtPct(visibleClosedSummary.winRatePct)} help="Win rate for the currently visible closed rows with realized P&L" />
              <CompactStat label="Shown Avg P&L" value={fmtPct(visibleClosedSummary.avgPnlPct)} help="Average realized P&L for the currently visible closed rows" />
              <CompactStat label="Truth Avg P&L" value={fmtPct(truthGradeClosedSummary.avgPnlPct)} help="Production-proof average P&L; this stays strict and may be empty when only historical paper rows are loaded" />
            </>
          )}
        </div>
      ) : null}

      {!error && view === "open" ? (
        <TodayPicksStrip
          positions={todayPickedPositions}
          selectedLaneLabel={selectedLaneLabel}
          entryDatePreset={entryDatePreset}
          entryDateValue={entryDateValue}
          onShowToday={() => {
            setEntryDateValue("");
            setEntryDatePreset("today");
          }}
        />
      ) : null}

      {!error && view === "open" ? (
        <div className="bg-bg-2 border border-border rounded-lg px-3 py-1.5 text-xs text-text-2 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
          <span>
            {openFilter === "share-safe"
              ? `Showing only open trades with fresh live option prices from the last ${SHARE_SAFE_REVIEW_MAX_AGE_MINUTES} minutes. ${hiddenOpenPositionCount} open trade(s) are hidden.`
              : "Showing all open trades. Live P&L is per trade and does not assume how many contracts anyone bought."}
            {entryDatePreset !== "all"
              ? ` Entry-date filter is showing ${positions.length} of ${basePositions.length} position(s) from ${entryDateFilterLabel(entryDatePreset, entryDateValue)}.`
              : ""}
            {selectedLaneLabel
              ? ` Source filter: ${selectedLaneLabel}.`
              : ` ${laneMixSummary(laneOptions)}`}
          </span>
          {openReviewSummary ? (
            <span className="text-text-1 whitespace-nowrap">{openReviewSummary}</span>
          ) : null}
        </div>
      ) : !error ? (
        <div className="bg-bg-2 border border-border rounded-lg px-3 py-2 text-xs text-text-2">
          Showing {positions.length} of {dateLaneClosedPositions.length} closed position(s)
          {closedRowsHasMore ? "+" : ""}
          {closedDataView !== "all" ? ` in ${closedDataViewLabel(closedDataView)}` : ""}
          {entryDatePreset !== "all" ? ` from ${entryDateFilterLabel(entryDatePreset, entryDateValue)}` : ""}
          {selectedLaneLabel ? ` from ${selectedLaneLabel}` : ""}.
          {!closedRowsLoaded ? " Closed rows are loading on demand." : ""}
          {closedRowsHasMore
            ? closedRowsLoading
              ? " Loading the next closed-history batch."
              : " More closed history is available; scroll to the bottom or use Load More for the next batch."
            : ""}
          {closedDataView === "truth_grade"
            ? ` ${closedEvidenceHiddenCount} non-truth-grade row(s) are hidden from this strict production-proof view.`
            : ""}
          {closedDataView === "current_policy"
            ? ` Raw realized rows: ${realizedPnlClosedPositions.length}; learned-away rows: ${learnedAwayClosedPositions.length}. Cohort state: ${currentPolicyCohortState}; showcase ${fmtCohortAvg(currentPolicyCohortHealth.showcaseMonth)}; recent ${fmtCohortAvg(currentPolicyCohortHealth.recentMonth)}, median ${fmtPct(currentPolicyCohortHealth.recentMonth?.medianPnlPct)}.`
            : ""}
          {closedDataView === "learned_away"
            ? " These rows stay visible as historical learning data, but current promoted entry guardrails would block them."
            : ""}
          {closedDataView === "realized_pnl"
            ? ` ${closedEvidenceHiddenCount} row(s) without trusted realized P&L are hidden.`
            : ""}
        </div>
      ) : null}

      {view === "closed" && closedRowsLoading && positions.length === 0 && !error ? (
        <TableSkeleton rows={6} />
      ) : positions.length === 0 && !loading && !error ? (
        <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
          <div>
            {view === "open"
              ? (openFilter === "share-safe" && dedupedOpenPositions.length > 0
                ? "No fresh-priced open trades match that entry date yet. Refresh prices or switch to All Trades."
                : hiddenByFilterCount > 0
                  ? "No open trades match those filters."
                  : "No open trades yet.")
              : !closedRowsLoaded
                ? "Closed trades have not been loaded yet."
                : hiddenByFilterCount > 0
                  ? "No closed trades match those filters."
                  : "No closed trades yet."}
          </div>
          {shouldOfferClosedPagination ? (
            <div className="mt-3 flex justify-center">
              <Button
                size="sm"
                variant="ghost"
                loading={closedRowsLoading}
                onClick={() => onLoadClosedRows({ notify: true })}
              >
                Load More
              </Button>
            </div>
          ) : null}
        </div>
      ) : (
        <>
          <FinTable
            data={rows}
            badgeCol="Trade"
            pnlCols={view === "open" ? [] : ["Realized P&L %"]}
            monoCols={view === "open" ? ["Taken", "Entry"] : ["Taken", "Entry", "Exit Px"]}
            label="Tracked options positions"
            density="compact"
            maxHeight={tableMaxHeight}
            mobileTitleCol="Ticker"
            mobileSubtitleCol={view === "open" ? "Live P&L" : "Realized P&L %"}
            mobilePriorityCols={
              view === "open"
                ? ["Signal", "Status", "Trade", "Taken", "Entry", "Live Px", "Quote", "Expiry"]
                : ["Status", "Signal", "Trade", "Taken", "Entry", "Exit Px"]
            }
          />
          {shouldOfferClosedPagination ? (
            <div className="flex flex-col items-center gap-2 pt-2">
              <div ref={loadMoreSentinelRef} className="h-2 w-full" aria-hidden="true" />
              <Button
                size="sm"
                variant="ghost"
                loading={closedRowsLoading}
                onClick={() => onLoadClosedRows({ notify: true })}
              >
                Load More
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
});
