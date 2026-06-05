"use client";

import MetricCard from "@/components/ui/MetricCard";
import {
  fmtCompactLabel,
  fmtDate,
  fmtUpperLabel,
} from "@/components/predictions/tradingDeskFormat";
import { displayLaneLabel } from "@/components/predictions/trackedPositionUtils";
import type {
  PaperGateBridgeRow,
  PaperGateOperatorWorkflow,
  PaperGateValidationRow,
} from "@/lib/types";

type PaperGateOperatorPanelProps = {
  workflow: PaperGateOperatorWorkflow | null | undefined;
};

function countMapLabel(counts: Record<string, number> | undefined): string {
  const entries = Object.entries(counts || {}).filter(([, value]) => Number(value || 0) > 0);
  if (!entries.length) return "none";
  return entries
    .map(([key, value]) => `${fmtCompactLabel(key)} ${value}`)
    .join(" / ");
}

function artifactStatus(workflow: PaperGateOperatorWorkflow): string {
  const refs = Object.values(workflow.artifacts || {});
  if (!refs.length) return "unknown";
  const missing = refs.filter((ref) => !ref?.available);
  return missing.length ? `${missing.length} missing` : "ready";
}

function bridgeRowLabel(row: PaperGateBridgeRow): string {
  return [
    row.symbol,
    row.playbook_id ? displayLaneLabel(row.playbook_id) : null,
    row.bridge_status ? fmtCompactLabel(row.bridge_status) : null,
  ].filter(Boolean).join(" / ");
}

function candidateLabel(row: PaperGateValidationRow): string {
  return [
    row.ticker,
    row.playbook_id ? displayLaneLabel(row.playbook_id) : null,
    row.contract_symbol || row.expiry,
  ].filter(Boolean).join(" / ");
}

function BridgeRows({ rows, emptyLabel }: { rows: PaperGateBridgeRow[]; emptyLabel: string }) {
  if (!rows.length) {
    return <div className="text-xs text-text-3">{emptyLabel}</div>;
  }
  return (
    <div className="space-y-2">
      {rows.slice(0, 5).map((row, index) => (
        <div key={`${row.symbol}-${row.playbook_id}-${index}`} className="rounded-md border border-border bg-bg-3 px-3 py-2">
          <div className="text-xs font-semibold text-text-1">{bridgeRowLabel(row)}</div>
          <div className="mt-1 text-xs text-text-3">
            Matched Tier A lanes {row.matched_tier_a_lanes?.length ? row.matched_tier_a_lanes.join(", ") : "none"}
            {" "}&middot; Blockers {row.blockers?.length ? row.blockers.join(", ") : "none"}
          </div>
        </div>
      ))}
    </div>
  );
}

function ValidationRows({ rows }: { rows: PaperGateValidationRow[] }) {
  if (!rows.length) {
    return <div className="text-xs text-text-3">No pending validation rows are available in the latest artifact.</div>;
  }
  return (
    <div className="space-y-2">
      {rows.slice(0, 6).map((row, index) => (
        <div key={`${row.candidate_key || row.contract_symbol || index}`} className="rounded-md border border-border bg-bg-3 px-3 py-2">
          <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-xs font-semibold text-text-1">{candidateLabel(row) || "Source missing"}</div>
            <div className="font-mono text-[11px] uppercase text-text-3">
              {fmtUpperLabel(row.validation_outcome)}
            </div>
          </div>
          <div className="mt-1 text-xs text-text-3">
            {row.fill_discipline_explanation || "No fill-discipline explanation recorded."}
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-wide text-text-3">
            Fill {fmtCompactLabel(row.fill_status || row.fill_attempt_status)}
            {" "}&middot; Link {fmtCompactLabel(row.position_link_status)}
            {" "}&middot; Realized P&L {fmtCompactLabel(row.realized_pnl_status)}
          </div>
        </div>
      ))}
    </div>
  );
}

