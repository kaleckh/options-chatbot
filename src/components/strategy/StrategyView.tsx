"use client";

import { useState, useEffect, useCallback, useMemo, useId } from "react";
import { Brain, Target, Save, History, Play } from "lucide-react";
import MetricCard from "@/components/ui/MetricCard";
import FinTable from "@/components/ui/FinTable";
import Button from "@/components/ui/Button";
import DayTradingLab from "@/components/strategy/DayTradingLab";
import { useToast } from "@/components/ui/Toast";
import { useSubmitGuard } from "@/lib/hooks";
import type {
  BacktestPricingLane,
  BacktestResult,
  BacktestReplayReport,
  MetricTruthReport,
  StrategyProfile,
  TruthLane,
  TruthLaneComparisonReport,
  TruthLaneSummary,
} from "@/lib/types";

// ── Constants ────────────────────────────────────────────────────────────────

const SUB_TABS = [
  { id: "brain", label: "Strategy Brain", icon: Brain },
  { id: "optimizer", label: "Optimizer", icon: Target },
  { id: "daytrading", label: "Day Trading", icon: Play },
] as const;

function fmtTruthSource(value?: string | null): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "historical_imported_daily") return "Imported daily validation";
  if (normalized === "historical_imported") return "Imported historical validation";
  if (normalized === "synthetic" || normalized === "synthetic_only") return "Synthetic research-only";
  return value ? `Unknown truth source (${value})` : "Unknown truth source";
}

function hasError(payload: unknown): payload is { error: string } {
  return Boolean(
    payload &&
    typeof payload === "object" &&
    !Array.isArray(payload) &&
    "error" in payload &&
    typeof (payload as { error?: unknown }).error === "string"
  );
}

// ── Main Component ───────────────────────────────────────────────────────────

