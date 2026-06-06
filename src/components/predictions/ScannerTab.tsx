"use client";

import { memo, useMemo } from "react";
import { RefreshCw } from "lucide-react";
import FinTable from "@/components/ui/FinTable";
import Button from "@/components/ui/Button";
import { OperatorSessionPanel } from "@/components/predictions/OperatorSessionPanel";
import { ScannerEvidencePanel } from "@/components/predictions/ScannerEvidencePanel";
import { ScannerPickRecordForm } from "@/components/predictions/ScannerPickRecordForm";
import {
  fmtDate,
  fmtMoney,
  fmtRiskUpsideLabel,
  quoteContextLabel,
} from "@/components/predictions/tradingDeskFormat";
import {
  displayLaneLabel,
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
  { id: "tracked_winner_observation", label: "Tracked Winner Research" },
  { id: "quality90_debit55_canary", label: "Quality 90 Debit 55 Canary" },
  { id: "bearish_index_put_observation", label: "Bearish Index Put" },
  { id: "range_breakout_observation", label: "Range Breakout" },
  { id: "volatility_expansion_observation", label: "Volatility Expansion" },
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
  submittingAlpacaPaperOrder: boolean;
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
  onSubmitAlpacaPaper: () => void;
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
  submittingAlpacaPaperOrder,
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
  onSubmitAlpacaPaper,
}: ScannerTabProps) {
  const promotionStatus = String(
    policy?.scan_policy.promotion_status || policy?.promotion_status || "watch"
  ).toLowerCase();
  const policyIsPromoted = promotionStatus === "promote";

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

      <OperatorSessionPanel onUnlocked={onRefresh} />

      <ScannerEvidencePanel
        useRecommendedPolicy={useRecommendedPolicy}
        policy={policy}
        policyError={policyError}
        exitAudit={exitAudit}
        decisionCounts={decisionCounts}
        guardrailCounts={guardrailCounts}
        candidateCount={candidateCount}
        forwardEvidence={forwardEvidence}
        optionsProfitStatus={optionsProfitStatus}
        truthHealthError={truthHealthError}
        playbook={playbook}
        playbooks={playbooks}
        exposureSnapshot={exposureSnapshot}
      />

      <ScannerPickRecordForm
        selectedPick={selectedPick}
        policyIsPromoted={policyIsPromoted}
        useRecommendedPolicy={useRecommendedPolicy}
        fillPrice={fillPrice}
        contracts={contracts}
        notes={notes}
        takingTrade={takingTrade}
        savingSuggestedTrade={savingSuggestedTrade}
        submittingAlpacaPaperOrder={submittingAlpacaPaperOrder}
        onCancel={onCancel}
        onFillPriceChange={onFillPriceChange}
        onContractsChange={onContractsChange}
        onNotesChange={onNotesChange}
        onSubmit={onSubmit}
        onSubmitSuggested={onSubmitSuggested}
        onSubmitAlpacaPaper={onSubmitAlpacaPaper}
      />

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
