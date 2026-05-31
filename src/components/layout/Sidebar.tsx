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
  { id: "predictions", label: "Trading Desk", icon: BarChart3 },
  { id: "strategy", label: "Strategy Lab", icon: FlaskConical },
];

export default function Sidebar({
  activeTab,
  onTabChange,
  riskSettings,
  isOpen,
  onClose,
}: SidebarProps) {
  const tabListRef = useRef<HTMLDivElement>(null);
  const mobilePanelRef = useRef<HTMLDivElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  const risk = riskSettings?.current_settings as Record<string, unknown> | undefined;
  const accountSize = Number(risk?.account_size || 0);
  const stopLoss = Number(risk?.stop_loss_pct || 90);
  const maxPct = Number(risk?.max_position_pct || 40);

  const selectTab = useCallback((tabId: string) => {
    onTabChange(tabId);
    if (isOpen) onClose();
  }, [isOpen, onClose, onTabChange]);

  const handleTabKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLButtonElement>) => {
      const tabIds = TABS.map((t) => t.id);
      const currentIdx = tabIds.indexOf(activeTab);
      let nextIdx: number | null = null;

      switch (e.key) {
        case "ArrowDown":
        case "ArrowRight":
          e.preventDefault();
          nextIdx = (currentIdx + 1) % tabIds.length;
          break;
        case "ArrowUp":
        case "ArrowLeft":
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
        const buttons = container?.querySelectorAll<HTMLButtonElement>('[role="tab"]');
        buttons?.[nextIdx]?.focus();
      }
    },
    [activeTab, onTabChange]
  );

  useEffect(() => {
    if (!isOpen) return undefined;
    previousFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    window.setTimeout(() => {
      const panel = mobilePanelRef.current;
      const selected = panel?.querySelector<HTMLButtonElement>('[role="tab"][aria-selected="true"]');
      selected?.focus();
    }, 0);

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const panel = mobilePanelRef.current;
      if (!panel) return;
      const focusable = Array.from(
        panel.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        )
      ).filter((element) => !element.hasAttribute("disabled"));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, [isOpen, onClose]);

  const riskSummary = accountSize > 0
    ? [
        `$${accountSize.toLocaleString()} account`,
        `${maxPct}% max/trade`,
        `${stopLoss}% stop`,
      ].join(" | ")
    : "Risk sizing not configured";

  const sidebarContent = (
    <aside className="w-56 flex-shrink-0 flex flex-col border-r border-border bg-bg-0 overflow-hidden h-full">
      <div className="flex-1 overflow-y-auto px-3 py-4">
        <div className="pb-4 mb-4 border-b border-border">
          <div className="font-mono text-lg font-bold text-text-0 tracking-tight">
            OPTIONS<span className="text-accent">AI</span>
          </div>
          <div className="mt-1.5 text-2xs text-text-2 tracking-wide uppercase font-medium">
            Supervised options workbench
          </div>
        </div>

        <div
          ref={tabListRef}
          role="tablist"
          aria-label="Main navigation"
          className="space-y-1"
        >
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                id={`${tab.id}-tab`}
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={isActive}
                aria-controls={`${tab.id}-panel`}
                tabIndex={isActive ? 0 : -1}
                onClick={() => selectTab(tab.id)}
                onKeyDown={handleTabKeyDown}
                className={`w-full flex items-center gap-2.5 rounded-md border px-3 py-2.5 text-sm font-medium transition-all ${
                  isActive
                    ? "bg-accent-dim text-accent border-accent/25"
                    : "text-text-2 hover:bg-bg-3 hover:text-text-0 border-transparent"
                }`}
              >
                <Icon size={16} aria-hidden="true" />
                {tab.label}
              </button>
            );
          })}
        </div>

        <div className="mt-4 rounded-md border border-border bg-bg-2 px-3 py-2">
          <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-text-3">
            Risk Snapshot
          </div>
          <div className="mt-1 text-xs leading-relaxed text-text-1">{riskSummary}</div>
        </div>
      </div>

      <div className="px-3 py-3 border-t border-border">
        <p className="text-2xs text-text-3 leading-relaxed">
          Not financial advice. Options trading involves substantial risk of loss.
        </p>
      </div>
    </aside>
  );

  return (
    <>
      <div className="hidden md:flex h-full">{sidebarContent}</div>

      {isOpen && (
        <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="Navigation menu">
          <div
            className="absolute inset-0 bg-black/55 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden="true"
          />

          <div ref={mobilePanelRef} className="absolute inset-y-0 left-0 animate-slide-in-left">
            <div className="relative h-full">
              {sidebarContent}
              <button
                type="button"
                onClick={onClose}
                aria-label="Close sidebar"
                className="absolute top-3 right-3 p-1 rounded-md text-text-3 hover:text-text-1 hover:bg-bg-4 transition-all"
              >
                <X size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
