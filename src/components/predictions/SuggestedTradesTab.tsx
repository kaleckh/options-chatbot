"use client";

import { memo, useState } from "react";
import { CheckCircle, RefreshCw } from "lucide-react";
import Button from "@/components/ui/Button";
import FinTable from "@/components/ui/FinTable";
import { TableSkeleton } from "@/components/ui/Skeleton";
import { CompactStat } from "@/components/predictions/TradingDeskCompactStat";
import {
  contractQualityLabel,
  fmtCompactLabel,
  fmtDate,
  fmtMoney,
  fmtPct,
} from "@/components/predictions/tradingDeskFormat";
import {
  formatSignalLabel,
  getResolvedListedExpiry,
  isShareSafeLivePosition,
  renderClosedStatusCell,
  renderExpiryCell,
  renderOpenPnlCell,
  renderOpenPriceCell,
  renderPositionStatusCell,
  renderQuoteCell,
  renderRealizedPnlCell,
  renderReviewedCell,
  SHARE_SAFE_REVIEW_MAX_AGE_MINUTES,
} from "@/components/predictions/tradingDeskCells";
import type { SuggestedTrade } from "@/lib/types";
import {
  calcWinRatePct,
  getCloseNowPnlPct,
  getOpenReviewActionState,
  getRealizedExitPrice,
  getRealizedPnlPct,
} from "@/lib/trading-desk/positionEvidence";

type SuggestedTradesTabProps = {
  openTrades: SuggestedTrade[];
  closedTrades: SuggestedTrade[];
  loading: boolean;
  error: string | null;
  view: "open" | "closed";
  reviewingIds: number[];
  closedRowsLoaded: boolean;
  closedRowsHasMore: boolean;
  closedRowsLoading: boolean;
  onViewChange: (value: "open" | "closed") => void;
  onRefresh: () => void;
  onLoadClosedRows: () => void;
  onReviewTrade: (positionId: number) => void;
  onOpenClose: (trade: SuggestedTrade) => void;
};

