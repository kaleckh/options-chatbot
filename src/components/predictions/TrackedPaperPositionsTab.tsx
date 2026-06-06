"use client";

import { memo, useEffect, useMemo, useState } from "react";
import { LineChart, RefreshCw } from "lucide-react";
import Button from "@/components/ui/Button";
import FinTable from "@/components/ui/FinTable";
import { CompactStat } from "@/components/predictions/TradingDeskCompactStat";
import { fmtDateTime, fmtMoney, fmtPct, metricToneClass } from "@/components/predictions/tradingDeskFormat";
import {
  fmtContractCoreLabel,
  fmtTakenDate,
  getPositionLaneDescriptor,
  renderTickerCell,
} from "@/components/predictions/trackedPositionUtils";
import {
  getCloseNowPnlPct,
  getCloseNowPrice,
  getEntryExecutionPrice,
  getMarkPnlPct,
  getMarkPrice,
  getRealizedExitPrice,
  getRealizedPnlPct,
} from "@/lib/trading-desk/positionEvidence";
import type { AlpacaPaperOrderMetadata, TrackedPosition } from "@/lib/types";

type TrackedPaperPositionsTabProps = {
  openPositions: TrackedPosition[];
  closedPositions: TrackedPosition[];
  loading: boolean;
  error: string | null;
  closedRowsLoaded: boolean;
  closedRowsHasMore: boolean;
  onRefresh: () => void;
};

export type TrackedPositionChartPoint = {
  id: string;
  label: string;
  timestamp: string;
  price: number | null;
  pnlPct: number | null;
};

