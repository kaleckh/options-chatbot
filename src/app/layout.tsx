"use client";

import "./globals.css";
import { useState, useEffect, useCallback } from "react";
import { Inter, JetBrains_Mono } from "next/font/google";
import dynamic from "next/dynamic";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import { ToastProvider, useToast } from "@/components/ui/Toast";
import ErrorBoundary from "@/components/ui/ErrorBoundary";
import { MetricGridSkeleton } from "@/components/ui/Skeleton";

const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-mono",
});

function LoadingSkeleton() {
  return (
    <div className="p-6">
      <MetricGridSkeleton count={5} />
    </div>
  );
}

const PredictionsView = dynamic(
  () => import("@/components/predictions/PredictionsView"),
  { loading: () => <LoadingSkeleton /> }
);

const StrategyView = dynamic(
  () => import("@/components/strategy/StrategyView"),
  { loading: () => <LoadingSkeleton /> }
);

function AppShell({ children }: { children: React.ReactNode }) {
  const toast = useToast();

  const [activeTab, setActiveTab] = useState<string>("predictions");
  const [riskSettings, setRiskSettings] = useState<Record<string, unknown> | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const fetchRisk = useCallback(async () => {
    try {
      const res = await fetch("/api/tools/manage_risk_settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.result) {
          setRiskSettings(JSON.parse(data.result));
        }
      }
    } catch {
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

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`dark ${inter.variable} ${jetbrainsMono.variable}`}>
      <body className="bg-bg-1 text-text-1 font-sans antialiased">
        <ToastProvider>
          <AppShell>{children}</AppShell>
        </ToastProvider>
      </body>
    </html>
  );
}
