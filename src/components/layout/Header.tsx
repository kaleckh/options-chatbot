"use client";

import { useEffect, useState, memo } from "react";
import { Menu, ShieldCheck } from "lucide-react";
import { getMainAppTab, type MainAppTabId } from "@/lib/navigation/tabs";

interface HeaderProps {
  onMenuClick?: () => void;
  activeTab: MainAppTabId;
}

function Header({ onMenuClick, activeTab }: HeaderProps) {
  const [now, setNow] = useState("");
  const activeTabMeta = getMainAppTab(activeTab);
  const title = activeTabMeta.title;
  const subtitle = activeTabMeta.subtitle;

  useEffect(() => {
    const update = () => {
      setNow(
        new Date().toLocaleString("en-US", {
          weekday: "short",
          month: "short",
          day: "2-digit",
          year: "numeric",
          hour: "2-digit",
          minute: "2-digit",
          timeZone: "America/New_York",
        }) + " ET"
      );
    };
    update();
    const iv = setInterval(update, 60000);
    return () => clearInterval(iv);
  }, []);

  return (
    <header className="flex items-center justify-between gap-4 px-4 md:px-8 py-3 border-b border-border bg-bg-1/95">
      <div className="flex items-center gap-3 md:gap-4">
        {onMenuClick && (
          <button
            type="button"
            onClick={onMenuClick}
            className="md:hidden p-1.5 rounded-md text-text-2 hover:text-text-1 hover:bg-bg-4 transition-colors"
            aria-label="Open navigation menu"
          >
            <Menu size={20} />
          </button>
        )}

        <div className="min-w-0">
          <div className="text-sm md:text-base font-semibold text-text-0">{title}</div>
          <div className="hidden sm:block text-xs text-text-2">{subtitle}</div>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <span className="hidden md:inline-flex items-center gap-1.5 rounded border border-green/25 bg-green-dim px-2.5 py-1 text-xs font-medium text-green">
          <ShieldCheck size={13} aria-hidden="true" />
          Guardrails
        </span>
        <div
          className="hidden sm:block font-mono text-xs text-text-2 bg-bg-3 px-2 md:px-3 py-1 rounded border border-border"
          aria-label="Current time in Eastern Time"
        >
          {now}
        </div>
      </div>
    </header>
  );
}

export default memo(Header);
