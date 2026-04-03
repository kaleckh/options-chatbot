import { NextRequest, NextResponse } from "next/server";

const {
  getDayTradingSnapshot,
  normalizeDayTradingMarket,
  runDayTradingExperiments,
} = require("@/lib/day-trading");

export const runtime = "nodejs";

function parseNumber(value: string | null | undefined): number | undefined {
  if (value == null || value === "") return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

async function readJsonBody(req: NextRequest): Promise<Record<string, unknown> | null> {
  try {
    const body = await req.json();
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      return null;
    }
    return body as Record<string, unknown>;
  } catch {
    return null;
  }
}

function resolveCryptoMarket(input: unknown) {
  const market = normalizeDayTradingMarket(input);
  if (market !== "crypto") {
    throw new Error("Day-trading experiments are only available for the crypto lane");
  }
  return market;
}

function buildExperimentOptions(source: Record<string, unknown> | URLSearchParams) {
  const getValue = (key: string) => {
    if (source instanceof URLSearchParams) {
      return source.get(key);
    }
    const value = source[key];
    return typeof value === "string" ? value : value == null ? null : String(value);
  };

  return {
    market: resolveCryptoMarket(getValue("market")),
    bars: parseNumber(getValue("bars")) ?? parseNumber(getValue("barsRequested")),
    top: parseNumber(getValue("top")),
    feesFraction: parseNumber(getValue("feesFraction")),
    windowMode: getValue("windowMode") || undefined,
    scope: getValue("scope") || undefined,
    researchMode: getValue("researchMode") || undefined,
    strictMarketData: getValue("strictMarketData") == null
      ? undefined
      : getValue("strictMarketData") !== "false",
  };
}

function resolveErrorStatus(err: unknown) {
  if (err instanceof Error && err.message.includes("only available for the crypto lane")) {
    return 400;
  }
  return 500;
}

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const options = buildExperimentOptions(searchParams);
    const snapshot = getDayTradingSnapshot(options);
    return NextResponse.json({
      report: snapshot.experimentReport || null,
      snapshot,
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: err instanceof Error ? err.message : "Failed to load day-trading experiments",
      },
      { status: resolveErrorStatus(err) },
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await readJsonBody(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const options = buildExperimentOptions(body);
    const report = await runDayTradingExperiments(options);
    const snapshot = getDayTradingSnapshot({ ...options, now: report.generatedAt });
    return NextResponse.json({
      report,
      snapshot,
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: err instanceof Error ? err.message : "Failed to run day-trading experiments",
      },
      { status: resolveErrorStatus(err) },
    );
  }
}
