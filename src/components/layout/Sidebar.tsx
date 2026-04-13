"use client";

import { useCallback, useEffect, useRef } from "react";
import { BarChart3, FlaskConical, X } from "lucide-react";

interface SidebarProps {
  activeTab: string;
  onTabChange: (tab: string) => void;
  riskSettings: Record<string, unknown> | null;
  isOpen: boolean;
  onClose: () => void;
}

const TABS = [
  { id: "predictions", label: "Picks", icon: BarChart3 },
  { id: "strategy", label: "Research Lab", icon: FlaskConical },
];

export default function Sidebar({
  activeTab,
  onTabChange,
  riskSettings,
  isOpen,
  onClose,
}: SidebarProps) {
  const tabListRef = useRef<HTMLDivElement>(null);

  const risk = riskSettings?.current_settings as Record<string, unknown> | undefined;
  const accountSize = Number(risk?.account_size || 0);
  const stopLoss = Number(risk?.stop_loss_pct || 50);
  const maxDrawdown = Number(risk?.max_drawdown_pct || 15);
  const minPct = Number(risk?.min_position_pct || 7);
  const maxPct = Number(risk?.max_position_pct || 40);

  const handleTabKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>) => {
      const tabIds = TABS.map((t) => t.id);
      const currentIdx = tabIds.indexOf(activeTab);
      let nextIdx: number | null = null;

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          nextIdx = (currentIdx + 1) % tabIds.length;
          break;
        case "ArrowUp":
          e.preventDefault();
          nextIdx = (currentIdx - 1 + tabIds.length) % tabIds.length;
          break;
        case "Home":
          e.preventDefault();
          nextIdx = 0;
          break;
        case "End":
          e.preventDefault();
          nextIdx = tabIds.length - 1;
          break;
      }

      if (nextIdx !== null) {
        onTabChange(tabIds[nextIdx]);
        const container = tabListRef.current;
        if (container) {
          const buttons = container.querySelectorAll<HTMLButtonElement>('[role="tab"]');
          buttons[nextIdx]?.focus();
        }
      }
    },
    [activeTab, onTabChange]
  );

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) onClose();
    };
    window.addEventListener("keydown", handleEsc);
    return () => window.removeEventListener("keydown", handleEsc);
  }, [isOpen, onClose]);

  const sidebarContent = (
    <aside className="w-64 flex-shrink-0 flex flex-col border-r border-border bg-gradient-to-b from-bg-2 to-bg-0 overflow-hidden h-full">
      <div className="flex-1 overflow-y-auto px-4 py-5">
        <div className="pb-3 mb-3 border-b border-border">
          <div className="font-mono text-lg font-bold text-text-0 tracking-tight">
            OPTIONS<span className="text-accent">AI</span>
          </div>
          <div className="flex items-center gap-1.5 mt-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-green shadow-[0_0_6px_var(--green)]" />
            <span className="text-2xs text-text-2 tracking-wide uppercase font-medium">
              Options picks and replay-backed research
            </span>
          </div>
        </div>

        <div
          ref={tabListRef}
          role="tablist"
          aria-label="Main navigation"
          className="space-y-1 mb-3"
        >
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                role="tab"
                aria-selected={isActive}
                aria-controls={tab.id + "-panel"}
                tabIndex={isActive ? 0 : -1}
                onClick={() => onTabChange(tab.id)}
                onKeyDown={handleTabKeyDown}
                className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-all ${
                  isActive
                    ? "bg-accent-dim text-accent border border-accent/20"
                    : "text-text-2 hover:bg-bg-4 hover:text-text-1 border border-transparent"
                }`}
              >
                <Icon size={16} />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="border-t border-border pt-3" />

        {activeTab === "predictions" && (
          <div className="space-y-3">
            <div className="bg-bg-3 border border-accent/20 rounded-md p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-accent mb-2">
                Picks Workflow
              </div>
              <div className="text-sm text-text-1 leading-relaxed">
                Refresh the scanner, review the playbook, and only act when the risk settings and gate checks line up.
              </div>
              <div className="text-xs text-text-3 mt-2 leading-relaxed">
                Keep the options scanner lane separate from exploratory tooling so the guardrails stay easy to audit.
              </div>
            </div>

            {accountSize > 0 ? (
              <div className="space-y-2">
                <div className="metric-card">
                  <div className="metric-label">Account Size</div>
                  <div className="metric-value">${accountSize.toLocaleString()}</div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="metric-card">
                    <div className="metric-label">Min/Trade</div>
                    <div className="metric-value text-sm">
                      ${Math.round(accountSize * minPct / 100).toLocaleString()}
                    </div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">Max/Trade</div>
                    <div className="metric-value text-sm">
                      ${Math.round(accountSize * maxPct / 100).toLocaleString()}
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="metric-card">
                    <div className="metric-label">Stop-Loss</div>
                    <div className="metric-value text-sm">{stopLoss}%</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">Max Drawdown</div>
                    <div className="metric-value text-sm">
                      ${Math.round(accountSize * maxDrawdown / 100).toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-xs text-text-3 bg-bg-3 rounded-md px-3 py-2 border border-border">
                Set your account size in risk settings to make the sizing guidance more useful.
              </div>
            )}

            <div className="bg-bg-3 border border-border rounded-md p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-text-3 mb-2">
                Current Product Scope
              </div>
              <div className="text-xs text-text-2 leading-relaxed">
                Options picks stay in the scanner workflow. Research tooling supports validation, replay, and policy review around the options product.
              </div>
            </div>
          </div>
        )}

        {activeTab === "strategy" && (
          <div className="space-y-3">
            <div className="bg-bg-3 border border-accent/20 rounded-md p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-accent mb-2">
                Research Lab
              </div>
              <div className="text-sm text-text-1 leading-relaxed">
                Use this area for replay work, validation, and policy review around the options system.
              </div>
              <div className="text-xs text-text-3 mt-2 leading-relaxed">
                If we prototype anything new, keep it behind the existing guardrails instead of stretching the current scanner beyond its tested lane.
              </div>
            </div>

            <div className="bg-bg-3 border border-border rounded-md p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-text-3 mb-2">
                Current Scope
              </div>
              <div className="text-xs text-text-2 leading-relaxed">
                Optimizer and replay diagnostics stay here as supporting tools behind the picks workflow.
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="px-4 py-3 border-t border-border">
        <p className="text-2xs text-text-3 leading-relaxed">
          Not financial advice. Options trading involves substantial risk of loss. Market data may be delayed by source.
        </p>
      </div>
    </aside>
  );

  return (
    <>
      <div className="hidden md:flex h-full">{sidebarContent}</div>

      {isOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden="true"
          />

          <div className="absolute inset-y-0 left-0 animate-slide-in-left">
            <div className="relative h-full">
              {sidebarContent}
              <button
                onClick={onClose}
                aria-label="Close sidebar"
                className="absolute top-3 right-3 p-1 rounded-md text-text-3 hover:text-text-1 hover:bg-bg-4 transition-all"
              >
                <X size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
