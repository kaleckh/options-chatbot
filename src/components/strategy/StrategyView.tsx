"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { useSubmitGuard } from "@/lib/hooks";
import { strategyLabMutationHeaders } from "@/lib/strategy-lab/replayIntent";
import type {
  BacktestPricingLane,
  BacktestReplayReport,
  BacktestResult,
  MetricTruthReport,
  StrategyProfile,
  TruthLane,
  TruthLaneComparisonReport,
} from "@/lib/types";
import { BrainTab } from "@/components/strategy/BrainTab";
import { OptimizerTab } from "@/components/strategy/OptimizerTab";
import { SUB_TABS, hasError } from "@/components/strategy/shared";

type ProfileType = "equity" | "index";
type ProfilesByType = Record<ProfileType, StrategyProfile>;
type SubTabId = (typeof SUB_TABS)[number]["id"];

export default function StrategyView() {
  const toast = useToast();
  const saveGuard = useSubmitGuard();
  const backtestGuard = useSubmitGuard();

  const [activeSubTab, setActiveSubTab] = useState<SubTabId>("optimizer");
  const [profileType, setProfileType] = useState<ProfileType>("equity");
  const [profiles, setProfiles] = useState<ProfilesByType | null>(null);
  const [changelog, setChangelog] = useState<Record<string, unknown>[]>([]);
  const [profilesLoaded, setProfilesLoaded] = useState(false);
  const [changelogLoadedProfile, setChangelogLoadedProfile] = useState<ProfileType | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveNote, setSaveNote] = useState("");
  const [edits, setEdits] = useState<Record<string, Record<string, unknown>>>({});

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
  const artifactRequestIdRef = useRef(0);
  const backtestRequestIdRef = useRef(0);
  const truthLaneRef = useRef(truthLane);

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
    const requestedProfile = profileType;
    setChangelog([]);
    setChangelogLoadedProfile(null);
    try {
      const response = await fetch(`/api/changelog?profile=${requestedProfile}`);
      if (!response.ok) {
        throw new Error(`Failed to load ${requestedProfile} changelog (${response.status})`);
      }
      setChangelog(await response.json());
      setChangelogLoadedProfile(requestedProfile);
    } catch (err) {
      setChangelog([]);
      setChangelogLoadedProfile(requestedProfile);
      toast.error(`Failed to load changelog: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }, [profileType, toast]);

  useEffect(() => {
    truthLaneRef.current = truthLane;
  }, [truthLane]);

  const loadBacktestArtifacts = useCallback(async (lane: TruthLane) => {
    const requestId = ++artifactRequestIdRef.current;
    const isCurrentRequest = () =>
      requestId === artifactRequestIdRef.current && lane === truthLaneRef.current;

    try {
      const params = new URLSearchParams({
        truth_lane: lane,
        min_trades: "20",
        bucket_size: "10",
      });
      const response = await fetch(`/api/backtest/summary?${params.toString()}`);
      const payload = await response.json().catch(() => ({}));
      if (!isCurrentRequest()) return;
      if (!response.ok || hasError(payload)) {
        throw new Error(hasError(payload) ? payload.error : `Failed to load ${lane} backtest summary.`);
      }

      const summary = payload as Record<string, unknown>;
      const lastData = summary.last;
      const reportData = summary.report;
      const truthData = summary.metricTruth;
      const comparisonData = summary.comparison;

      const primaryError =
        hasError(lastData)
          ? lastData.error
          : hasError(reportData)
            ? reportData.error
            : hasError(truthData)
              ? truthData.error
              : hasError(comparisonData)
                ? comparisonData.error
                : null;

      setBacktestResult(hasError(lastData) ? null : (lastData as BacktestResult | null));
      setBacktestReport(hasError(reportData) ? null : (reportData as BacktestReplayReport | null));
      setMetricTruthReport(hasError(truthData) ? null : (truthData as MetricTruthReport | null));
      setComparisonReport(
        hasError(comparisonData) ? null : ((comparisonData ?? null) as TruthLaneComparisonReport | null)
      );
      setArtifactNotice(primaryError);
    } catch (err) {
      if (!isCurrentRequest()) return;
      setBacktestResult(null);
      setBacktestReport(null);
      setMetricTruthReport(null);
      setComparisonReport(null);
      setArtifactNotice(err instanceof Error ? err.message : "unknown error");
      toast.error(`Failed to load backtest artifacts: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }, [toast]);

  useEffect(() => {
    if (activeSubTab !== "brain") return;
    if (!profilesLoaded) {
      void fetchProfiles();
    }
    if (changelogLoadedProfile !== profileType) {
      void fetchChangelog();
    }
  }, [activeSubTab, changelogLoadedProfile, fetchChangelog, fetchProfiles, profileType, profilesLoaded]);

  useEffect(() => {
    if (activeSubTab !== "optimizer") return;
    void loadBacktestArtifacts(truthLane);
  }, [activeSubTab, loadBacktestArtifacts, truthLane]);

  const profile = profiles?.[profileType];

  const getVal = (section: string, key: string, fallback: number | boolean): number | boolean => {
    if (edits[section]?.[key] !== undefined) return edits[section][key] as number | boolean;
    const sectionData = profile?.[section as keyof StrategyProfile] as Record<string, unknown> | undefined;
    if (sectionData?.[key] !== undefined) return sectionData[key] as number | boolean;
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
        const response = await fetch("/api/profile", {
          method: "PUT",
          headers: strategyLabMutationHeaders("save_strategy_profile"),
          body: JSON.stringify({
            type: profileType,
            updates: edits,
            note: saveNote || `${profileType} profile updated`,
          }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || hasError(payload)) {
          throw new Error(hasError(payload) ? payload.error : `Failed to save profile (${response.status})`);
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
      const lane = truthLane;
      const requestId = ++backtestRequestIdRef.current;
      const isCurrentRequest = () =>
        requestId === backtestRequestIdRef.current && lane === truthLaneRef.current;
      setBacktestRunning(true);
      try {
        const response = await fetch("/api/backtest", {
          method: "POST",
          headers: strategyLabMutationHeaders("run_replay_backtest"),
          body: JSON.stringify({
            lookback_years: backtestYears,
            iv_adj: ivAdj,
            truth_lane: lane,
            pricing_lane: lane === "synthetic" ? pricingLane : undefined,
          }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!isCurrentRequest()) return;
        if (!response.ok || hasError(payload)) {
          throw new Error(hasError(payload) ? payload.error : `Backtest failed with status ${response.status}`);
        }

        setBacktestResult(payload as BacktestResult);
        await loadBacktestArtifacts(lane);
        if (!isCurrentRequest()) return;
        toast.success("Backtest completed successfully");
      } catch (err) {
        if (!isCurrentRequest()) return;
        setBacktestResult(null);
        setBacktestReport(null);
        setMetricTruthReport(null);
        setComparisonReport(null);
        setArtifactNotice(err instanceof Error ? err.message : "unknown error");
        toast.error(`Backtest failed: ${err instanceof Error ? err.message : "unknown error"}`);
      } finally {
        if (requestId === backtestRequestIdRef.current) {
          setBacktestRunning(false);
        }
      }
    });
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-5 md:px-8">
      <div className="mb-4">
        <h1 className="text-xl font-semibold text-text-0">Strategy Lab</h1>
        <p className="mt-1 text-sm text-text-2">
          Start with replay evidence, then edit policy settings only when the proof layer supports it.
        </p>
      </div>

      <div className="mb-6 flex items-center gap-1 overflow-x-auto rounded-lg border border-border bg-bg-2 p-1" role="tablist" aria-label="Strategy lab views">
        {SUB_TABS.map((tab) => {
          const Icon = tab.icon;
          const active = activeSubTab === tab.id;
          return (
            <button
              key={tab.id}
              id={`${tab.id}-strategy-tab`}
              type="button"
              role="tab"
              aria-selected={active}
              aria-controls={`${tab.id}-strategy-panel`}
              tabIndex={active ? 0 : -1}
              onClick={() => setActiveSubTab(tab.id)}
              onKeyDown={(event) => {
                const tabIds = SUB_TABS.map((item) => item.id);
                const currentIndex = tabIds.indexOf(activeSubTab);
                let nextIndex: number | null = null;
                if (event.key === "ArrowRight") nextIndex = (currentIndex + 1) % tabIds.length;
                if (event.key === "ArrowLeft") nextIndex = (currentIndex - 1 + tabIds.length) % tabIds.length;
                if (event.key === "Home") nextIndex = 0;
                if (event.key === "End") nextIndex = tabIds.length - 1;
                if (nextIndex == null) return;
                event.preventDefault();
                setActiveSubTab(tabIds[nextIndex]);
                const buttons = event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
                buttons?.[nextIndex]?.focus();
              }}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-all whitespace-nowrap ${
                active
                  ? "bg-accent-dim text-accent"
                  : "text-text-2 hover:bg-bg-3 hover:text-text-0"
              }`}
            >
              <span className="inline-flex items-center gap-2">
                <Icon size={16} aria-hidden="true" />
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>

      <div id={`${activeSubTab}-strategy-panel`} role="tabpanel" aria-labelledby={`${activeSubTab}-strategy-tab`}>
        {activeSubTab === "brain" ? (
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
        ) : (
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
        )}
      </div>
    </div>
  );
}
