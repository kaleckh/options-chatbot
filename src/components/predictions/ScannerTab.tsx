"use client";

import { memo, useMemo } from "react";
import { RefreshCw } from "lucide-react";
import MetricCard from "@/components/ui/MetricCard";
import FinTable from "@/components/ui/FinTable";
import Button from "@/components/ui/Button";
import {
  contractQualityLabel,
  fmtCompactLabel,
  fmtDate,
  fmtMoney,
  fmtRiskUpsideLabel,
  fmtTruthSource,
  fmtUpperLabel,
  quoteContextLabel,
} from "@/components/predictions/tradingDeskFormat";
import {
  displayLaneLabel,
  fmtContractCoreLabel,
  fmtContractLabel,
} from "@/components/predictions/trackedPositionUtils";
import type {
  ExposureSnapshot,
  ForwardEvidenceReport,
  LiveTradePolicy,
  OptionsProfitStatus,
  PlaybookExitAudit,
  ScanPick,
  ScanPlaybook,
} from "@/lib/types";

const FALLBACK_SCAN_PLAYBOOKS = [
  { id: "bullish_pullback_observation", label: "Bullish Pullback" },
  { id: "tracked_winner_primary", label: "Tracked Winner Primary" },
  { id: "short_term", label: "Short-Term" },
  { id: "swing", label: "Swing" },
  { id: "bullish_momentum", label: "Bullish Momentum" },
  { id: "bearish_defensive", label: "Bearish Defensive" },
  { id: "regular_bearish_put_primary", label: "Regular Bearish Put Primary" },
  { id: "tracked_winner_observation", label: "Tracked Winner Observation" },
  { id: "quality90_debit55_canary", label: "Quality 90 Debit 55 Canary" },
  { id: "bearish_index_put_observation", label: "Bearish Index Put Observation" },
  { id: "range_breakout_observation", label: "Range Breakout Observation" },
  { id: "volatility_expansion_observation", label: "Volatility Expansion Observation" },
  { id: "speculative", label: "Speculative" },
] as const;

const SCANNER_MONO_COLS: string[] = [
  "Contract",
  "Quote",
  "Dir. Score",
  "Quality",
  "Size",
  "Stock",
  "Premium",
  "Strike",
];

const SCANNER_MOBILE_PRIORITY_COLS: string[] = [
  "Decision",
  "Guardrails",
  "Quote",
  "Premium",
  "Strike",
  "Expiry",
  "Dir. Score",
  "Quality",
];

const SCANNER_MOBILE_HIDDEN_COLS: string[] = ["Contract", "Guardrail Detail"];

type ScannerTabProps = {
  picks: ScanPick[];
  loading: boolean;
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
  showBlockedIdeas: boolean;
  selectedPick: ScanPick | null;
  fillPrice: string;
  contracts: string;
  notes: string;
  takingTrade: boolean;
  savingSuggestedTrade: boolean;
  onRefresh: () => void;
  onPolicyModeChange: (value: boolean) => void;
  onPlaybookChange: (value: string) => void;
  onShowBlockedIdeasChange: (value: boolean) => void;
  onPick: (pick: ScanPick) => void;
  onCancel: () => void;
  onFillPriceChange: (value: string) => void;
  onContractsChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onSubmit: () => void;
  onSubmitSuggested: () => void;
};

