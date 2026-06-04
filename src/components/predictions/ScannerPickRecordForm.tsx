"use client";

import Button from "@/components/ui/Button";
import {
  contractQualityLabel,
  fmtCompactLabel,
  fmtMoney,
  fmtRiskUpsideLabel,
  fmtUpperLabel,
  quoteContextLabel,
} from "@/components/predictions/tradingDeskFormat";
import {
  fmtContractCoreLabel,
  fmtContractLabel,
} from "@/components/predictions/trackedPositionUtils";
import type { ScanPick } from "@/lib/types";

type ScannerPickRecordFormProps = {
  selectedPick: ScanPick | null;
  policyIsPromoted: boolean;
  useRecommendedPolicy: boolean;
  fillPrice: string;
  contracts: string;
  notes: string;
  takingTrade: boolean;
  savingSuggestedTrade: boolean;
  onCancel: () => void;
  onFillPriceChange: (value: string) => void;
  onContractsChange: (value: string) => void;
  onNotesChange: (value: string) => void;
  onSubmit: () => void;
  onSubmitSuggested: () => void;
};

export function ScannerPickRecordForm({
  selectedPick,
  policyIsPromoted,
  useRecommendedPolicy,
  fillPrice,
  contracts,
  notes,
  takingTrade,
  savingSuggestedTrade,
  onCancel,
  onFillPriceChange,
  onContractsChange,
  onNotesChange,
  onSubmit,
  onSubmitSuggested,
}: ScannerPickRecordFormProps) {
  if (!selectedPick) return null;

  return (
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
  );
}
