"use client";

import { useEffect } from "react";
import Button from "@/components/ui/Button";
import {
  fmtDate,
  fmtDateTime,
  fmtMoney,
  fmtPct,
  fmtPricingSource,
  metricToneClass,
} from "@/components/predictions/tradingDeskFormat";
import {
  formatSignalLabel,
  getResolvedListedExpiry,
  getReviewedAt,
  getShareSafeReason,
} from "@/components/predictions/tradingDeskCells";
import { fmtTakenDate } from "@/components/predictions/trackedPositionUtils";
import { parseNonnegativePriceInput } from "@/components/predictions/tradingDeskCloseForm";
import type { SuggestedTrade, TrackedPosition } from "@/lib/types";
import {
  calcNetOptionPnlPct,
  getCloseNowPnlPct,
  getCloseNowPrice,
  getEntryExecutionPrice,
  getMarkPrice,
} from "@/lib/trading-desk/positionEvidence";

export type CloseTradeModalProps = {
  item: TrackedPosition | SuggestedTrade | null;
  mode: "tracked" | "suggested";
  exitPrice: string;
  notes: string;
  closingId: number | null;
  onExitPriceChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
};

export function CloseTradeModal({
  item,
  mode,
  exitPrice,
  notes,
  closingId,
  onExitPriceChange,
  onNotesChange,
  onCancel,
  onConfirm,
}: CloseTradeModalProps) {
  useEffect(() => {
    if (!item) return undefined;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && closingId !== item.id) {
        onCancel();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [item, closingId, onCancel]);

  if (!item) return null;

  const title = mode === "tracked" ? "Close Tracked Trade" : "Close Suggested Trade";
  const confirmLabel = mode === "tracked" ? "Confirm Close" : "Confirm Hypothetical Close";
  const exitLabel = mode === "tracked" ? "Actual exit price" : "Hypothetical exit price";
  const liveExitPrice = getCloseNowPrice(item);
  const markValue = getMarkPrice(item);
  const enteredExitPrice = parseNonnegativePriceInput(exitPrice);
  const exitPnl =
    enteredExitPrice != null
      ? calcNetOptionPnlPct({
          entryPrice: getEntryExecutionPrice(item),
          exitPrice: enteredExitPrice,
          contracts: item.contracts,
          feeTotalUsd: item.latest_review?.fee_total_usd ?? item.fee_total_usd ?? 0,
        })
      : getCloseNowPnlPct(item);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 px-4 py-6 flex items-center justify-center"
      onMouseDown={() => {
        if (closingId !== item.id) onCancel();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="close-trade-modal-title"
        className="w-full max-w-2xl rounded-xl border border-border bg-bg-1 shadow-2xl"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="px-5 py-4 border-b border-border">
          <div id="close-trade-modal-title" className="text-base font-semibold text-text-0">
            {title}
          </div>
          <div className="text-sm text-text-2 mt-1">
            {item.ticker} {item.direction.toUpperCase()} · Taken {fmtTakenDate(item)} · Exp {fmtDate(getResolvedListedExpiry(item))}
          </div>
        </div>

        <div className="px-5 py-4 space-y-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">Entry</div>
              <div className="font-mono text-sm text-text-0 mt-1">{fmtMoney(item.entry_option_price)}</div>
            </div>
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">Mark Value</div>
              <div className="font-mono text-sm text-text-0 mt-1">{fmtMoney(markValue)}</div>
            </div>
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">Est. Exit</div>
              <div className="font-mono text-sm text-text-0 mt-1">{fmtMoney(liveExitPrice)}</div>
            </div>
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-2">Exit P&L</div>
              <div className={`font-mono text-sm mt-1 ${metricToneClass(exitPnl)}`}>{fmtPct(exitPnl)}</div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs text-text-2">
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div>
                Signal: <strong className="text-text-0">{formatSignalLabel(item.last_recommendation)}</strong>
              </div>
              <div className="mt-1">
                Pricing: <strong className="text-text-0">{fmtPricingSource(item.latest_review?.pricing_source)}</strong>
              </div>
            </div>
            <div className="bg-bg-2 border border-border rounded-lg px-3 py-2">
              <div>
                Provenance: <strong className="text-text-0">{getShareSafeReason(item)}</strong>
              </div>
              <div className="mt-1">
                Renewed: <strong className="text-text-0">{fmtDateTime(getReviewedAt(item))}</strong>
              </div>
            </div>
          </div>

          {item.latest_review?.warnings?.length ? (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              {item.latest_review.warnings[0]}
            </div>
          ) : null}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">{exitLabel}</span>
              <input
                type="number"
                min="0"
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
                value={notes}
                onChange={(e) => onNotesChange(e.target.value)}
                placeholder="Optional close note"
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
              />
            </label>
          </div>
        </div>

        <div className="px-5 py-4 border-t border-border flex items-center justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onCancel} disabled={closingId === item.id}>
            Cancel
          </Button>
          <Button variant="danger" size="sm" loading={closingId === item.id} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