export const SuggestedTradesTab = memo(function SuggestedTradesTab({
  openTrades,
  closedTrades,
  loading,
  error,
  view,
  reviewingIds,
  closedRowsLoaded,
  closedRowsHasMore,
  closedRowsLoading,
  onViewChange,
  onRefresh,
  onLoadClosedRows,
  onReviewTrade,
  onOpenClose,
}: SuggestedTradesTabProps) {
  const dedupedOpenTrades = openTrades;
  const [openFilter, setOpenFilter] = useState<"share-safe" | "all">("all");
  const shareSafeOpenTrades = dedupedOpenTrades.filter((trade) => isShareSafeLivePosition(trade));
  const hiddenOpenTradeCount = Math.max(dedupedOpenTrades.length - shareSafeOpenTrades.length, 0);
  const trades = view === "open"
    ? (openFilter === "share-safe" ? shareSafeOpenTrades : dedupedOpenTrades)
    : closedTrades;
  const openPnlValues = dedupedOpenTrades
    .map((trade) => getCloseNowPnlPct(trade))
    .filter((value): value is number => value != null);
  const openActionStates = dedupedOpenTrades.map((trade) => getOpenReviewActionState(trade));
  const reviewRequiredSuggestedTrades = openActionStates.filter((state) =>
    state.id === "review_missing" ||
    state.id === "review_unpriced" ||
    state.id === "non_executable_sell"
  ).length;
  const closeReadySuggestedTrades = openActionStates.filter((state) => state.id === "executable_sell").length;
  const closedPnlValues = closedTrades
    .map((trade) => getRealizedPnlPct(trade))
    .filter((value): value is number => value != null);
  const avgOpenPnl = openPnlValues.length > 0
    ? openPnlValues.reduce((sum, value) => sum + value, 0) / openPnlValues.length
    : null;
  const avgClosedPnl = closedPnlValues.length > 0
    ? closedPnlValues.reduce((sum, value) => sum + value, 0) / closedPnlValues.length
    : null;
  const closedWinRate = calcWinRatePct(closedTrades, getRealizedPnlPct);

  const rows = trades.map((trade) => {
    const displayPnl = view === "open"
      ? getCloseNowPnlPct(trade)
      : getRealizedPnlPct(trade);

    if (view === "open") {
      const actionState = getOpenReviewActionState(trade);
      const closeIsExecutable = actionState.id === "executable_sell";
      return {
        Ticker: trade.ticker,
        Trade: trade.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
        Logged: fmtDate(trade.filled_at),
        Entry: fmtMoney(trade.entry_option_price),
        "Live Px": renderOpenPriceCell(trade),
        "Live P&L": renderOpenPnlCell(trade),
        Status: renderPositionStatusCell(trade),
        Signal: formatSignalLabel(trade.last_recommendation),
        "Contract Q": contractQualityLabel(trade.source_pick_snapshot),
        Source: fmtCompactLabel(trade.source_pick_snapshot?.selection_source || trade.source_pick_snapshot?.promotion_class),
        "Entry Basis": fmtCompactLabel(trade.entry_execution_basis || trade.source_pick_snapshot?.entry_execution_basis),
        Quote: renderQuoteCell(trade),
        Expiry: renderExpiryCell(trade),
        Reviewed: renderReviewedCell(trade),
        Reason: trade.last_recommendation_reason || trade.latest_review?.reason || "\u2014",
        Action: (
          <div className="flex min-w-[126px] items-center gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              icon={<RefreshCw size={12} />}
              loading={reviewingIds.includes(trade.id)}
              onClick={() => onReviewTrade(trade.id)}
            >
              Review
            </Button>
            <Button
              size="sm"
              variant={closeIsExecutable ? "danger" : "ghost"}
              icon={<CheckCircle size={12} />}
              aria-label={
                closeIsExecutable
                  ? `Close ${trade.ticker} paper idea from executable review`
                  : `Manually close ${trade.ticker} paper idea after entering an exit price`
              }
              title={closeIsExecutable ? "Close from executable review" : "Manual hypothetical close"}
              onClick={() => onOpenClose(trade)}
            >
              {closeIsExecutable ? "Close" : "Manual"}
            </Button>
          </div>
        ),
      };
    }

    return {
      Ticker: trade.ticker,
      Trade: trade.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
      Entry: fmtMoney(trade.entry_option_price),
      "Exit Px": fmtMoney(getRealizedExitPrice(trade)),
      "Realized P&L %": renderRealizedPnlCell(displayPnl),
      Status: renderClosedStatusCell(trade),
      Signal: formatSignalLabel(trade.last_recommendation),
      "Contract Q": contractQualityLabel(trade.source_pick_snapshot),
      Expiry: fmtDate(getResolvedListedExpiry(trade)),
    };
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-col lg:flex-row lg:items-start lg:justify-between gap-3">
        <div className="max-w-3xl">
          <div className="text-lg font-semibold text-text-0">Paper Ideas</div>
          <p className="mt-1 text-sm text-text-2">
            Manual paper-tracked ideas from the scanner. Open trades reprice automatically here, and stay separate from positions you actually took.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
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
          {view === "open" ? (
            <>
              <Button
                size="sm"
                variant={openFilter === "share-safe" ? "secondary" : "ghost"}
                onClick={() => setOpenFilter("share-safe")}
              >
                Fresh Prices
              </Button>
              <Button
                size="sm"
                variant={openFilter === "all" ? "secondary" : "ghost"}
                onClick={() => setOpenFilter("all")}
              >
                All Ideas
              </Button>
            </>
          ) : null}
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
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-7 gap-2">
          <CompactStat label="Open Ideas" value={String(openTrades.length)} help="Open paper ideas currently loaded" />
          <CompactStat label="Needs Review" value={String(reviewRequiredSuggestedTrades)} help="Open ideas missing fresh executable review evidence" />
          <CompactStat label="Close-ready" value={String(closeReadySuggestedTrades)} help="Open ideas with executable SELL review evidence" />
          <CompactStat label="Avg Live P&L" value={fmtPct(avgOpenPnl)} />
          <CompactStat label="Closed Ideas" value={closedRowsLoaded ? `${closedTrades.length}${closedRowsHasMore ? "+" : ""}` : "\u2014"} />
          <CompactStat label="Win Rate" value={fmtPct(closedWinRate)} />
          <CompactStat label="Avg Closed P&L" value={fmtPct(avgClosedPnl)} />
        </div>
      )}

      {!error && view === "open" && reviewRequiredSuggestedTrades > 0 ? (
        <div className="bg-amber-500/10 border border-amber-500/30 rounded-lg px-3 py-2 text-xs text-amber-100">
          {reviewRequiredSuggestedTrades} open paper idea(s) need fresh executable review evidence before P&L or close state is reliable.
        </div>
      ) : null}

      {!error && view === "open" ? (
        <div className="bg-bg-2 border border-border rounded-lg px-3 py-2 text-xs text-text-2">
          {openFilter === "share-safe"
            ? `Showing only paper ideas with fresh live option prices from the last ${SHARE_SAFE_REVIEW_MAX_AGE_MINUTES} minutes. ${hiddenOpenTradeCount} open idea(s) are hidden.`
            : "Showing all open paper ideas. Live P&L is per trade and does not assume how many contracts anyone bought."}
        </div>
      ) : null}

      {view === "closed" && closedRowsLoading && trades.length === 0 && !error ? (
        <TableSkeleton rows={6} />
      ) : trades.length === 0 && !loading && !error ? (
        <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
          <div>
            {view === "open"
              ? (openFilter === "share-safe" && dedupedOpenTrades.length > 0
                ? "No fresh-priced paper ideas yet. Refresh prices or switch to All Ideas."
                : "No paper ideas yet.")
              : closedRowsLoaded
                ? "No closed paper ideas yet."
                : "Closed paper ideas have not been loaded yet."}
          </div>
          {view === "closed" && closedRowsHasMore ? (
            <div className="mt-3 flex justify-center">
              <Button
                size="sm"
                variant="ghost"
                loading={closedRowsLoading}
                onClick={onLoadClosedRows}
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
            monoCols={view === "open" ? ["Contract Q", "Entry Basis", "Entry"] : ["Contract Q", "Entry", "Exit Px", "Expiry"]}
            label="Paper ideas"
            maxHeight={view === "open" ? "min(60vh, 760px)" : "min(64vh, 820px)"}
            mobileTitleCol="Ticker"
            mobileSubtitleCol={view === "open" ? "Status" : "Realized P&L %"}
            mobilePriorityCols={
              view === "open"
                ? ["Live P&L", "Signal", "Trade", "Logged", "Entry", "Live Px", "Quote", "Expiry", "Reviewed"]
                : ["Status", "Signal", "Trade", "Entry", "Exit Px", "Contract Q", "Expiry"]
            }
            mobileHiddenCols={view === "open" ? ["Contract Q", "Source", "Entry Basis", "Reason"] : []}
          />
          {view === "closed" && closedRowsHasMore ? (
            <div className="flex justify-center pt-2">
              <Button
                size="sm"
                variant="ghost"
                loading={closedRowsLoading}
                onClick={onLoadClosedRows}
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
