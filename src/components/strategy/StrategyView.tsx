"use client";

import { useCallback, useEffect, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { useSubmitGuard } from "@/lib/hooks";
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

  const [activeSubTab, setActiveSubTab] = useState<SubTabId>("brain");
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
      const response = await fetch(`/api/changelog?profile=${profileType}`);
      if (!response.ok) return;
      setChangelog(await response.json());
      setChangelogLoadedProfile(profileType);
    } catch (err) {
      toast.error(`Failed to load changelog: ${err instanceof Error ? err.message : "unknown error"}`);
    }
  }, [profileType, toast]);

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
              : null;

      setBacktestResult(hasError(lastData) ? null : (lastData as BacktestResult | null));
      setBacktestReport(hasError(reportData) ? null : (reportData as BacktestReplayReport | null));
      setMetricTruthReport(hasError(truthData) ? null : (truthData as MetricTruthReport | null));
      setComparisonReport(
        hasError(comparisonData) ? null : ((comparisonData ?? null) as TruthLaneComparisonReport | null)
      );
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
          headers: { "Content-Type": "application/json" },
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
      setBacktestRunning(true);
      try {
        const response = await fetch("/api/backtest", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            lookback_years: backtestYears,
            iv_adj: ivAdj,
            truth_lane: truthLane,
            pricing_lane: truthLane === "synthetic" ? pricingLane : undefined,
          }),
        });
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || hasError(payload)) {
          throw new Error(hasError(payload) ? payload.error : `Backtest failed with status ${response.status}`);
        }

        setBacktestResult(payload as BacktestResult);
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
    <div className="mx-auto max-w-7xl px-4 py-6 md:px-8">
      <div className="mb-6 flex items-center gap-0 overflow-x-auto border-b border-border">
        {SUB_TABS.map((tab) => {
          const Icon = tab.icon;
          const active = activeSubTab === tab.id;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveSubTab(tab.id)}
              className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-all whitespace-nowrap ${
                active
                  ? "text-text-0 border-accent bg-bg-2/50"
                  : "text-text-3 border-transparent hover:text-text-2 hover:bg-bg-2/30"
              }`}
            >
              <span className="inline-flex items-center gap-2">
                <Icon size={16} />
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>

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
  );
}
