"use client";

import MetricCard from "@/components/ui/MetricCard";
import { PaperGateOperatorPanel } from "@/components/predictions/PaperGateOperatorPanel";
import {
  fmtCompactLabel,
  fmtDate,
  fmtTruthSource,
  fmtUpperLabel,
} from "@/components/predictions/tradingDeskFormat";
import { displayLaneLabel } from "@/components/predictions/trackedPositionUtils";
import type {
  ExposureSnapshot,
  ForwardEvidenceReport,
  LiveTradePolicy,
  OptionsProfitStatus,
  PlaybookExitAudit,
  ScanPlaybook,
} from "@/lib/types";

type ScannerEvidencePanelProps = {
  useRecommendedPolicy: boolean;
  policy: LiveTradePolicy | null;
  policyError: string | null;
  exitAudit: PlaybookExitAudit | null;
  decisionCounts: Record<string, number> | null;
  guardrailCounts: Record<string, number> | null;
  candidateCount: number;
  forwardEvidence: ForwardEvidenceReport | null;
  optionsProfitStatus: OptionsProfitStatus | null;
  truthHealthError: string | null;
  playbook: string;
  playbooks: ScanPlaybook[];
  exposureSnapshot: ExposureSnapshot | null;
};

export function ScannerEvidencePanel({
  useRecommendedPolicy,
  policy,
  policyError,
  exitAudit,
  decisionCounts,
  guardrailCounts,
  candidateCount,
  forwardEvidence,
  optionsProfitStatus,
  truthHealthError,
  playbook,
  playbooks,
  exposureSnapshot,
}: ScannerEvidencePanelProps) {
  const hardFilters = policy?.scan_policy.hard_filters;
  const preferred = policy?.scan_policy.preferred_filters;
  const promotionStatus = String(
    policy?.scan_policy.promotion_status || policy?.promotion_status || "watch"
  ).toLowerCase();
  const policyIsPromoted = promotionStatus === "promote";
  const truthSource = String(policy?.source?.truth_source || policy?.truth_source || "").toLowerCase();
  const truthSourceLabel = fmtTruthSource(truthSource);
  const quoteCoverage = policy?.source?.quote_coverage_pct ?? policy?.quote_coverage_pct ?? null;
  const sourceLabel = [
    policy?.source_run_at ? fmtDate(policy.source_run_at) : null,
    policy?.lookback_years != null ? `${policy.lookback_years}y` : null,
    policy?.pricing_lane ? String(policy.pricing_lane).toUpperCase() : null,
    policy?.playbook ? String(policy.playbook).replaceAll("_", " ") : null,
  ].filter(Boolean).join(" \u00b7 ");
  const approvedCount = decisionCounts?.approved || 0;
  const watchCount = decisionCounts?.watch || 0;
  const blockedCount = decisionCounts?.blocked || 0;
  const approvedReplayTrades = exitAudit?.approved?.trades ?? null;
  const clearCount = guardrailCounts?.clear || 0;
  const cautionCount = guardrailCounts?.caution || 0;
  const guardrailBlockedCount = guardrailCounts?.blocked || 0;
  const activePlaybook = playbooks.find((item) => item.id === playbook) || null;
  const activePlaybookLabel = activePlaybook
    ? displayLaneLabel(activePlaybook.id, activePlaybook.label)
    : null;
  const measurementGate = optionsProfitStatus?.measurement_gate;
  const gateState = String(measurementGate?.state || "unknown").toLowerCase();
  const importedDailyCheck = measurementGate?.checks?.imported_daily_artifact || null;
  const forwardGateCheck = measurementGate?.checks?.forward_evidence || null;
  const trackedPositionsCheck = measurementGate?.checks?.tracked_positions || null;
  const dailyTruthRefresh = optionsProfitStatus?.daily_truth_refresh || null;
  const exactContractCount = Number(forwardEvidence?.exact_contract_capture_counts?.with_contract_count || 0);
  const totalForwardCaptures = Number(forwardEvidence?.scan_pick_count || 0);
  const exactContractCoveragePct = totalForwardCaptures > 0
    ? (exactContractCount / totalForwardCaptures) * 100
    : null;
  const contractResolutionOverview =
    forwardEvidence?.archived_forward_artifact?.contract_resolution_overview || null;
  const trackedDbStatus = trackedPositionsCheck?.available
    ? "READY"
    : trackedPositionsCheck?.database_url_configured
      ? "DOWN"
      : "MISSING";
  const blockerMessages = (measurementGate?.blockers || [])
    .map((item) => {
      if (typeof item === "string") return item;
      return String(item?.message || item?.code || "").trim();
    })
    .filter(Boolean)
    .slice(0, 3);

  if (!activePlaybook && !forwardEvidence && !optionsProfitStatus && !truthHealthError && !policy && !policyError) {
    return null;
  }

  return (
    <details className="rounded-lg border border-border bg-bg-1 px-4 py-3">
      <summary className="cursor-pointer text-sm font-semibold text-text-0">
        Evidence & guardrails
        <span className="ml-2 font-mono text-xs font-normal text-text-2">
          Gate {fmtUpperLabel(gateState)} | Policy {promotionStatus.toUpperCase()}
        </span>
      </summary>
      <div className="mt-4 space-y-4">
        {activePlaybook && (
          <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
            <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-text-0">{activePlaybookLabel} Playbook</div>
                <p className="text-xs text-text-3 mt-1">{activePlaybook.description}</p>
                {activePlaybook.allowed_tickers?.length ? (
                  <div className="text-[11px] uppercase tracking-wide text-text-3 mt-2">
                    Managed lane
                    {activePlaybook.allowed_tickers.length
                      ? ` \u00b7 Universe ${activePlaybook.allowed_tickers.join(" / ")}`
                      : ""}
                  </div>
                ) : null}
                {typeof activePlaybook.historical_scan_ready_count === "number" && (
                  <div className="text-[11px] uppercase tracking-wide text-emerald-200/80 mt-1">
                    Theta EOD ready {activePlaybook.historical_scan_ready_count}/{activePlaybook.historical_scan_required_count ?? activePlaybook.allowed_tickers?.length ?? 0}
                    {typeof activePlaybook.historical_core_ready_count === "number"
                      ? ` \u00b7 Core ${activePlaybook.historical_core_ready_count}/${activePlaybook.historical_core_required_count ?? 0}`
                      : ""}
                  </div>
                )}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <MetricCard label="Target DTE" value={String(activePlaybook.target_dte)} />
                <MetricCard label="Day Cap" value={String(activePlaybook.max_new_positions_per_day)} />
                <MetricCard label="Sector Cap" value={String(activePlaybook.max_sector_open_positions)} />
                <MetricCard label="Regime Cap" value={String(activePlaybook.max_regime_open_positions)} />
              </div>
            </div>

            {exposureSnapshot && (
              <div className="space-y-3">
                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                  <MetricCard label="Open Positions" value={String(exposureSnapshot.open_positions)} />
                  <MetricCard label="Opened Today" value={String(exposureSnapshot.opened_today)} />
                  <MetricCard label="Guardrail Clear" value={String(clearCount)} />
                  <MetricCard label="Guardrail Caution" value={String(cautionCount)} />
                  <MetricCard label="Guardrail Blocked" value={String(guardrailBlockedCount)} />
                </div>
                <div className="text-xs text-text-3">
                  Opened today {exposureSnapshot.opened_today}/{activePlaybook.max_new_positions_per_day}
                  {" "}&middot; Same-sector cap {activePlaybook.max_sector_open_positions}
                  {" "}&middot; Same-regime cap {activePlaybook.max_regime_open_positions}
                </div>
                {(policy?.priced_trade_count != null ||
                  policy?.unpriced_trade_count != null ||
                  policy?.entry_quote_time_et ||
                  policy?.exit_quote_time_et) && (
                  <div className="text-[11px] uppercase tracking-wide text-text-3 mt-1">
                    {policy?.priced_trade_count != null || policy?.unpriced_trade_count != null
                      ? `Priced ${policy?.priced_trade_count ?? 0} / Unpriced ${policy?.unpriced_trade_count ?? 0}`
                      : "Quote windows active"}
                    {policy?.entry_quote_time_et ? ` | Entry ${policy.entry_quote_time_et}` : ""}
                    {policy?.exit_quote_time_et ? ` | Exit ${policy.exit_quote_time_et}` : ""}
                  </div>
                )}
              </div>
            )}

            {exposureSnapshot?.warnings?.length ? (
              <div className="space-y-1">
                {exposureSnapshot.warnings.map((line) => (
                  <div key={line} className="text-xs text-text-3">
                    {line}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        )}

        {(forwardEvidence || optionsProfitStatus || truthHealthError) && (
          <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
            <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-text-0">Options Truth Health</div>
                <p className="text-xs text-text-3 mt-1">
                  This surface summarizes whether current scanner evidence is fresh enough, exact enough, and operationally usable for supervised decisions.
                </p>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <MetricCard label="Gate" value={fmtUpperLabel(gateState)} />
                <MetricCard label="Truth Horizon" value={fmtDate(forwardGateCheck?.trusted_truth_horizon as string | null | undefined)} />
                <MetricCard label="Eligible Live" value={String(forwardGateCheck?.eligible_event_count ?? 0)} />
                <MetricCard label="Exact Coverage" value={exactContractCoveragePct != null ? `${exactContractCoveragePct.toFixed(0)}%` : "\u2014"} />
                <MetricCard label="Tracked DB" value={trackedDbStatus} />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Imported Daily</div>
                <div className="text-sm text-text-1">
                  {importedDailyCheck?.present && importedDailyCheck?.matches_store
                    ? `Coverage ${Number(importedDailyCheck.quote_coverage_pct ?? 0).toFixed(1)}%`
                    : "Artifact missing or stale"}
                </div>
                <div className="text-xs text-text-3">
                  Refresh {fmtCompactLabel(dailyTruthRefresh?.status as string | null | undefined)}
                  {dailyTruthRefresh?.stage ? ` \u00b7 ${fmtCompactLabel(dailyTruthRefresh.stage as string)}` : ""}
                </div>
              </div>
              <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Authoritative Forward</div>
                <div className="text-sm text-text-1">
                  {String(forwardEvidence?.authoritative_session_count ?? 0)} sessions &middot; {String(forwardEvidence?.scan_pick_count ?? 0)} picks
                </div>
                <div className="text-xs text-text-3">
                  Pending truth {String(forwardGateCheck?.pending_truth_event_count ?? 0)}
                  {" "}&middot; Artifact {forwardEvidence?.archived_forward_artifact?.available ? "ready" : "waiting"}
                </div>
              </div>
              <div className="bg-bg-3 border border-border rounded-lg p-3 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Contract Quality</div>
                <div className="text-sm text-text-1">
                  {exactContractCount}/{totalForwardCaptures || 0} captures kept exact
                </div>
                <div className="text-xs text-text-3">
                  Fallback {forwardEvidence?.archived_forward_artifact?.primary_judge_fallback_used ? fmtCompactLabel(forwardEvidence.archived_forward_artifact.primary_judge_fallback_reason) : "none"}
                </div>
                {contractResolutionOverview && (
                  <div className="text-xs text-text-3">
                    Archived {String(contractResolutionOverview.exact_archived_contract ?? 0)}
                    {" "}&middot; Model {String(contractResolutionOverview.exact_target_contract ?? 0)}
                    {" "}&middot; Nearest {String(contractResolutionOverview.nearest_listed_contract ?? 0)}
                    {" "}&middot; Pending {String(contractResolutionOverview.pending_truth_horizon ?? 0)}
                  </div>
                )}
              </div>
            </div>

            {truthHealthError && (
              <div className="bg-red-dim border border-red/30 rounded-lg px-3 py-2 text-xs text-red">
                {truthHealthError}
              </div>
            )}

            {gateState !== "healthy" && blockerMessages.length > 0 && (
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
                {blockerMessages.map((line) => (
                  <div key={line} className="text-xs text-amber-200">
                    {line}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <PaperGateOperatorPanel workflow={optionsProfitStatus?.paper_gate_operator_workflow} />

        {policy && (
          <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
            <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-text-0">Replay-Backed Policy State</div>
                <p className="text-xs text-text-3 mt-1">
                  This scanner gate follows the latest saved options truth artifacts. It is a truth layer, not a promise that the strategy is ready for trust-by-default.
                </p>
                {sourceLabel && (
                  <div className="text-[11px] uppercase tracking-wide text-text-3 mt-2">
                    Source {sourceLabel}
                  </div>
                )}
                <div className="text-[11px] uppercase tracking-wide text-text-3 mt-1">
                  Truth {truthSourceLabel}
                  {quoteCoverage != null ? ` | Coverage ${Number(quoteCoverage).toFixed(1)}%` : ""}
                </div>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <MetricCard label="Status" value={promotionStatus.toUpperCase()} />
                <MetricCard label="Scan Pool" value={String(candidateCount)} />
                <MetricCard label="Approved" value={String(approvedCount)} />
                <MetricCard label="Watch" value={String(watchCount)} />
                <MetricCard label="Blocked" value={String(blockedCount)} />
              </div>
            </div>

            {!useRecommendedPolicy && (
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
                <div className="text-xs text-amber-200">
                  Replay-Backed Focus is overridden. You are looking at all qualifying ideas, but the policy state above still describes the latest replay-backed truth and should be used as the risk context for any manual entry.
                </div>
              </div>
            )}

            {!policyIsPromoted && (
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
                <div className="text-xs text-amber-200">
                  Current policy state is <strong>{promotionStatus.toUpperCase()}</strong>, and the current truth lane is <strong>{truthSourceLabel.toUpperCase()}</strong>, so scanner ideas should be treated as watch-oriented and supervised paper-first unless you choose to override that manually.
                </div>
                {approvedReplayTrades === 0 && (
                  <div className="text-xs text-amber-200">
                    The active {playbook.replaceAll("_", " ")} replay audit has zero approved trades in the latest saved artifact.
                  </div>
                )}
                {approvedCount === 0 && (
                  <div className="text-xs text-amber-200">
                    There are zero approved live picks in this scan right now.
                  </div>
                )}
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="bg-bg-3 border border-border rounded-lg p-3">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Hard Gate</div>
                <div className="text-sm text-text-1 mt-1">
                  {hardFilters?.direction_score_min != null
                    ? `Direction score ${hardFilters.direction_score_min.toFixed(0)}${hardFilters.direction_score_max != null ? `-${hardFilters.direction_score_max.toFixed(0)}` : "+"}`
                    : "No score-band gate available yet"}
                </div>
              </div>
              <div className="bg-bg-3 border border-border rounded-lg p-3">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Preferred Context</div>
                <div className="text-sm text-text-1 mt-1">
                  {[
                    preferred?.asset_class ? preferred.asset_class : null,
                    ...(preferred?.market_regimes || []),
                  ].filter(Boolean).join(" / ") || "No broad asset-regime preference yet"}
                </div>
              </div>
              <div className="bg-bg-3 border border-border rounded-lg p-3">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Preferred Sectors</div>
                <div className="text-sm text-text-1 mt-1">
                  {preferred?.sectors?.length ? preferred.sectors.join(", ") : "No broad sector preference yet"}
                </div>
              </div>
            </div>

            {policy.scan_policy.rationale.length > 0 && (
              <div className="space-y-1">
                {policy.scan_policy.rationale.map((line) => (
                  <div key={line} className="text-xs text-text-2">
                    {line}
                  </div>
                ))}
              </div>
            )}

            {policy.scan_policy.warnings.length > 0 && (
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 space-y-1">
                {policy.scan_policy.warnings.map((line) => (
                  <div key={line} className="text-xs text-amber-200">
                    {line}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {policyError && (
          <div className="bg-red-dim border border-red/30 rounded-lg px-4 py-3 text-sm text-red">
            {policyError}
          </div>
        )}
      </div>
    </details>
  );
}
