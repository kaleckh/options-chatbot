"use client";

import { memo } from "react";

interface MetricCardProps {
  label: string;
  value: string;
  delta?: string;
  help?: string;
}

function MetricCard({ label, value, delta, help }: MetricCardProps) {
  const tone =
    delta?.startsWith("+") || delta?.startsWith("\u25B2")
      ? "text-green"
      : delta?.startsWith("-") || delta?.startsWith("\u25BC")
        ? "text-red"
        : "text-text-2";

  return (
    <div className="metric-card" title={help}>
      <div className="metric-label">
        {label}
        {help && <span className="sr-only">: {help}</span>}
      </div>
      <div className="metric-value">{value}</div>
      {delta && <div className={`mt-0.5 text-xs font-mono ${tone}`}>{delta}</div>}
    </div>
  );
}

export default memo(MetricCard);
