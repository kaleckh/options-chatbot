import { NextRequest, NextResponse } from "next/server";

const { getDayTradingSnapshot, runDayTradingValidation, normalizeDayTradingMarket } = require("@/lib/day-trading");

export const runtime = "nodejs";

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

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const market = normalizeDayTradingMarket(searchParams.get("market"));
    const snapshot = getDayTradingSnapshot({ market });
    return NextResponse.json(snapshot);
  } catch (err) {
    return NextResponse.json(
      {
        error: err instanceof Error ? err.message : "Failed to load day-trading snapshot",
      },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await readJsonBody(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const market = normalizeDayTradingMarket(body.market);
    const report = await runDayTradingValidation({
      market,
      bars: body.bars,
      startingCash: body.startingCash,
    });
    const snapshot = getDayTradingSnapshot({ market });
    return NextResponse.json({ report, snapshot });
  } catch (err) {
    return NextResponse.json(
      {
        error: err instanceof Error ? err.message : "Failed to run day-trading validation",
      },
      { status: 500 }
    );
  }
}