function finiteNumber(value: unknown): number | null {
  if (value == null || typeof value === "boolean") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function getAlpacaPaperOrder(position: TrackedPosition): AlpacaPaperOrderMetadata | null {
  const order = position.source_pick_snapshot?.alpaca_paper_order;
  return order && typeof order === "object" ? order : null;
}

export function isAlpacaPaperTrackedPosition(position: TrackedPosition): boolean {
  const order = getAlpacaPaperOrder(position);
  return Boolean(order?.client_order_id || order?.order_id || position.source_pick_snapshot?.broker_execution_mode === "alpaca_paper");
}

function addPointOnce(points: TrackedPositionChartPoint[], point: TrackedPositionChartPoint) {
  if (!point.timestamp) return;
  const key = `${point.label}:${point.timestamp}`;
  if (points.some((item) => `${item.label}:${item.timestamp}` === key)) return;
  points.push(point);
}

export function buildTrackedPositionChartPoints(position: TrackedPosition): TrackedPositionChartPoint[] {
  const points: TrackedPositionChartPoint[] = [];
  const entryPrice = getEntryExecutionPrice(position);
  addPointOnce(points, {
    id: "entry",
    label: "Entry",
    timestamp: position.filled_at,
    price: entryPrice,
    pnlPct: entryPrice != null ? 0 : null,
  });

  const latestReviewAt = position.latest_review?.reviewed_at ?? position.last_reviewed_at ?? null;
  const closeNowPrice = getCloseNowPrice(position);
  const closeNowPnl = getCloseNowPnlPct(position);
  if (latestReviewAt && closeNowPrice != null) {
    addPointOnce(points, {
      id: "latest-exit",
      label: "Executable Exit",
      timestamp: latestReviewAt,
      price: closeNowPrice,
      pnlPct: closeNowPnl,
    });
  }

  const markPrice = getMarkPrice(position);
  const markPnl = getMarkPnlPct(position);
  if (latestReviewAt && markPrice != null && (closeNowPrice == null || markPrice !== closeNowPrice)) {
    addPointOnce(points, {
      id: "latest-mark",
      label: "Paper Mark",
      timestamp: latestReviewAt,
      price: markPrice,
      pnlPct: markPnl,
    });
  }

  const realizedExit = getRealizedExitPrice(position);
  const realizedPnl = getRealizedPnlPct(position);
  if (position.closed_at && realizedExit != null) {
    addPointOnce(points, {
      id: "closed",
      label: "Closed",
      timestamp: position.closed_at,
      price: realizedExit,
      pnlPct: realizedPnl,
    });
  }

  return points
    .filter((point) => point.pnlPct != null && !Number.isNaN(point.pnlPct))
    .sort((a, b) => {
      const aTime = new Date(a.timestamp).getTime();
      const bTime = new Date(b.timestamp).getTime();
      return (Number.isNaN(aTime) ? 0 : aTime) - (Number.isNaN(bTime) ? 0 : bTime);
    });
}

function PaperOrderStatus({ order }: { order: AlpacaPaperOrderMetadata | null }) {
  const status = String(order?.status || "submitted").replaceAll("_", " ");
  const filledPrice = finiteNumber(order?.filled_avg_price);
  return (
    <div className="space-y-1 leading-tight min-w-[132px]">
      <div className="text-sm font-semibold capitalize text-text-0">{status}</div>
      <div className="text-xs text-text-3">
        {order?.order_id ? `Order ${order.order_id}` : order?.client_order_id ?? "Client order pending"}
      </div>
      <div className="text-xs text-text-2">
        {filledPrice != null ? `Fill ${fmtMoney(filledPrice)}` : `Limit ${fmtMoney(finiteNumber(order?.limit_price))}`}
      </div>
    </div>
  );
}

function PaperPositionChart({ position }: { position: TrackedPosition | null }) {
  const points = useMemo(
    () => (position ? buildTrackedPositionChartPoints(position) : []),
    [position]
  );
  if (!position) {
    return (
      <div className="rounded-lg border border-border bg-bg-2 p-6 text-center text-sm text-text-3">
        Select a paper-tracked position to see its P&L path.
      </div>
    );
  }
  if (points.length < 2) {
    return (
      <div className="rounded-lg border border-border bg-bg-2 p-6 text-center text-sm text-text-3">
        {fmtContractCoreLabel(position)} needs another review or close event before a line can be drawn.
      </div>
    );
  }

  const width = 720;
  const height = 260;
  const padX = 42;
  const padY = 28;
  const values = points.map((point) => Number(point.pnlPct));
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(0, ...values);
  const span = Math.max(maxValue - minValue, 1);
  const plotWidth = width - padX * 2;
  const plotHeight = height - padY * 2;
  const xFor = (index: number) => padX + (points.length === 1 ? 0 : (plotWidth * index) / (points.length - 1));
  const yFor = (value: number) => padY + plotHeight - ((value - minValue) / span) * plotHeight;
  const path = points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${xFor(index).toFixed(2)} ${yFor(Number(point.pnlPct)).toFixed(2)}`)
    .join(" ");
  const zeroY = yFor(0);

  return (
    <section className="rounded-lg border border-border bg-bg-2 p-4" aria-label="Tracked paper position line chart">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-text-0">{fmtContractCoreLabel(position)}</div>
          <div className="mt-1 text-xs text-text-3">{getPositionLaneDescriptor(position).label}</div>
        </div>
        <div className={`font-mono text-sm font-semibold ${metricToneClass(points[points.length - 1]?.pnlPct ?? null)}`}>
          {fmtPct(points[points.length - 1]?.pnlPct ?? null)}
        </div>
      </div>
      <div className="overflow-x-auto">
        <svg viewBox={`0 0 ${width} ${height}`} className="h-[260px] min-w-[560px] w-full" role="img" aria-label="Paper tracked P&L line">
          <line x1={padX} x2={width - padX} y1={zeroY} y2={zeroY} stroke="var(--border)" strokeDasharray="5 5" />
          <path d={path} fill="none" stroke="var(--accent)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          {points.map((point, index) => {
            const x = xFor(index);
            const y = yFor(Number(point.pnlPct));
            return (
              <g key={point.id}>
                <circle cx={x} cy={y} r="5" fill="var(--bg-1)" stroke="var(--accent)" strokeWidth="2" />
                <text x={x} y={height - 8} textAnchor="middle" fill="var(--text-3)" className="text-[10px]">
                  {point.label}
                </text>
                <text x={x} y={Math.max(14, y - 10)} textAnchor="middle" fill="var(--text-0)" className="text-[11px] font-mono">
                  {fmtPct(point.pnlPct)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
        {points.map((point) => (
          <div key={`${point.id}-detail`} className="rounded-md border border-border bg-bg-1 px-3 py-2">
            <div className="text-xs font-semibold text-text-0">{point.label}</div>
            <div className="mt-1 font-mono text-sm text-text-1">{fmtPct(point.pnlPct)}</div>
            <div className="mt-1 text-xs text-text-3">
              {fmtMoney(point.price)} / {fmtDateTime(point.timestamp)}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export const TrackedPaperPositionsTab = memo(function TrackedPaperPositionsTab({
  openPositions,
  closedPositions,
  loading,
  error,
  closedRowsLoaded,
  closedRowsHasMore,
  onRefresh,
}: TrackedPaperPositionsTabProps) {
  const paperPositions = useMemo(
    () => [...openPositions, ...closedPositions].filter(isAlpacaPaperTrackedPosition),
    [closedPositions, openPositions]
  );
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    if (!paperPositions.length) {
      setSelectedId(null);
      return;
    }
    if (selectedId == null || !paperPositions.some((position) => position.id === selectedId)) {
      setSelectedId(paperPositions[0].id);
    }
  }, [paperPositions, selectedId]);

  const selectedPosition = paperPositions.find((position) => position.id === selectedId) ?? paperPositions[0] ?? null;
  const openPaperCount = paperPositions.filter((position) => position.status === "open").length;
  const closedPaperCount = paperPositions.filter((position) => position.status === "closed").length;
  const filledCount = paperPositions.filter((position) => {
    const status = String(getAlpacaPaperOrder(position)?.status || "").toLowerCase();
    return status === "filled" || status === "partially_filled";
  }).length;
  const selectedChartPoints = useMemo(
    () => (selectedPosition ? buildTrackedPositionChartPoints(selectedPosition) : []),
    [selectedPosition]
  );
  const latestPoint = selectedChartPoints.length > 0 ? selectedChartPoints[selectedChartPoints.length - 1] : null;
  const latestPnl = latestPoint?.pnlPct ?? null;

  const rows = paperPositions.map((position) => {
    const order = getAlpacaPaperOrder(position);
    return {
      __rowKey: position.id,
      Ticker: renderTickerCell(position),
      Contract: fmtContractCoreLabel(position),
      Source: getPositionLaneDescriptor(position).label,
      "Paper Order": <PaperOrderStatus order={order} />,
      Entry: fmtMoney(getEntryExecutionPrice(position)),
      "Latest P&L": fmtPct(getCloseNowPnlPct(position) ?? getRealizedPnlPct(position)),
      Taken: fmtTakenDate(position),
      Action: (
        <Button size="sm" variant={selectedPosition?.id === position.id ? "secondary" : "ghost"} onClick={() => setSelectedId(position.id)}>
          Chart
        </Button>
      ),
    };
  });

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <div className="flex items-center gap-2 text-lg font-semibold text-text-0">
            <LineChart size={18} aria-hidden="true" />
            Paper Track
          </div>
          <p className="mt-1 text-sm text-text-2">
            Alpaca paper orders linked to tracked option positions, with executable P&L separated from mark values.
          </p>
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

      {!error ? (
        <div className="grid grid-cols-2 gap-2 xl:grid-cols-5">
          <CompactStat label="Paper Rows" value={`${paperPositions.length}${closedRowsHasMore ? "+" : ""}`} help="Tracked positions that carry Alpaca paper order metadata" />
          <CompactStat label="Open" value={String(openPaperCount)} help="Open Alpaca paper-tracked rows" />
          <CompactStat label="Closed" value={String(closedPaperCount)} help="Closed Alpaca paper-tracked rows loaded in this browser session" />
          <CompactStat label="Filled" value={String(filledCount)} help="Rows whose latest Alpaca order status reports a paper fill" />
          <CompactStat label="Selected P&L" value={fmtPct(latestPnl)} help="Last available executable or realized P&L point for the selected row" />
        </div>
      ) : null}

      {!error ? <PaperPositionChart position={selectedPosition} /> : null}

      {!error && !closedRowsLoaded ? (
        <div className="rounded-lg border border-border bg-bg-2 px-3 py-2 text-xs text-text-2">
          Closed paper rows load on demand; open rows are already included.
        </div>
      ) : null}

      {!error && closedRowsHasMore ? (
        <div className="rounded-lg border border-border bg-bg-2 px-3 py-2 text-xs text-text-2">
          More closed history is available; this view updates as the closed archive loads.
        </div>
      ) : null}

      {!error && paperPositions.length === 0 ? (
        <div className="rounded-lg border border-border bg-bg-2 p-6 text-center text-sm text-text-3">
          No Alpaca paper-tracked positions are loaded yet.
        </div>
      ) : !error ? (
        <FinTable
          data={rows}
          label="Alpaca paper tracked positions"
          density="compact"
          monoCols={["Contract", "Entry", "Latest P&L", "Taken"]}
          pnlCols={["Latest P&L"]}
          maxHeight="520px"
          mobileTitleCol="Ticker"
          mobileSubtitleCol="Latest P&L"
          mobilePriorityCols={["Paper Order", "Source", "Contract", "Entry", "Taken"]}
        />
      ) : null}
    </div>
  );
});