export function PaperGateOperatorPanel({ workflow }: PaperGateOperatorPanelProps) {
  if (!workflow) return null;

  const summary = workflow.summary || {};
  const artifacts = Object.values(workflow.artifacts || {});
  const missingArtifacts = artifacts.filter((ref) => !ref?.available);
  const eligibleRows = workflow.paper_shortlist?.eligible_rows || [];
  const bridgePreview = workflow.paper_shortlist?.non_eligible_preview || [];
  const pendingRows = workflow.pending_validation?.rows || [];
  const noFillRows = workflow.no_fill_and_auto_track?.rows || [];
  const circuitRoutes = workflow.current_policy_circuit_breaker?.lane_routes || [];

  return (
    <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-text-0">Paper Gate Operator Readback</div>
          <p className="text-xs text-text-3 mt-1">
            {workflow.operator_message || "Paper gate state is unavailable."}
          </p>
          <div className="mt-2 text-[11px] uppercase tracking-wide text-text-3">
            Generated {fmtDate(workflow.generated_at_utc)}
            {" "}&middot; Artifacts {artifactStatus(workflow)}
          </div>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <MetricCard label="Release" value={fmtUpperLabel(summary.release_gate_status)} />
          <MetricCard label="Eligible" value={String(summary.eligible_count ?? 0)} />
          <MetricCard label="Pending" value={String(summary.pending_candidate_count ?? 0)} />
          <MetricCard label="No-Fill" value={String(summary.no_fill_or_auto_track_skipped_count ?? 0)} />
          <MetricCard label="Breaker" value={summary.breaker_active ? "ACTIVE" : "CLEAR"} />
        </div>
      </div>

      <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 text-xs text-amber-200">
        {workflow.operator_policy?.paper_review_language ||
          "Rows shown here are paper-review-only until fresh executable entry, verified linkage, and exact realized OPRA/NBBO exit P&L all pass."}
      </div>

      {missingArtifacts.length ? (
        <div className="bg-red-dim border border-red/30 rounded-lg px-3 py-2 space-y-1">
          {missingArtifacts.map((ref) => (
            <div key={String(ref.path)} className="text-xs text-red">
              Missing {ref.path || "artifact"} {ref.error ? `(${ref.error})` : ""}
            </div>
          ))}
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-text-3">Bridge Status</div>
          <BridgeRows
            rows={eligibleRows.length ? eligibleRows : bridgePreview}
            emptyLabel="No bridge rows are available in the latest paper shortlist artifact."
          />
        </div>
        <div className="space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-text-3">Pending Outcomes</div>
          <div className="rounded-md border border-border bg-bg-3 px-3 py-2 text-xs text-text-2">
            {countMapLabel(summary.pending_outcome_counts)}
          </div>
          <ValidationRows rows={pendingRows} />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div className="space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-text-3">No-Fill / Skipped Auto-Track</div>
          <div className="text-xs text-text-3">
            {workflow.no_fill_and_auto_track?.operator_rule}
          </div>
          <ValidationRows rows={noFillRows} />
        </div>
        <div className="space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-text-3">Circuit Breaker Routes</div>
          {circuitRoutes.length ? (
            <div className="space-y-2">
              {circuitRoutes.map((route, index) => (
                <div key={`${String(route.lane_id)}-${index}`} className="rounded-md border border-border bg-bg-3 px-3 py-2">
                  <div className="text-xs font-semibold text-text-1">
                    {displayLaneLabel(String(route.lane_id || "unknown"))}
                  </div>
                  <div className="mt-1 text-xs text-text-3">
                    {fmtCompactLabel(String(route.route_status || "unknown"))}
                    {" "}&middot; {fmtCompactLabel(String(route.route_reason || "unknown"))}
                  </div>
                  <div className="mt-1 text-[11px] uppercase tracking-wide text-text-3">
                    Live policy change {route.live_policy_change ? "TRUE" : "FALSE"}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-text-3">No circuit breaker routes are available.</div>
          )}
        </div>
      </div>
    </div>
  );
}
