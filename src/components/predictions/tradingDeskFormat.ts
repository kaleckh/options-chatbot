import type { ScanPick } from "@/lib/types";

export function fmtMoney(value?: number | null, digits: number = 2): string {
  if (value == null || Number.isNaN(value)) return "\u2014";
  return `$${value.toFixed(digits)}`;
}

export function fmtPct(value?: number | null, digits: number = 1): string {
  if (value == null || Number.isNaN(value)) return "\u2014";
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function fmtDate(value?: string | null): string {
  return value ? value.slice(0, 10) : "\u2014";
}

export function fmtDateTime(value?: string | null): string {
  if (!value) return "\u2014";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function metricToneClass(value?: number | null): string {
  if (value == null || Number.isNaN(value)) return "text-text-2";
  if (value > 0) return "text-green";
  if (value < 0) return "text-red";
  return "text-text-2";
}

export function fmtPricingSource(value?: string | null): string {
  if (!value) return "\u2014";
  if (value === "mid") return "Bid/ask midpoint";
  if (value === "spread_mid_exact") return "Exact spread midpoint";
  if (value === "spread_bid_ask_exact") return "Exact spread bid/ask";
  if (value === "spread_mid_approx") return "Comparable spread midpoint";
  if (value === "last_price") return "Last trade only";
  if (value === "expired") return "Expired";
  if (value === "unavailable") return "Unpriced";
  return value;
}

export function fmtTruthSource(value?: string | null): string {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "historical_imported_daily") return "Imported daily validation";
  if (normalized === "historical_imported") return "Imported historical validation";
  if (normalized === "synthetic" || normalized === "synthetic_only") return "Synthetic research-only";
  return value ? `Unknown truth source (${value})` : "Unknown truth source";
}

export function fmtCompactLabel(value?: string | null): string {
  const normalized = String(value || "").trim();
  if (!normalized) return "\u2014";
  return normalized.replaceAll("_", " ");
}

export function fmtUpperLabel(value?: string | null): string {
  const normalized = String(value || "").trim();
  if (!normalized) return "\u2014";
  return normalized.replaceAll("_", " ").toUpperCase();
}

export function contractQualityLabel(pick?: Partial<ScanPick> | null): string {
  const selectionSource = String(pick?.selection_source || "").trim().toLowerCase();
  const promotionClass = String(pick?.promotion_class || "").trim().toLowerCase();
  if (String(pick?.contract_symbol || "").trim()) {
    if (selectionSource.includes("archived_exact") || selectionSource.includes("exact_contract")) {
      return "Exact contract";
    }
    if (selectionSource.includes("model_target") || promotionClass.includes("bootstrap") || promotionClass.includes("sparse")) {
      return "Model exact fallback";
    }
    if (selectionSource.includes("nearest") || promotionClass.includes("nearest")) {
      return "Nearest listed";
    }
    return "Exact symbol recorded";
  }
  if (selectionSource.includes("nearest") || promotionClass.includes("nearest")) {
    return "Nearest listed";
  }
  return "Contract missing";
}

export function quoteContextLabel(pick?: Partial<ScanPick> | null): string {
  const basis = fmtCompactLabel(pick?.quote_basis);
  const freshness = fmtCompactLabel(pick?.quote_freshness_status);
  if (basis === "\u2014" && freshness === "\u2014") return "\u2014";
  if (basis === "\u2014") return freshness;
  if (freshness === "\u2014") return basis;
  return `${basis} / ${freshness}`;
}

export function fmtRiskUpsideLabel(pick?: Partial<ScanPick> | null): string {
  const risk = pick?.risk_tier;
  const upside = pick?.upside_tier;
  if (risk == null && upside == null) return "\u2014";
  return `R${risk ?? "\u2014"} / U${upside ?? "\u2014"}`;
}
