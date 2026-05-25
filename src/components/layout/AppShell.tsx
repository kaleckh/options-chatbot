"use client";

import { useCallback, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import { ToastProvider, useToast } from "@/components/ui/Toast";
import ErrorBoundary from "@/components/ui/ErrorBoundary";
import { MetricGridSkeleton } from "@/components/ui/Skeleton";

function LoadingSkeleton() {
  return (
    <div className="p-6">
      <MetricGridSkeleton count={5} />
    </div>
  );
}

const PredictionsView = dynamic(
  () => import("@/components/predictions/PredictionsView"),
  { loading: () => <LoadingSkeleton />, ssr: false }
);

const StrategyView = dynamic(
  () => import("@/components/strategy/StrategyView"),
  { loading: () => <LoadingSkeleton />, ssr: false }
);

function AppShellContent({ children }: { children: React.ReactNode }) {
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<string>("predictions");
  const [riskSettings, setRiskSettings] = useState<Record<string, unknown> | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const fetchRisk = useCallback(async () => {
    try {
      const res = await fetch("/api/risk-settings");
      const data = await res.json().catch(() => ({}));
      if (!res.ok || (data && typeof data === "object" && "error" in data)) {
        const message =
          data && typeof data === "object" && "error" in data
            ? String((data as { error?: unknown }).error)
            : `Risk settings request failed (${res.status})`;
        throw new Error(message);
      }
      setRiskSettings(data as Record<string, unknown>);
    } catch (error) {
      console.error("Could not load risk settings:", error);
      toast.error("Could not load risk settings.");
    }
  }, [toast]);

  useEffect(() => {
    void fetchRisk();
  }, [fetchRisk]);

  return (
    <>
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-2 focus:left-2 focus:px-4 focus:py-2 focus:bg-accent focus:text-white focus:rounded-md focus:text-sm"
      >
        Skip to main content
      </a>

      <div className="flex h-dvh overflow-hidden">
        <Sidebar
          activeTab={activeTab}
          onTabChange={setActiveTab}
          riskSettings={riskSettings}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />

        <div className="flex-1 flex flex-col overflow-hidden">
          <Header onMenuClick={() => setSidebarOpen((o) => !o)} />

          <main id="main-content" className="flex-1 overflow-hidden">
            <ErrorBoundary>
              {activeTab === "predictions" && (
                <div role="tabpanel" aria-label="Picks">
                  <PredictionsView />
                </div>
              )}

              {activeTab === "strategy" && (
                <div role="tabpanel" aria-label="Strategy Lab">
                  <StrategyView />
                </div>
              )}
            </ErrorBoundary>
          </main>
        </div>
      </div>

      {children}
    </>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      <AppShellContent>{children}</AppShellContent>
    </ToastProvider>
  );
}
