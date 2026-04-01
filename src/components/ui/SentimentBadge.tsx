"use client";

import { memo } from "react";

const COLORS: Record<string, string> = {
  "Very Bullish": "#1f6b36",
  Bullish: "#3fb950",
  Neutral: "#484f58",
  Bearish: "#d29922",
  "Very Bearish": "#f85149",
};

const ICONS: Record<string, string> = {
  "Very Bullish": "⬆⬆",
  Bullish: "⬆",
  Neutral: "→",
  Bearish: "⬇",
  "Very Bearish": "⬇⬇",
};

interface SentimentBadgeProps {
  sentiment: string;
  returnPct?: number;
  oldSentiment?: string | null;
}

function SentimentBadge({
  sentiment,
  returnPct,
  oldSentiment,
}: SentimentBadgeProps) {
  const color = COLORS[sentiment] || "#484f58";
  const icon = ICONS[sentiment] || "→";

  const badge = (
    <span className="sent-badge" style={{ background: color }} role="img" aria-label={sentiment}>
      <span aria-hidden="true">{icon}</span> {sentiment}
    </span>
  );

  const retEl =
    returnPct != null ? (
      <span className="text-xs ml-1" style={{ color }}>
        {returnPct >= 0 ? "+" : ""}
        {returnPct.toFixed(1)}%
      </span>
    ) : null;

  if (oldSentiment && oldSentiment !== sentiment) {
    const oldColor = COLORS[oldSentiment] || "#484f58";
    const oldIcon = ICONS[oldSentiment] || "→";
    return (
      <span className="inline-flex items-center gap-1">
        <span className="opacity-55">
          <span className="sent-badge" style={{ background: oldColor }} role="img" aria-label={`Previously ${oldSentiment}`}>
            <span aria-hidden="true">{oldIcon}</span> {oldSentiment}
          </span>
        </span>
        <span className="text-xs text-text-3" aria-hidden="true">→</span>
        <span className="sr-only">changed to</span>
        {badge}
        {retEl}
        <span className="text-xs text-amber ml-1">changed</span>
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1">
      {badge}
      {retEl}
    </span>
  );
}

export default memo(SentimentBadge);
