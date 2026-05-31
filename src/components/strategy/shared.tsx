"use client";

import { Brain, Target } from "lucide-react";
import { useId } from "react";

export const SUB_TABS = [
  { id: "optimizer", label: "Replay Review", icon: Target },
  { id: "brain", label: "Policy Editor", icon: Brain },
] as const;

export function fmtTruthSource(value?: string | null): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "historical_imported_daily") return "Imported daily validation";
  if (normalized === "historical_imported") return "Imported historical validation";
  if (normalized === "synthetic" || normalized === "synthetic_only") return "Synthetic research-only";
  return value ? `Unknown truth source (${value})` : "Unknown truth source";
}

export function hasError(payload: unknown): payload is { error: string } {
  return Boolean(
    payload &&
      typeof payload === "object" &&
      !Array.isArray(payload) &&
      "error" in payload &&
      typeof (payload as { error?: unknown }).error === "string"
  );
}

export function Slider({
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
      <div className="mb-1 flex items-center justify-between">
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
        className="h-1.5 w-full cursor-pointer appearance-none rounded-full bg-border accent-accent"
      />
    </div>
  );
}

export function ProfileSkeleton() {
  return (
    <div className="grid animate-pulse grid-cols-1 gap-6 lg:grid-cols-2">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="space-y-3 rounded-lg border border-border bg-bg-2 p-4">
          <div className="h-4 w-40 rounded bg-bg-3" />
          <div className="space-y-2">
            {[...Array(4)].map((__, j) => (
              <div key={j} className="h-6 rounded bg-bg-3" />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