export const ScannerTab = memo(function ScannerTab({
  picks,
  loading,
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
  showBlockedIdeas,
  selectedPick,
  fillPrice,
  contracts,
  notes,
  takingTrade,
  savingSuggestedTrade,
  onRefresh,
  onPolicyModeChange,
  onPlaybookChange,
  onShowBlockedIdeasChange,
  onPick,
  onCancel,
  onFillPriceChange,
  onContractsChange,
  onNotesChange,
  onSubmit,
  onSubmitSuggested,
}: ScannerTabProps) {
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

  const rows = useMemo(() => picks.map((pick) => ({
    Ticker: pick.ticker,
    Trade: pick.direction === "call" ? "\u25B2 CALL" : "\u25BC PUT",
    Contract: fmtContractLabel({
      ticker: pick.ticker,
      direction: pick.direction,
      strike: pick.strike ?? pick.strike_est,
      short_strike: pick.short_strike,
      expiry: pick.expiry,
      contract_symbol: pick.contract_symbol,
    }),
    Quote: quoteContextLabel(pick),
    "Dir. Score": pick.direction_score.toFixed(0),
    Quality: pick.quality_score.toFixed(0),
    Decision: pick.policy_decision
      ? pick.policy_decision === "approved"
        ? "Approved"
        : pick.policy_decision === "watch"
          ? "Watch"
          : "Blocked"
      : "\u2014",
    Guardrails: pick.guardrail_decision
      ? pick.guardrail_decision === "clear"
        ? "Clear"
        : pick.guardrail_decision === "caution"
          ? "Caution"
          : "Blocked"
      : "\u2014",
    Size: pick.suggested_size_tier ? pick.suggested_size_tier.toUpperCase() : "\u2014",
    "Risk/Upside": fmtRiskUpsideLabel(pick),
    Regime: pick.market_regime ? pick.market_regime.toUpperCase() : "\u2014",
    Sector: pick.sector || "\u2014",
    Stock: fmtMoney(pick.stock_price),
    Premium: fmtMoney(pick.premium ?? pick.est_premium),
    Strike: fmtMoney(pick.strike ?? pick.strike_est, 0),
    Expiry: fmtDate(pick.expiry),
    "Target Move": pick.target_move_pct != null ? `${pick.target_move_pct.toFixed(2)}%` : "\u2014",
    Action: (
      <Button size="sm" variant="secondary" onClick={() => onPick(pick)}>
        {pick.guardrail_decision === "blocked"
          ? "Inspect"
          : pick.guardrail_decision === "caution"
            ? "Take Smaller"
            : pick.policy_decision === "approved"
              ? "Take Approved"
              : pick.policy_decision === "watch"
                ? "Take Watch"
                : "Take Trade"}
      </Button>
    ),
  })), [onPick, picks]);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="text-lg font-semibold text-text-0">Live Scanner</div>
          <p className="mt-1 text-sm text-text-2">
            Current supervised setups, filtered by playbook and replay policy.
          </p>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <label className="flex items-center gap-2 text-xs font-medium text-text-2">
            <span>Playbook</span>
            <select
              value={playbook}
              onChange={(event) => onPlaybookChange(event.target.value)}
              className="min-w-[220px] rounded-md border border-border bg-bg-2 px-3 py-1.5 text-sm text-text-0"
            >
              {(playbooks.length ? playbooks : FALLBACK_SCAN_PLAYBOOKS).map((item) => (
                <option key={item.id} value={item.id}>{displayLaneLabel(item.id, item.label)}</option>
              ))}
            </select>
          </label>
          <div className="inline-flex rounded-md border border-border bg-bg-2 p-1">
            <Button
              size="sm"
              variant={useRecommendedPolicy ? "secondary" : "ghost"}
              aria-pressed={useRecommendedPolicy}
              onClick={() => onPolicyModeChange(true)}
            >
              Replay Focus
            </Button>
            <Button
              size="sm"
              variant={!useRecommendedPolicy ? "secondary" : "ghost"}
              aria-pressed={!useRecommendedPolicy}
              onClick={() => onPolicyModeChange(false)}
            >
              All Qualifying
            </Button>
          </div>
          <Button
            variant="secondary"
            size="sm"
            loading={loading}
            icon={<RefreshCw size={12} />}
            onClick={onRefresh}
          >
            Refresh Scan
          </Button>
          <Button
            size="sm"
            variant={showBlockedIdeas ? "secondary" : "ghost"}
            aria-pressed={showBlockedIdeas}
            onClick={() => onShowBlockedIdeasChange(!showBlockedIdeas)}
          >
            {showBlockedIdeas ? "Hide Blocked" : "Show Blocked"}
          </Button>
        </div>
      </div>

      {(activePlaybook || forwardEvidence || optionsProfitStatus || truthHealthError || policy || policyError) && (
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
      )}

      {selectedPick && (
        <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
          <div>
            <div className="text-sm font-semibold text-text-0">
              Record {fmtContractCoreLabel({
                ticker: selectedPick.ticker,
                direction: selectedPick.direction,
                strike: selectedPick.strike ?? selectedPick.strike_est,
                short_strike: selectedPick.short_strike,
                expiry: selectedPick.expiry,
              })}
            </div>
            <div className="text-xs text-text-3 mt-1">
              {fmtContractLabel({
                ticker: selectedPick.ticker,
                direction: selectedPick.direction,
                strike: selectedPick.strike ?? selectedPick.strike_est,
                short_strike: selectedPick.short_strike,
                expiry: selectedPick.expiry,
                contract_symbol: selectedPick.contract_symbol,
              })}
              {" "}&middot; Scan premium {fmtMoney(selectedPick.premium ?? selectedPick.est_premium)}
            </div>
            {(!policyIsPromoted || selectedPick.policy_decision !== "approved") && (
              <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg px-3 py-2 mt-3 text-xs text-amber-200">
                {useRecommendedPolicy
                  ? "This setup is not replay-approved right now. Saving it as a tracked position is still allowed, but it should be treated as supervised paper-first decision support."
                  : "Replay-Backed Focus is overridden, and this setup is not replay-approved right now. Saving it as a tracked position is still allowed, but it should be treated as supervised paper-first decision support."}
              </div>
            )}
            {selectedPick.policy_decision && (
              <div className="text-xs text-text-2 mt-2 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Policy</div>
                <div>
                  Decision: <strong className="text-text-0">{selectedPick.policy_decision.toUpperCase()}</strong>
                </div>
                {selectedPick.policy_fit_reasons?.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
              </div>
            )}
            {selectedPick.guardrail_decision && (
              <div className="text-xs text-text-2 mt-2 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Portfolio Guardrails</div>
                <div>
                  Guardrails: <strong className="text-text-0">{selectedPick.guardrail_decision.toUpperCase()}</strong>
                  {" "}&middot; Size tier <strong className="text-text-0">{selectedPick.suggested_size_tier?.toUpperCase() || "\u2014"}</strong>
                </div>
                {selectedPick.guardrail_reasons?.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
                {selectedPick.suggested_size_reason && <div>{selectedPick.suggested_size_reason}</div>}
              </div>
            )}
            {(selectedPick.risk_tier != null ||
              selectedPick.upside_tier != null ||
              selectedPick.convexity_class) && (
              <div className="text-xs text-text-2 mt-2 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-text-3">Risk Profile</div>
                <div>
                  Convexity: <strong className="text-text-0">{fmtUpperLabel(selectedPick.convexity_class)}</strong>
                  {" "}&middot; {fmtRiskUpsideLabel(selectedPick)}
                  {selectedPick.speculative_flag ? " \u00b7 SPECULATIVE" : ""}
                </div>
                {selectedPick.speculative_reason?.map((reason) => (
                  <div key={reason}>{reason}</div>
                ))}
              </div>
            )}
            <div className="text-xs text-text-2 mt-2 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-text-3">Contract And Quote Provenance</div>
              <div>
                Contract quality: <strong className="text-text-0">{contractQualityLabel(selectedPick)}</strong>
                {selectedPick.contract_symbol ? ` \u00b7 ${selectedPick.contract_symbol}` : ""}
              </div>
              <div>
                Quote: <strong className="text-text-0">{quoteContextLabel(selectedPick)}</strong>
                {selectedPick.quote_time_et ? ` \u00b7 ${selectedPick.quote_time_et}` : ""}
              </div>
              <div>
                Selection: <strong className="text-text-0">{fmtCompactLabel(selectedPick.selection_source)}</strong>
                {" "}&middot; Promotion <strong className="text-text-0">{fmtCompactLabel(selectedPick.promotion_class)}</strong>
              </div>
              <div>
                Entry execution: <strong className="text-text-0">{fmtCompactLabel(selectedPick.entry_execution_basis)}</strong>
                {" "}&middot; {fmtMoney(selectedPick.entry_execution_price ?? selectedPick.premium ?? selectedPick.est_premium)}
              </div>
              <div>
                Profitability: <strong className="text-text-0">{fmtUpperLabel(selectedPick.profitability_eligibility)}</strong>
                {selectedPick.profitability_blockers?.length
                  ? ` \u00b7 ${selectedPick.profitability_blockers.join(", ")}`
                  : ""}
              </div>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Entry price</span>
              <input
                type="number"
                min="0.01"
                step="0.01"
                value={fillPrice}
                onChange={(event) => onFillPriceChange(event.target.value)}
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0 font-mono"
              />
            </label>
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Contracts</span>
              <input
                type="number"
                min="1"
                step="1"
                value={contracts}
                onChange={(event) => onContractsChange(event.target.value)}
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0 font-mono"
              />
            </label>
            <label className="text-xs text-text-2 space-y-1">
              <span className="block">Notes</span>
              <input
                type="text"
                value={notes}
                onChange={(event) => onNotesChange(event.target.value)}
                placeholder="Optional note"
                className="w-full bg-bg-3 border border-border rounded px-3 py-2 text-sm text-text-0"
              />
            </label>
          </div>
          <div className="text-xs text-text-3">
            Eligible scheduled scanner picks are auto-tracked. Use this form for manual corrections or trades you actually placed outside the scheduled run.
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="sm"
              loading={takingTrade}
              disabled={selectedPick.guardrail_decision === "blocked" || savingSuggestedTrade}
              onClick={onSubmit}
            >
              Save Real Tracked Position
            </Button>
            <Button
              variant="secondary"
              size="sm"
              loading={savingSuggestedTrade}
              disabled={takingTrade}
              onClick={onSubmitSuggested}
            >
              Save Paper Idea
            </Button>
            <Button variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      {picks.length === 0 && !loading ? (
        <div className="text-sm text-text-3 bg-bg-2 rounded-lg p-6 text-center border border-border">
          No qualifying options picks were returned by the live scan.
        </div>
      ) : (
        <FinTable
          data={rows}
          badgeCol="Trade"
          monoCols={SCANNER_MONO_COLS}
          label="Live options scanner picks"
          maxHeight="620px"
          mobileTitleCol="Ticker"
          mobileSubtitleCol="Trade"
          mobilePriorityCols={SCANNER_MOBILE_PRIORITY_COLS}
          mobileHiddenCols={SCANNER_MOBILE_HIDDEN_COLS}
        />
      )}
    </div>
  );
});