export default function StrategyView() {
  const toast = useToast();
  const saveGuard = useSubmitGuard();
  const backtestGuard = useSubmitGuard();

  const [activeSubTab, setActiveSubTab] = useState("daytrading");
  const [profileType, setProfileType] = useState<"equity" | "index">("equity");
  const [profiles, setProfiles] = useState<Record<string, StrategyProfile> | null>(null);
  const [changelog, setChangelog] = useState<Record<string, unknown>[]>([]);
  const [profilesLoaded, setProfilesLoaded] = useState(false);
  const [changelogLoadedProfile, setChangelogLoadedProfile] = useState<"equity" | "index" | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveNote, setSaveNote] = useState("");
  const [edits, setEdits] = useState<Record<string, Record<string, unknown>>>({});

  // Backtest state
  const [backtestYears, setBacktestYears] = useState(5);
  const [ivAdj, setIvAdj] = useState(1.2);
  const [truthLane, setTruthLane] = useState<TruthLane>("historical_imported");
  const [pricingLane, setPricingLane] = useState<BacktestPricingLane>("pessimistic");
  const [backtestRunning, setBacktestRunning] = useState(false);
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [backtestReport, setBacktestReport] = useState<BacktestReplayReport | null>(null);
  const [metricTruthReport, setMetricTruthReport] = useState<MetricTruthReport | null>(null);
  const [comparisonReport, setComparisonReport] = useState<TruthLaneComparisonReport | null>(null);
  const [artifactNotice, setArtifactNotice] = useState<string | null>(null);

  const fetchProfiles = useCallback(async () => {
    try {
      const [equityRes, indexRes] = await Promise.all([
        fetch("/api/profile?type=equity"),
        fetch("/api/profile?type=index"),
      ]);
      const [equityProfile, indexProfile] = await Promise.all([
        equityRes.json().catch(() => ({})),
        indexRes.json().catch(() => ({})),
      ]);
      if (!equityRes.ok || hasError(equityProfile)) {
        throw new Error(
          hasError(equityProfile) ? equityProfile.error : `Failed to load equity profile (${equityRes.status})`
        );
      }
      if (!indexRes.ok || hasError(indexProfile)) {
        throw new Error(
          hasError(indexProfile) ? indexProfile.error : `Failed to load index profile (${indexRes.status})`
        );
      }
      setProfiles({
        equity: equityProfile as StrategyProfile,
        index: indexProfile as StrategyProfile,
      });
      setProfilesLoaded(true);
    } catch (err) {
      toast.error(`Failed to load profiles: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }, [toast]);

  const fetchChangelog = useCallback(async () => {
    try {
      const res = await fetch(`/api/changelog?profile=${profileType}`);
      if (res.ok) {
        setChangelog(await res.json());
        setChangelogLoadedProfile(profileType);
      }
    } catch (err) {
      toast.error(`Failed to load changelog: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }, [profileType, toast]);

  useEffect(() => {
    if (activeSubTab !== "brain") return;
    if (!profilesLoaded) {
      void fetchProfiles();
    }
    if (changelogLoadedProfile !== profileType) {
      void fetchChangelog();
    }
  }, [activeSubTab, changelogLoadedProfile, fetchChangelog, fetchProfiles, profileType, profilesLoaded]);

  const loadBacktestArtifacts = useCallback(async (lane: TruthLane) => {
    try {
      const params = new URLSearchParams({
        truth_lane: lane,
        min_trades: "20",
        bucket_size: "10",
      });
      const response = await fetch(`/api/backtest/summary?${params.toString()}`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok || hasError(payload)) {
        throw new Error(hasError(payload) ? payload.error : `Failed to load ${lane} backtest summary.`);
      }

      const lastData = (payload as Record<string, unknown>).last;
      const reportData = (payload as Record<string, unknown>).report;
      const truthData = (payload as Record<string, unknown>).metricTruth;
      const comparisonData = (payload as Record<string, unknown>).comparison;

      const primaryError =
        hasError(lastData)
          ? lastData.error
          : hasError(reportData)
            ? reportData.error
            : hasError(truthData)
              ? truthData.error
              : null;

      setBacktestResult(hasError(lastData) ? null : (lastData as BacktestResult | null));
      setBacktestReport(hasError(reportData) ? null : (reportData as BacktestReplayReport | null));
      setMetricTruthReport(hasError(truthData) ? null : (truthData as MetricTruthReport | null));
      setComparisonReport(hasError(comparisonData) ? null : ((comparisonData ?? null) as TruthLaneComparisonReport | null));
      setArtifactNotice(primaryError);
    } catch (err) {
      setBacktestResult(null);
      setBacktestReport(null);
      setMetricTruthReport(null);
      setComparisonReport(null);
      setArtifactNotice(err instanceof Error ? err.message : "unknown error");
      toast.error(`Failed to load backtest artifacts: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }, [toast]);

  useEffect(() => {
    if (activeSubTab !== "optimizer") return;
    void loadBacktestArtifacts(truthLane);
  }, [activeSubTab, loadBacktestArtifacts, truthLane]);

  const profile = profiles?.[profileType] as StrategyProfile | undefined;

  const getVal = (section: string, key: string, fallback: number | boolean): number | boolean => {
    if (edits[section]?.[key] !== undefined) return edits[section][key] as number | boolean;
    if (profile && (profile as unknown as Record<string, Record<string, unknown>>)[section]?.[key] !== undefined) {
      return (profile as unknown as Record<string, Record<string, unknown>>)[section][key] as number | boolean;
    }
    return fallback;
  };

  const setVal = (section: string, key: string, value: number | boolean) => {
    setEdits((prev) => ({
      ...prev,
      [section]: { ...prev[section], [key]: value },
    }));
  };

  const handleSave = async () => {
    if (!Object.keys(edits).length) return;
    await saveGuard.guard(async () => {
      setSaving(true);
      try {
        const res = await fetch("/api/profile", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            type: profileType,
            updates: edits,
            note: saveNote || `${profileType} profile updated`,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || hasError(data)) {
          throw new Error(hasError(data) ? data.error : `Failed to save profile (${res.status})`);
        }
        setEdits({});
        setSaveNote("");
        await fetchProfiles();
        await fetchChangelog();
        toast.success("Profile saved successfully");
      } catch (err) {
        toast.error(`Failed to save profile: ${err instanceof Error ? err.message : "unknown error"}`);
      } finally {
        setSaving(false);
      }
    });
  };

  const runBacktest = async () => {
    await backtestGuard.guard(async () => {
      setBacktestRunning(true);
      try {
        const res = await fetch("/api/backtest", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            lookback_years: backtestYears,
            iv_adj: ivAdj,
            truth_lane: truthLane,
            pricing_lane: truthLane === "synthetic" ? pricingLane : undefined,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || (data as Record<string, unknown>).error) {
          throw new Error(String((data as Record<string, unknown>).error || `Backtest failed with status ${res.status}`));
        }
        setBacktestResult(data as BacktestResult);
        await loadBacktestArtifacts(truthLane);
        toast.success("Backtest completed successfully");
      } catch (err) {
        setBacktestResult(null);
        setBacktestReport(null);
        setMetricTruthReport(null);
        setComparisonReport(null);
        setArtifactNotice(err instanceof Error ? err.message : "unknown error");
        toast.error(`Backtest failed: ${err instanceof Error ? err.message : "unknown error"}`);
      } finally {
        setBacktestRunning(false);
      }
    });
  };

  return (
    <div className="px-4 md:px-8 py-6 max-w-7xl mx-auto">
      {/* Sub-tabs */}
      <div
        className="flex items-center gap-0 border-b border-border mb-6 overflow-x-auto"
        role="tablist"
        aria-label="Strategy sub-tabs"
      >
        {SUB_TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeSubTab === tab.id;
          return (
            <button
              key={tab.id}
              role="tab"
              aria-selected={isActive}
              aria-controls={`tabpanel-${tab.id}`}
              id={`tab-${tab.id}`}
              onClick={() => setActiveSubTab(tab.id)}
              className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium uppercase tracking-wide transition-all border-b-2 whitespace-nowrap ${
                isActive
                  ? "text-text-0 border-accent"
                  : "text-text-2 border-transparent hover:text-text-1"
              }`}
            >
              <Icon size={14} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {activeSubTab === "brain" && (
        <div role="tabpanel" id="tabpanel-brain" aria-labelledby="tab-brain">
          <BrainTab
            profile={profile}
            profileType={profileType}
            onProfileTypeChange={setProfileType}
            getVal={getVal}
            setVal={setVal}
            edits={edits}
            saving={saving}
            saveNote={saveNote}
            setSaveNote={setSaveNote}
            onSave={handleSave}
            changelog={changelog}
          />
        </div>
      )}

      {activeSubTab === "optimizer" && (
        <div role="tabpanel" id="tabpanel-optimizer" aria-labelledby="tab-optimizer">
          <OptimizerTab
            backtestYears={backtestYears}
            setBacktestYears={setBacktestYears}
            ivAdj={ivAdj}
            setIvAdj={setIvAdj}
            truthLane={truthLane}
            setTruthLane={setTruthLane}
            pricingLane={pricingLane}
            setPricingLane={setPricingLane}
            running={backtestRunning}
            onRun={runBacktest}
            result={backtestResult}
            report={backtestReport}
            metricTruthReport={metricTruthReport}
            comparisonReport={comparisonReport}
            artifactNotice={artifactNotice}
          />
        </div>
      )}

      {activeSubTab === "daytrading" && (
        <div role="tabpanel" id="tabpanel-daytrading" aria-labelledby="tab-daytrading">
          <DayTradingLab />
        </div>
      )}
    </div>
  );
}

// ── Slider component ─────────────────────────────────────────────────────────

function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  suffix = "",
  help,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  suffix?: string;
  help?: string;
}) {
  const id = useId();
  const sliderId = `slider-${id}`;

  return (
    <div className="mb-3" title={help}>
      <div className="flex justify-between items-center mb-1">
        <label htmlFor={sliderId} className="text-xs text-text-2">
          {label}
        </label>
        <span className="text-xs font-mono text-text-0">
          {value}
          {suffix}
        </span>
      </div>
      <input
        id={sliderId}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        aria-label={label}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full h-1.5 bg-border rounded-full appearance-none cursor-pointer accent-accent"
      />
    </div>
  );
}

// ── Loading Skeleton ─────────────────────────────────────────────────────────

function ProfileSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-pulse">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="bg-bg-2 border border-border rounded-lg p-4 space-y-3">
          <div className="h-4 w-40 bg-bg-3 rounded" />
          <div className="space-y-2">
            {[...Array(4)].map((_, j) => (
              <div key={j} className="h-6 bg-bg-3 rounded" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Brain Tab ────────────────────────────────────────────────────────────────

function BrainTab({
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
}: {
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
}) {
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
      {/* Profile toggle */}
      <div className="flex gap-2">
        {(["equity", "index"] as const).map((t) => (
          <Button
            key={t}
            variant={profileType === t ? "primary" : "secondary"}
            onClick={() => onProfileTypeChange(t)}
          >
            {t === "equity" ? (
              <>
                <span aria-hidden="true">📈</span> Equity (Single Stocks)
              </>
            ) : (
              <>
                <span aria-hidden="true">📊</span> Index (ETFs)
              </>
            )}
          </Button>
        ))}
      </div>

      {!profile ? (
        <ProfileSkeleton />
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Left column */}
          <div className="space-y-4">
            {/* Direction Score Weights */}
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Direction Score Weights</div>
              <Slider label="Tech setup" value={getVal("direction_score_weights", "tech", 0.55) as number} min={0.10} max={0.80} step={0.05} onChange={(v) => setVal("direction_score_weights", "tech", v)} />
              <Slider label="SPY regime" value={getVal("direction_score_weights", "regime", 0.30) as number} min={0.05} max={0.60} step={0.05} onChange={(v) => setVal("direction_score_weights", "regime", v)} />
              <Slider label="Momentum" value={getVal("direction_score_weights", "momentum", 0.15) as number} min={0.00} max={0.40} step={0.05} onChange={(v) => setVal("direction_score_weights", "momentum", v)} />

              <div className="section-header">RSI Overextension</div>
              <Slider label="Severe threshold" value={getVal("rsi_overextension", "severe_threshold", 72) as number} min={60} max={80} step={1} onChange={(v) => setVal("rsi_overextension", "severe_threshold", v)} />
              <Slider label="Moderate threshold" value={getVal("rsi_overextension", "moderate_threshold", 68) as number} min={55} max={75} step={1} onChange={(v) => setVal("rsi_overextension", "moderate_threshold", v)} />
              <Slider label="Severe penalty" value={getVal("rsi_overextension", "severe_penalty", 15) as number} min={5} max={25} step={1} suffix=" pts" onChange={(v) => setVal("rsi_overextension", "severe_penalty", v)} />
              <Slider label="Moderate penalty" value={getVal("rsi_overextension", "moderate_penalty", 8) as number} min={1} max={15} step={1} suffix=" pts" onChange={(v) => setVal("rsi_overextension", "moderate_penalty", v)} />
            </div>

            {/* Quality Score Weights */}
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Quality Score Weights</div>
              <Slider label="IV Rank weight" value={getVal("quality_score_weights", "iv_rank", 0.40) as number} min={0.10} max={0.70} step={0.05} onChange={(v) => setVal("quality_score_weights", "iv_rank", v)} />
              <Slider label="Delta fit weight" value={getVal("quality_score_weights", "delta", 0.35) as number} min={0.10} max={0.60} step={0.05} onChange={(v) => setVal("quality_score_weights", "delta", v)} />
              <Slider label="DTE fit weight" value={getVal("quality_score_weights", "dte", 0.25) as number} min={0.05} max={0.50} step={0.05} onChange={(v) => setVal("quality_score_weights", "dte", v)} />

              <div className="section-header">Strike & Expiry Targets</div>
              <Slider label="Delta sweet spot" value={getVal("targets", "delta_optimal", 0.30) as number} min={0.15} max={0.55} step={0.05} onChange={(v) => setVal("targets", "delta_optimal", v)} />
              <Slider label="Delta window ±" value={getVal("targets", "delta_falloff", 0.20) as number} min={0.05} max={0.35} step={0.05} onChange={(v) => setVal("targets", "delta_falloff", v)} />
              <Slider label="DTE sweet spot" value={getVal("targets", "dte_optimal", 10) as number} min={5} max={35} step={1} suffix=" days" onChange={(v) => setVal("targets", "dte_optimal", v)} />
              <Slider label="DTE window ±" value={getVal("targets", "dte_falloff", 20) as number} min={3} max={15} step={1} suffix=" days" onChange={(v) => setVal("targets", "dte_falloff", v)} />
            </div>
          </div>

          {/* Right column */}
          <div className="space-y-4">
            {/* Entry Gates */}
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Entry Gates</div>
              <Slider label="Max IV rank" value={getVal("targets", "iv_percentile_max", 50) as number} min={20} max={80} step={5} onChange={(v) => setVal("targets", "iv_percentile_max", v)} />
              <Slider label="Min EV %" value={getVal("filters", "min_ev_return_pct", 10) as number} min={3} max={25} step={1} suffix="%" onChange={(v) => setVal("filters", "min_ev_return_pct", v)} />
              <Slider label="Max spread %" value={getVal("filters", "liquidity_spread_max_pct", 1.5) as number} min={0.5} max={5.0} step={0.5} suffix="%" onChange={(v) => setVal("filters", "liquidity_spread_max_pct", v)} />

              <div className="section-header">Momentum & Technical Gates</div>
              <Slider label="Min Direction Score" value={getVal("entry", "min_direction_score", 35) as number} min={20} max={65} step={5} onChange={(v) => setVal("entry", "min_direction_score", v)} />
              <Slider label="Min Tech Score" value={getVal("entry", "min_tech_score", 55) as number} min={30} max={75} step={5} onChange={(v) => setVal("entry", "min_tech_score", v)} />
              <Slider label="Momentum threshold" value={getVal("entry", "entry_momentum_pct", 0.50) as number} min={0.1} max={1.5} step={0.1} suffix="%" onChange={(v) => setVal("entry", "entry_momentum_pct", v)} />
            </div>

            {/* Exit Rules */}
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Exit Rules</div>
              <Slider label="Stop-loss" value={getVal("risk", "stop_loss_pct", 50) as number} min={20} max={80} step={5} suffix="%" onChange={(v) => setVal("risk", "stop_loss_pct", v)} />
              <Slider label="Profit target" value={getVal("risk", "profit_target_pct", 100) as number} min={50} max={200} step={10} suffix="%" onChange={(v) => setVal("risk", "profit_target_pct", v)} />
              <Slider label="Time exit" value={getVal("risk", "time_exit_pct", 50) as number} min={25} max={90} step={5} suffix="% DTE" onChange={(v) => setVal("risk", "time_exit_pct", v)} />
              <Slider label="Max drawdown" value={getVal("risk", "max_drawdown_pct", 15) as number} min={5} max={30} step={1} suffix="%" onChange={(v) => setVal("risk", "max_drawdown_pct", v)} />
            </div>

            {/* Defense & IV Filters */}
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Defense & IV Filters</div>
              <Slider label="VIX defense level" value={getVal("filters", "vix_defense_threshold", 25) as number} min={18} max={40} step={1} onChange={(v) => setVal("filters", "vix_defense_threshold", v)} />
              <Slider label="Defense size mult" value={getVal("filters", "defense_position_mult", 0.5) as number} min={0.2} max={0.9} step={0.1} suffix="x" onChange={(v) => setVal("filters", "defense_position_mult", v)} />
              <Slider label="IV crush σ" value={getVal("filters", "iv_crush_z_threshold", 2.0) as number} min={1.0} max={3.5} step={0.5} onChange={(v) => setVal("filters", "iv_crush_z_threshold", v)} />
              <Slider label="IV crush penalty" value={getVal("filters", "iv_crush_confidence_penalty", 20) as number} min={5} max={30} step={5} suffix=" pts" onChange={(v) => setVal("filters", "iv_crush_confidence_penalty", v)} />
            </div>

            {/* Position Sizing */}
            <div className="bg-bg-2 border border-border rounded-lg p-4">
              <div className="section-header mt-0">Position Sizing</div>
              <Slider label="Min position" value={getVal("risk", "min_position_pct", 7) as number} min={1} max={20} step={1} suffix="%" onChange={(v) => setVal("risk", "min_position_pct", v)} />
              <Slider label="Max position" value={getVal("risk", "max_position_pct", 40) as number} min={10} max={60} step={5} suffix="%" onChange={(v) => setVal("risk", "max_position_pct", v)} />
            </div>
          </div>
        </div>
      )}

      {/* Save bar */}
      {hasEdits && (
        <div className="sticky bottom-4 bg-bg-3 border border-accent/30 rounded-lg p-4 flex items-center gap-4 shadow-lg">
          <input
            type="text"
            value={saveNote}
            onChange={(e) => setSaveNote(e.target.value)}
            placeholder="Change note (optional)..."
            aria-label="Change note"
            className="flex-1 bg-bg-2 border border-border rounded px-3 py-2 text-sm text-text-0"
          />
          <Button
            variant="primary"
            onClick={onSave}
            loading={saving}
            icon={<Save size={14} />}
          >
            {saving ? "Saving..." : "Save Changes"}
          </Button>
        </div>
      )}

      {/* Version History */}
      <div className="bg-bg-2 border border-border rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <History size={14} className="text-text-3" />
          <span className="section-header mt-0 mb-0 border-0 pb-0">
            Version History
          </span>
        </div>
        {changelog.length === 0 ? (
          <p className="text-xs text-text-3">No changes recorded yet.</p>
        ) : (
          <FinTable
            data={reversedChangelog}
            maxHeight="200px"
          />
        )}
      </div>
    </div>
  );
}

// ── Optimizer Tab ────────────────────────────────────────────────────────────

function OptimizerTab({
  backtestYears,
  setBacktestYears,
  ivAdj,
  setIvAdj,
  truthLane,
  setTruthLane,
  pricingLane,
  setPricingLane,
  running,
  onRun,
  result,
  report,
  metricTruthReport,
  comparisonReport,
  artifactNotice,
}: {
  backtestYears: number;
  setBacktestYears: (v: number) => void;
  ivAdj: number;
  setIvAdj: (v: number) => void;
  truthLane: TruthLane;
  setTruthLane: (v: TruthLane) => void;
  pricingLane: BacktestPricingLane;
  setPricingLane: (v: BacktestPricingLane) => void;
  running: boolean;
  onRun: () => void;
  result: BacktestResult | null;
  report: BacktestReplayReport | null;
  metricTruthReport: MetricTruthReport | null;
  comparisonReport: TruthLaneComparisonReport | null;
  artifactNotice: string | null;
}) {
  const summaryMetrics = useMemo(() => {
    if (!result) return null;
    return {
      totalTrades: result.total_trades.toLocaleString(),
      winRate: `${result.win_rate_pct?.toFixed(1)}%`,
      fullHitRate: `${result.full_hit_rate_pct?.toFixed(1)}%`,
      directionalAccuracy: `${result.directional_accuracy_pct?.toFixed(1)}%`,
      profitFactor: result.profit_factor?.toFixed(2) || "\u2014",
      avgPnl: `${result.avg_pnl_pct?.toFixed(1)}%`,
      avgPicksPerDay: result.avg_picks_per_day?.toFixed(2) || "\u2014",
      sharpe: result.sharpe?.toFixed(2) || "\u2014",
      maxDrawdown: `${result.max_drawdown_pct?.toFixed(1)}%`,
      truthSource: fmtTruthSource(result.truth_source || result.source?.truth_source || report?.truth_source),
      quoteCoverage: result.quote_coverage_pct ?? report?.quote_coverage_pct ?? null,
      pricedTradeCount: result.priced_trade_count ?? report?.priced_trade_count ?? null,
      unpricedTradeCount: result.unpriced_trade_count ?? report?.unpriced_trade_count ?? null,
      entryQuoteTime: result.entry_quote_time_et ?? report?.entry_quote_time_et ?? null,
      exitQuoteTime: result.exit_quote_time_et ?? report?.exit_quote_time_et ?? null,
      promotionStatus: String(result.source?.promotion_status || report?.source?.promotion_status || "block").toUpperCase(),
    };
  }, [report, result]);

  const truthBandRows = useMemo(() => {
    if (!metricTruthReport?.metric_buckets?.direction_score) return [];
    return metricTruthReport.metric_buckets.direction_score
      .filter((bucket) => bucket.trades > 0)
      .map((bucket) => ({
        Band: bucket.label,
        Trades: bucket.trades.toLocaleString(),
        "Win Rate": `${bucket.win_rate_pct.toFixed(1)}%`,
        "Dir Accuracy": `${bucket.directional_accuracy_pct.toFixed(1)}%`,
        "Profit Factor": bucket.profit_factor.toFixed(2),
        "Avg P&L": `${bucket.avg_pnl_pct >= 0 ? "+" : ""}${bucket.avg_pnl_pct.toFixed(2)}%`,
        "Cal Gap": bucket.calibration_gap_pct == null
          ? "—"
          : `${bucket.calibration_gap_pct >= 0 ? "+" : ""}${bucket.calibration_gap_pct.toFixed(1)} pts`,
      }));
  }, [metricTruthReport]);

  const tradeRows = useMemo(() => {
    if (!result?.trades) return [];
    return result.trades.map((t) => ({
      Date: t.date,
      Ticker: t.ticker,
      Type: t.type === "call" ? "\u25B2 CALL" : "\u25BC PUT",
      Sector: t.sector || "\u2014",
      "Dir Score": t.direction_score?.toFixed(0) || "\u2014",
      Quality: t.quality_score?.toFixed(0) || "\u2014",
      Tech: t.tech_score?.toFixed(0) || "\u2014",
      EV: t.ev ? `${t.ev.toFixed(0)}%` : "\u2014",
      "Target Move": t.target_move_pct !== undefined ? `${t.target_move_pct.toFixed(1)}%` : "\u2014",
      Strike: `$${t.strike?.toFixed(0)}`,
      "Entry $": `$${t.entry_px?.toFixed(2)}`,
      "Exit $": `$${t.exit_px?.toFixed(2)}`,
      "P&L %": `${t.pnl_pct >= 0 ? "+" : ""}${t.pnl_pct?.toFixed(1)}%`,
      Outcome: t.prediction_outcome || "\u2014",
      Exit: t.exit_reason || "\u2014",
    }));
  }, [result]);

  return (
    <div className="space-y-6">
      {/* Config */}
      <div className="bg-bg-2 border border-border rounded-lg p-4">
        <div className="section-header mt-0">Backtest Configuration</div>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="text-xs text-text-2 block mb-1">
              Validation lane
            </label>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant={truthLane === "historical_imported_daily" ? "primary" : "secondary"}
                onClick={() => setTruthLane("historical_imported_daily")}
              >
                Imported daily
              </Button>
              <Button
                size="sm"
                variant={truthLane === "historical_imported" ? "primary" : "secondary"}
                onClick={() => setTruthLane("historical_imported")}
              >
                Imported intraday
              </Button>
              <Button
                size="sm"
                variant={truthLane === "synthetic" ? "primary" : "secondary"}
                onClick={() => setTruthLane("synthetic")}
              >
                Synthetic research
              </Button>
            </div>
            <div className="text-xs text-text-3 mt-2">
              {truthLane === "historical_imported"
                ? "Higher-trust intraday validation lane. It prices model-targeted contracts with imported historical intraday quotes and leaves missing quotes unpriced."
                : truthLane === "historical_imported_daily"
                ? "Free daily validation lane. It prices model-targeted contracts with imported end-of-day quotes, which is stronger than synthetic but still not morning-fill proof."
                : "Fast research lane. Useful for ranking ideas, not for proving live options profitability."}
            </div>
          </div>
          <div>
            <label className="text-xs text-text-2 block mb-1">
              Years of history
            </label>
            <input
              type="range"
              min={2}
              max={7}
              step={1}
              value={backtestYears}
              onChange={(e) => setBacktestYears(Number(e.target.value))}
              className="w-full accent-accent"
            />
            <div className="text-xs font-mono text-text-0 mt-1">
              {backtestYears} years
            </div>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div>
            <label className="text-xs text-text-2 block mb-1">
              Synthetic pricing lane
            </label>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant={pricingLane === "pessimistic" ? "primary" : "secondary"}
                onClick={() => setPricingLane("pessimistic")}
              >
                Pessimistic
              </Button>
              <Button
                size="sm"
                variant={pricingLane === "mid" ? "primary" : "secondary"}
                onClick={() => setPricingLane("mid")}
              >
                Mid
              </Button>
            </div>
            <div className="text-xs text-text-3 mt-2">
              {truthLane === "synthetic"
                ? "Choose which synthetic replay lane to run for research-only comparisons."
                : "Synthetic pricing is ignored for imported validation runs."}
            </div>
          </div>
          <div>
            <label className="text-xs text-text-2 block mb-1">
              IV premium adjustment
            </label>
            <input
              type="range"
              min={1.0}
              max={1.5}
              step={0.05}
              value={ivAdj}
              onChange={(e) => setIvAdj(Number(e.target.value))}
              className="w-full accent-accent"
              disabled={truthLane !== "synthetic"}
            />
            <div className="text-xs font-mono text-text-0 mt-1">
              {ivAdj.toFixed(2)}x
            </div>
          </div>
        </div>
        <Button
          variant="primary"
          onClick={onRun}
          loading={running}
          icon={running ? undefined : <Play size={14} />}
        >
          {running ? "Running Backtest..." : "Run Historical Backtest"}
        </Button>
      </div>

      {!summaryMetrics && artifactNotice && (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4 text-sm text-amber-100">
          {artifactNotice}
        </div>
      )}

      {/* Results */}
      {summaryMetrics && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <MetricCard label="Total Trades" value={summaryMetrics.totalTrades} />
            <MetricCard label="Win Rate" value={summaryMetrics.winRate} />
            <MetricCard label="Full Hit Rate" value={summaryMetrics.fullHitRate} />
            <MetricCard label="Directional Accuracy" value={summaryMetrics.directionalAccuracy} />
            <MetricCard label="Profit Factor" value={summaryMetrics.profitFactor} />
            <MetricCard label="Avg P&L/Trade" value={summaryMetrics.avgPnl} />
            <MetricCard label="Avg Picks/Day" value={summaryMetrics.avgPicksPerDay} />
            <MetricCard label="Sharpe" value={summaryMetrics.sharpe} />
            <MetricCard label="Max Drawdown" value={summaryMetrics.maxDrawdown} />
            <MetricCard label="Truth Source" value={summaryMetrics.truthSource} />
            <MetricCard
              label="Quote Coverage"
              value={summaryMetrics.quoteCoverage == null ? "\u2014" : `${summaryMetrics.quoteCoverage.toFixed(1)}%`}
            />
            <MetricCard label="Promotion" value={summaryMetrics.promotionStatus} />
            <MetricCard
              label="Priced / Unpriced"
              value={
                summaryMetrics.pricedTradeCount != null || summaryMetrics.unpricedTradeCount != null
                  ? `${summaryMetrics.pricedTradeCount ?? 0} / ${summaryMetrics.unpricedTradeCount ?? 0}`
                  : "\u2014"
              }
            />
          </div>

          <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-2">
            <div className="section-header mt-0">Validation Lane</div>
            <div className="text-sm text-text-2">
              {summaryMetrics.truthSource === "Imported historical validation"
                ? "This replay uses imported intraday historical option quotes for pricing. It is the strongest lane in the app today, but contract targeting is still replay-model-derived rather than a perfect reconstruction of archived live picks."
                : summaryMetrics.truthSource === "Imported daily validation"
                ? "This replay uses imported daily end-of-day option quotes for pricing. It is materially better than synthetic, but still not a proof of morning entry quality."
                : "This replay is synthetic research-only. It is useful for ranking hypotheses, but not for proving profitability."}
            </div>
            <div className="text-xs uppercase tracking-wide text-text-3">
              {result?.truth_source || report?.truth_source ? `Truth ${summaryMetrics.truthSource}` : "Truth Synthetic research-only"}
              {summaryMetrics.quoteCoverage != null ? ` | Coverage ${summaryMetrics.quoteCoverage.toFixed(1)}%` : ""}
              {result?.priced_trade_count != null || result?.unpriced_trade_count != null
                ? ` | Priced ${result?.priced_trade_count ?? 0} / Unpriced ${result?.unpriced_trade_count ?? 0}`
                : ""}
            </div>
            {(summaryMetrics.entryQuoteTime || summaryMetrics.exitQuoteTime) && (
              <div className="text-xs text-text-3">
                Entry window {summaryMetrics.entryQuoteTime || "\u2014"}
                {summaryMetrics.exitQuoteTime ? ` | Exit mark ${summaryMetrics.exitQuoteTime}` : ""}
              </div>
            )}
          </div>

          {metricTruthReport && (
            <div className="grid grid-cols-1 xl:grid-cols-[1.1fr_0.9fr] gap-6">
              <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
                <div>
                  <div className="section-header mt-0">Metric Truth Audit</div>
                  <p className="text-sm text-text-2">
                    This checks whether the current score stack is actually aligned with profitable outcomes.
                    Synthetic research helps us rank ideas, but imported validation is what should
                    carry the strongest truth claim.
                  </p>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                  <MetricCard
                    label="Truth Trades"
                    value={metricTruthReport.source.total_trades.toLocaleString()}
                  />
                  <MetricCard
                    label="Bucket Size"
                    value={`${metricTruthReport.quality_bar.bucket_size} pts`}
                  />
                  <MetricCard
                    label="Min Trades"
                    value={metricTruthReport.quality_bar.min_trades.toLocaleString()}
                  />
                  <MetricCard
                    label="Best Dir Floor"
                    value={
                      metricTruthReport.metric_health?.direction_score?.best_floor
                        ? `>=${metricTruthReport.metric_health.direction_score.best_floor.floor}`
                        : "None"
                    }
                  />
                  <MetricCard
                    label="Truth Source"
                    value={fmtTruthSource(metricTruthReport.source.truth_source)}
                  />
                </div>

                <div className="text-xs uppercase tracking-wide text-text-3">
                  {metricTruthReport.source.truth_source
                    ? fmtTruthSource(metricTruthReport.source.truth_source)
                    : "Synthetic research-only"}
                  {metricTruthReport.source.quote_coverage_pct != null
                    ? ` | Coverage ${metricTruthReport.source.quote_coverage_pct.toFixed(1)}%`
                    : ""}
                  {metricTruthReport.source.priced_trade_count != null || metricTruthReport.source.unpriced_trade_count != null
                    ? ` | Priced ${metricTruthReport.source.priced_trade_count ?? 0} / Unpriced ${metricTruthReport.source.unpriced_trade_count ?? 0}`
                    : ""}
                </div>
                {(metricTruthReport.source.entry_quote_time_et || metricTruthReport.source.exit_quote_time_et) && (
                  <div className="text-xs text-text-3">
                    Entry window {metricTruthReport.source.entry_quote_time_et || "\u2014"}
                    {metricTruthReport.source.exit_quote_time_et ? ` | Exit mark ${metricTruthReport.source.exit_quote_time_et}` : ""}
                  </div>
                )}

                {truthBandRows.length > 0 && (
                  <div>
                    <div className="section-header">Direction Score Bands</div>
                    <FinTable
                      data={truthBandRows}
                      pnlCols={["Avg P&L"]}
                      monoCols={["Trades", "Win Rate", "Dir Accuracy", "Profit Factor", "Avg P&L", "Cal Gap"]}
                      maxHeight="320px"
                    />
                  </div>
                )}
              </div>

              <div className="space-y-4">
                <div className="bg-bg-2 border border-border rounded-lg p-4">
                  <div className="section-header mt-0">Risk Flags</div>
                  {metricTruthReport.risk_flags.length > 0 ? (
                    <ul className="space-y-2 text-sm text-rose-300">
                      {metricTruthReport.risk_flags.map((flag) => (
                        <li key={flag} className="border border-rose-500/30 bg-rose-500/10 rounded-md px-3 py-2">
                          {flag}
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-sm text-text-2">No audit flags on the current replay.</p>
                  )}
                </div>

                <div className="bg-bg-2 border border-border rounded-lg p-4">
                  <div className="section-header mt-0">Recommendations</div>
                  <ul className="space-y-2 text-sm text-text-1">
                    {metricTruthReport.recommendations.map((item) => (
                      <li key={item} className="border border-border rounded-md px-3 py-2 bg-bg-3/40">
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          )}

          {report && (
            <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="section-header mt-0">Replay Report</div>
                  <p className="text-sm text-text-2">
                    A grouped replay view of the current options lane. Truth-source, coverage, and pricing metadata are shown here explicitly so we do not over-read synthetic research as validated profitability.
                  </p>
                </div>
                <div className="text-xs uppercase tracking-wide text-text-3 text-right">
                  {fmtTruthSource(report.truth_source || report.source?.truth_source)}
                  {report.quote_coverage_pct != null ? ` | Coverage ${report.quote_coverage_pct.toFixed(1)}%` : ""}
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <MetricCard label="Grouped Trades" value={report.source.total_trades?.toLocaleString() || "—"} />
                <MetricCard label="Truth Source" value={fmtTruthSource(report.truth_source || report.source?.truth_source)} />
                <MetricCard
                  label="Priced / Unpriced"
                  value={
                    report.priced_trade_count != null || report.unpriced_trade_count != null
                      ? `${report.priced_trade_count ?? 0} / ${report.unpriced_trade_count ?? 0}`
                      : "—"
                  }
                />
                <MetricCard
                  label="Coverage"
                  value={report.quote_coverage_pct != null ? `${report.quote_coverage_pct.toFixed(1)}%` : "—"}
                />
              </div>

              {(report.entry_quote_time_et || report.exit_quote_time_et) && (
                <div className="text-xs text-text-3">
                  Entry window {report.entry_quote_time_et || "—"}
                  {report.exit_quote_time_et ? ` | Exit mark ${report.exit_quote_time_et}` : ""}
                </div>
              )}
            </div>
          )}

          {comparisonReport && (
            <div className="bg-bg-2 border border-border rounded-lg p-4 space-y-4">
              <div>
                <div className="section-header mt-0">Synthetic vs Imported Comparison</div>
                <p className="text-sm text-text-2">
                  This disagreement view compares the latest synthetic research run with the selected imported quote-validation lane so we can see how much the research lane drifts once real option quotes are used.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {(
                  [
                    ["Synthetic", comparisonReport.synthetic],
                    ["Imported", comparisonReport.imported],
                  ] as Array<[string, TruthLaneSummary | null | undefined]>
                ).map(([label, lane]) => (
                  <div key={label} className="bg-bg-3 border border-border rounded-lg p-3 space-y-1">
                    <div className="text-xs uppercase tracking-wide text-text-3">{label}</div>
                    <div className="text-sm text-text-1">
                      {lane ? fmtTruthSource(lane.truth_source) : "—"}
                    </div>
                    <div className="text-xs text-text-3">
                      Trades {lane?.total_trades != null ? lane.total_trades : "—"}
                      {lane?.profit_factor != null ? ` · PF ${lane.profit_factor.toFixed(2)}` : ""}
                      {lane?.avg_pnl_pct != null ? ` · Avg ${lane.avg_pnl_pct.toFixed(2)}%` : ""}
                      {lane?.directional_accuracy_pct != null ? ` · Dir ${lane.directional_accuracy_pct.toFixed(1)}%` : ""}
                    </div>
                    <div className="text-xs text-text-3">
                      Coverage {lane?.quote_coverage_pct != null ? `${lane.quote_coverage_pct.toFixed(1)}%` : "—"}
                      {lane?.promotion_status ? ` · Policy ${String(lane.promotion_status).toUpperCase()}` : ""}
                    </div>
                  </div>
                ))}
              </div>

              {comparisonReport.deltas && (
                <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                  <MetricCard label="Trade Delta" value={String(comparisonReport.deltas.total_trades)} />
                  <MetricCard label="PF Delta" value={comparisonReport.deltas.profit_factor.toFixed(2)} />
                  <MetricCard label="Avg P&L Delta" value={`${comparisonReport.deltas.avg_pnl_pct.toFixed(2)}%`} />
                  <MetricCard label="Dir Delta" value={`${comparisonReport.deltas.directional_accuracy_pct.toFixed(1)}%`} />
                  <MetricCard label="Coverage Delta" value={`${comparisonReport.deltas.quote_coverage_pct.toFixed(1)}%`} />
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="bg-bg-3 border border-border rounded-lg p-3">
                  <div className="text-[11px] uppercase tracking-wide text-text-3">Coverage Notes</div>
                  <div className="text-sm text-text-1 mt-1">
                    Matching priced trades {comparisonReport.matching_priced_trade_count ?? 0}
                    {" "}&middot; Unsupported by imported lane {comparisonReport.unsupported_by_import_count ?? 0}
                  </div>
                </div>
                <div className="bg-bg-3 border border-border rounded-lg p-3">
                  <div className="text-[11px] uppercase tracking-wide text-text-3">Warnings</div>
                  <div className="text-sm text-text-1 mt-1">
                    {(comparisonReport.warnings?.length ? comparisonReport.warnings : comparisonReport.notes || ["No comparison warnings."]).join(" ")}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Trades table */}
          {tradeRows.length > 0 && (
            <div>
              <div className="section-header">
                All Trades ({tradeRows.length})
              </div>
              <FinTable
                data={tradeRows}
                pnlCols={["P&L %"]}
                badgeCol="Type"
                monoCols={["Dir Score", "Quality", "Tech", "Target Move", "Strike", "Entry $", "Exit $"]}
                maxHeight="600px"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
