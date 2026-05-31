"use client";

import { History, Save } from "lucide-react";
import { useMemo } from "react";
import Button from "@/components/ui/Button";
import FinTable from "@/components/ui/FinTable";
import type { StrategyProfile } from "@/lib/types";
import { ProfileSkeleton, Slider } from "@/components/strategy/shared";

type BrainTabProps = {
  profile: StrategyProfile | undefined;
  profileType: "equity" | "index";
  onProfileTypeChange: (t: "equity" | "index") => void;
  getVal: (section: string, key: string, fallback: number | boolean) => number | boolean;
  setVal: (section: string, key: string, value: number | boolean) => void;
  edits: Record<string, Record<string, unknown>>;
  saving: boolean;
  saveNote: string;
  setSaveNote: (s: string) => void;
  onSave: () => void;
  changelog: Record<string, unknown>[];
};

export function BrainTab({
  profile,
  profileType,
  onProfileTypeChange,
  getVal,
  setVal,
  edits,
  saving,
  saveNote,
  setSaveNote,
  onSave,
  changelog,
}: BrainTabProps) {
  const hasEdits = Object.keys(edits).length > 0;

  const reversedChangelog = useMemo(
    () =>
      [...changelog].reverse().slice(0, 20).map((entry) => ({
        Timestamp: (entry.ts as string) || "",
        Profile: (entry.profile as string) || "equity",
        Details: (entry.note as string) || "",
      })),
    [changelog]
  );

  return (
    <div className="space-y-6">
      <div className="flex gap-2">
        {(["equity", "index"] as const).map((t) => (
          <Button
            key={t}
            variant={profileType === t ? "primary" : "secondary"}
            onClick={() => onProfileTypeChange(t)}
          >
            {t === "equity" ? "Equity (Single Stocks)" : "Index (ETFs)"}
          </Button>
        ))}
      </div>

      {!profile ? (
        <ProfileSkeleton />
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="space-y-4">
            <div className="rounded-lg border border-border bg-bg-2 p-4">
              <div className="section-header mt-0">Direction Score Weights</div>
              <Slider label="Tech setup" value={getVal("direction_score_weights", "tech", 0.55) as number} min={0.1} max={0.8} step={0.05} onChange={(v) => setVal("direction_score_weights", "tech", v)} />
              <Slider label="SPY regime" value={getVal("direction_score_weights", "regime", 0.3) as number} min={0.05} max={0.6} step={0.05} onChange={(v) => setVal("direction_score_weights", "regime", v)} />
              <Slider label="Momentum" value={getVal("direction_score_weights", "momentum", 0.15) as number} min={0} max={0.4} step={0.05} onChange={(v) => setVal("direction_score_weights", "momentum", v)} />

              <div className="section-header">RSI Overextension</div>
              <Slider label="Severe threshold" value={getVal("rsi_overextension", "severe_threshold", 72) as number} min={60} max={80} step={1} onChange={(v) => setVal("rsi_overextension", "severe_threshold", v)} />
              <Slider label="Moderate threshold" value={getVal("rsi_overextension", "moderate_threshold", 68) as number} min={55} max={75} step={1} onChange={(v) => setVal("rsi_overextension", "moderate_threshold", v)} />
              <Slider label="Severe penalty" value={getVal("rsi_overextension", "severe_penalty", 15) as number} min={5} max={25} step={1} suffix=" pts" onChange={(v) => setVal("rsi_overextension", "severe_penalty", v)} />
              <Slider label="Moderate penalty" value={getVal("rsi_overextension", "moderate_penalty", 8) as number} min={1} max={15} step={1} suffix=" pts" onChange={(v) => setVal("rsi_overextension", "moderate_penalty", v)} />
            </div>

            <div className="rounded-lg border border-border bg-bg-2 p-4">
              <div className="section-header mt-0">Quality Score Weights</div>
              <Slider label="IV Rank weight" value={getVal("quality_score_weights", "iv_rank", 0.4) as number} min={0.1} max={0.7} step={0.05} onChange={(v) => setVal("quality_score_weights", "iv_rank", v)} />
              <Slider label="Delta fit weight" value={getVal("quality_score_weights", "delta", 0.35) as number} min={0.1} max={0.6} step={0.05} onChange={(v) => setVal("quality_score_weights", "delta", v)} />
              <Slider label="DTE fit weight" value={getVal("quality_score_weights", "dte", 0.25) as number} min={0.05} max={0.5} step={0.05} onChange={(v) => setVal("quality_score_weights", "dte", v)} />

              <div className="section-header">Strike & Expiry Targets</div>
              <Slider label="Delta sweet spot" value={getVal("targets", "delta_optimal", 0.3) as number} min={0.15} max={0.55} step={0.05} onChange={(v) => setVal("targets", "delta_optimal", v)} />
              <Slider label="Delta window +/-" value={getVal("targets", "delta_falloff", 0.2) as number} min={0.05} max={0.35} step={0.05} onChange={(v) => setVal("targets", "delta_falloff", v)} />
              <Slider label="DTE sweet spot" value={getVal("targets", "dte_optimal", 10) as number} min={5} max={35} step={1} suffix=" days" onChange={(v) => setVal("targets", "dte_optimal", v)} />
              <Slider label="DTE window +/-" value={getVal("targets", "dte_falloff", 20) as number} min={3} max={15} step={1} suffix=" days" onChange={(v) => setVal("targets", "dte_falloff", v)} />
            </div>
          </div>

          <div className="space-y-4">
            <div className="rounded-lg border border-border bg-bg-2 p-4">
              <div className="section-header mt-0">Entry Gates</div>
              <Slider label="Max IV rank" value={getVal("targets", "iv_percentile_max", 50) as number} min={20} max={80} step={5} onChange={(v) => setVal("targets", "iv_percentile_max", v)} />
              <Slider label="Min EV %" value={getVal("filters", "min_ev_return_pct", 10) as number} min={3} max={25} step={1} suffix="%" onChange={(v) => setVal("filters", "min_ev_return_pct", v)} />
              <Slider label="Max spread %" value={getVal("filters", "liquidity_spread_max_pct", 1.5) as number} min={0.5} max={5} step={0.5} suffix="%" onChange={(v) => setVal("filters", "liquidity_spread_max_pct", v)} />

              <div className="section-header">Momentum & Technical Gates</div>
              <Slider label="Min Direction Score" value={getVal("entry", "min_direction_score", 35) as number} min={20} max={65} step={5} onChange={(v) => setVal("entry", "min_direction_score", v)} />
              <Slider label="Min Tech Score" value={getVal("entry", "min_tech_score", 55) as number} min={30} max={75} step={5} onChange={(v) => setVal("entry", "min_tech_score", v)} />
              <Slider label="Momentum threshold" value={getVal("entry", "entry_momentum_pct", 0.5) as number} min={0.1} max={1.5} step={0.1} suffix="%" onChange={(v) => setVal("entry", "entry_momentum_pct", v)} />
            </div>

            <div className="rounded-lg border border-border bg-bg-2 p-4">
              <div className="section-header mt-0">Exit Rules</div>
              <Slider label="Stop-loss" value={getVal("risk", "stop_loss_pct", 90) as number} min={20} max={90} step={5} suffix="%" onChange={(v) => setVal("risk", "stop_loss_pct", v)} />
              <Slider label="Profit target" value={getVal("risk", "profit_target_pct", 100) as number} min={50} max={200} step={10} suffix="%" onChange={(v) => setVal("risk", "profit_target_pct", v)} />
              <Slider label="Time exit" value={getVal("risk", "time_exit_pct", 50) as number} min={25} max={90} step={5} suffix="% DTE" onChange={(v) => setVal("risk", "time_exit_pct", v)} />
              <Slider label="Max drawdown" value={getVal("risk", "max_drawdown_pct", 15) as number} min={5} max={30} step={1} suffix="%" onChange={(v) => setVal("risk", "max_drawdown_pct", v)} />
            </div>

            <div className="rounded-lg border border-border bg-bg-2 p-4">
              <div className="section-header mt-0">Defense & IV Filters</div>
              <Slider label="VIX defense level" value={getVal("filters", "vix_defense_threshold", 25) as number} min={18} max={40} step={1} onChange={(v) => setVal("filters", "vix_defense_threshold", v)} />
              <Slider label="Defense size mult" value={getVal("filters", "defense_position_mult", 0.5) as number} min={0.2} max={0.9} step={0.1} suffix="x" onChange={(v) => setVal("filters", "defense_position_mult", v)} />
              <Slider label="IV crush sigma" value={getVal("filters", "iv_crush_z_threshold", 2.0) as number} min={1} max={3.5} step={0.5} onChange={(v) => setVal("filters", "iv_crush_z_threshold", v)} />
              <Slider label="IV crush penalty" value={getVal("filters", "iv_crush_confidence_penalty", 20) as number} min={5} max={30} step={5} suffix=" pts" onChange={(v) => setVal("filters", "iv_crush_confidence_penalty", v)} />
            </div>

            <div className="rounded-lg border border-border bg-bg-2 p-4">
              <div className="section-header mt-0">Position Sizing</div>
              <Slider label="Min position" value={getVal("risk", "min_position_pct", 7) as number} min={1} max={20} step={1} suffix="%" onChange={(v) => setVal("risk", "min_position_pct", v)} />
              <Slider label="Max position" value={getVal("risk", "max_position_pct", 40) as number} min={10} max={60} step={5} suffix="%" onChange={(v) => setVal("risk", "max_position_pct", v)} />
            </div>
          </div>
        </div>
      )}

      {hasEdits ? (
        <div className="sticky bottom-4 flex items-center gap-4 rounded-lg border border-accent/30 bg-bg-3 p-4 shadow-lg">
          <input
            type="text"
            value={saveNote}
            onChange={(e) => setSaveNote(e.target.value)}
            placeholder="Change note (optional)..."
            aria-label="Change note"
            className="flex-1 rounded border border-border bg-bg-2 px-3 py-2 text-sm text-text-0"
          />
          <Button variant="primary" onClick={onSave} loading={saving} icon={<Save size={14} />}>
            {saving ? "Saving..." : "Save Changes"}
          </Button>
        </div>
      ) : null}

      <div className="rounded-lg border border-border bg-bg-2 p-4">
        <div className="mb-3 flex items-center gap-2">
          <History size={14} className="text-text-3" />
          <span className="section-header mb-0 mt-0 border-0 pb-0">Version History</span>
        </div>
        {changelog.length === 0 ? (
          <p className="text-xs text-text-3">No changes recorded yet.</p>
        ) : (
          <FinTable data={reversedChangelog} maxHeight="200px" />
        )}
      </div>
    </div>
  );
}
