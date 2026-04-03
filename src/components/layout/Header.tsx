"use client";

import { useEffect, useState, memo } from "react";
import { Menu } from "lucide-react";

interface HeaderProps {
  onMenuClick?: () => void;
}

function Header({ onMenuClick }: HeaderProps) {
  const [now, setNow] = useState("");

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
    <header className="flex items-center justify-between px-4 md:px-8 py-3 border-b border-border">
      <div className="flex items-center gap-3 md:gap-4">
        {onMenuClick && (
          <button
            onClick={onMenuClick}
            className="md:hidden p-1.5 rounded-md text-text-2 hover:text-text-1 hover:bg-bg-4 transition-colors"
            aria-label="Open navigation menu"
          >
            <Menu size={20} />
          </button>
        )}

        <div className="font-mono text-lg md:text-xl font-bold text-text-0 tracking-tight">
          OPTIONS<span className="text-accent">AI</span>
        </div>

        <div className="hidden md:flex gap-2 items-center">
          <span className="inline-block px-2 py-0.5 rounded bg-accent-dim text-accent text-2xs font-semibold tracking-wide uppercase font-mono">
            Options Desk
          </span>
          <span className="inline-block px-2 py-0.5 rounded bg-bg-4 text-text-2 text-2xs font-medium tracking-wide uppercase font-mono">
            Crypto Pilot
          </span>
          <span className="inline-block px-2 py-0.5 rounded bg-bg-4 text-text-2 text-2xs font-medium tracking-wide uppercase font-mono">
            Guardrails On
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div
          className="font-mono text-xs text-text-3 bg-bg-3 px-2 md:px-3 py-1 rounded border border-border"
          aria-label="Current time in Eastern Time"
        >
          {now}
        </div>
      </div>
    </header>
  );
}

export default memo(Header);
