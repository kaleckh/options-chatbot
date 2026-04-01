"use client";

import { memo } from "react";

interface MetricCardProps {
  label: string;
  value: string;
  delta?: string;
  help?: string;
}

function MetricCard({ label, value, delta, help }: MetricCardProps) {
  return (
    <div className="metric-card">
      <div className="metric-label">
        {label}
        {help && <span className="sr-only">: {help}</span>}
      </div>
      <div className="metric-value">{value}</div>
      {delta && (
        <div
          className={`text-xs font-mono mt-0.5 ${
            delta.startsWith("+") || delta.startsWith("▲")
              ? "text-green"
              : delta.startsWith("-") || delta.startsWith("▼")
              ? "text-red"
              : "text-text-2"
          }`}
        >
          {delta}
        </div>
      )}
    </div>
  );
}

export default memo(MetricCard);
