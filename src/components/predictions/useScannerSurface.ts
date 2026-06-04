"use client";

import { useCallback, useRef, useState } from "react";
import { useToast } from "@/components/ui/Toast";
import { fetchWithTimeout, readJsonResponseOrThrow } from "@/lib/client-json";
import type {
  ExposureSnapshot,
  ForwardEvidenceReport,
  LiveTradePolicy,
  OptionsProfitStatus,
  PlaybookExitAudit,
  ScanPick,
  ScanPlaybook,
} from "@/lib/types";

type LiveScanResponse = {
  picks?: ScanPick[];
  policy?: LiveTradePolicy | null;
  policy_error?: string | null;
  playbook_exit_audit?: PlaybookExitAudit | null;
  policy_decision_counts?: Record<string, number> | null;
  guardrail_decision_counts?: Record<string, number> | null;
  candidate_count?: number;
  playbooks?: ScanPlaybook[];
  exposure_snapshot?: ExposureSnapshot | null;
};

export function useScannerSurface() {
  const toast = useToast();
  const [scanPicks, setScanPicks] = useState<ScanPick[]>([]);
  const [scanPolicy, setScanPolicy] = useState<LiveTradePolicy | null>(null);
  const [scanPolicyError, setScanPolicyError] = useState<string | null>(null);
  const [scanDecisionCounts, setScanDecisionCounts] = useState<Record<string, number> | null>(null);
  const [guardrailDecisionCounts, setGuardrailDecisionCounts] = useState<Record<string, number> | null>(null);
  const [scanExitAudit, setScanExitAudit] = useState<PlaybookExitAudit | null>(null);
  const [scanCandidateCount, setScanCandidateCount] = useState(0);
  const [forwardEvidence, setForwardEvidence] = useState<ForwardEvidenceReport | null>(null);
  const [optionsProfitStatus, setOptionsProfitStatus] = useState<OptionsProfitStatus | null>(null);
  const [truthHealthError, setTruthHealthError] = useState<string | null>(null);
  const [useRecommendedPolicy, setUseRecommendedPolicy] = useState(false);
  const [scanPlaybook, setScanPlaybook] = useState<string>("bullish_pullback_observation");
  const [showBlockedIdeas, setShowBlockedIdeas] = useState(false);
  const [availablePlaybooks, setAvailablePlaybooks] = useState<ScanPlaybook[]>([]);
  const [exposureSnapshot, setExposureSnapshot] = useState<ExposureSnapshot | null>(null);
  const [scanLoading, setScanLoading] = useState(false);
  const scanRequestIdRef = useRef(0);
  const truthHealthRequestIdRef = useRef(0);

  const fetchScanner = useCallback(async (showToast = false) => {
    const requestId = ++scanRequestIdRef.current;
    const isCurrentRequest = () => requestId === scanRequestIdRef.current;
    setScanLoading(true);
    try {
      const res = await fetchWithTimeout("/api/scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          n_picks: 2,
          use_recommended_policy: useRecommendedPolicy,
          playbook: scanPlaybook,
          include_blocked_policy_picks: showBlockedIdeas,
          include_blocked_guardrail_picks: showBlockedIdeas,
          enforce_portfolio_caps: true,
        }),
      }, "Live scan");
      const data = await readJsonResponseOrThrow<LiveScanResponse>(res, "Live scan");
      if (!isCurrentRequest()) return;
      setScanPicks(data.picks || []);
      setScanPolicy(data.policy || null);
      setScanPolicyError(data.policy_error || null);
      setScanExitAudit(data.playbook_exit_audit || null);
      setScanDecisionCounts(data.policy_decision_counts || null);
      setGuardrailDecisionCounts(data.guardrail_decision_counts || null);
      setScanCandidateCount(Number(data.candidate_count || (data.picks || []).length || 0));
      setAvailablePlaybooks(data.playbooks || []);
      setExposureSnapshot(data.exposure_snapshot || null);
    } catch (err) {
      if (!isCurrentRequest()) return;
      console.error("Failed to load scan picks:", err);
      const message = err instanceof Error ? err.message : "Failed to load scan picks.";
      setScanPicks([]);
      setScanPolicy(null);
      setScanPolicyError(message);
      setScanExitAudit(null);
      setScanDecisionCounts(null);
      setGuardrailDecisionCounts(null);
      setScanCandidateCount(0);
      setAvailablePlaybooks([]);
      setExposureSnapshot(null);
      if (showToast) {
        toast.error(message);
      }
    } finally {
      if (isCurrentRequest()) {
        setScanLoading(false);
      }
    }
  }, [showBlockedIdeas, toast, scanPlaybook, useRecommendedPolicy]);

  const fetchTruthHealth = useCallback(async (showToast = false) => {
    const requestId = ++truthHealthRequestIdRef.current;
    const isCurrentRequest = () => requestId === truthHealthRequestIdRef.current;
    try {
      const [forwardRes, statusRes] = await Promise.all([
        fetchWithTimeout("/api/backtest/forward-evidence", undefined, "Forward evidence report"),
        fetchWithTimeout("/api/options-profit/status", undefined, "Options profit status"),
      ]);
      const forwardData = await readJsonResponseOrThrow<ForwardEvidenceReport>(
        forwardRes,
        "Forward evidence report"
      );
      const statusData = await readJsonResponseOrThrow<OptionsProfitStatus>(
        statusRes,
        "Options profit status"
      );
      if (!isCurrentRequest()) return;
      setForwardEvidence((forwardData || null) as ForwardEvidenceReport | null);
      setOptionsProfitStatus((statusData || null) as OptionsProfitStatus | null);
      setTruthHealthError(null);
    } catch (err) {
      if (!isCurrentRequest()) return;
      console.error("Failed to load truth health:", err);
      const message = err instanceof Error ? err.message : "Failed to load truth health.";
      setForwardEvidence(null);
      setOptionsProfitStatus(null);
      setTruthHealthError(message);
      if (showToast) {
        toast.error(message);
      }
    }
  }, [toast]);

  const refreshScannerSurface = useCallback(async (showToast = false) => {
    await Promise.all([
      fetchScanner(showToast),
      fetchTruthHealth(showToast),
    ]);
  }, [fetchScanner, fetchTruthHealth]);

  return {
    scanPicks,
    scanPolicy,
    scanPolicyError,
    scanDecisionCounts,
    guardrailDecisionCounts,
    scanExitAudit,
    scanCandidateCount,
    forwardEvidence,
    optionsProfitStatus,
    truthHealthError,
    useRecommendedPolicy,
    setUseRecommendedPolicy,
    scanPlaybook,
    setScanPlaybook,
    showBlockedIdeas,
    setShowBlockedIdeas,
    availablePlaybooks,
    exposureSnapshot,
    scanLoading,
    fetchScanner,
    fetchTruthHealth,
    refreshScannerSurface,
  };
}
