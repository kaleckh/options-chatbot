import { NextRequest, NextResponse } from "next/server";

const { getDayTradingSnapshot, runDayTradingValidation, normalizeDayTradingMarket } = require("@/lib/day-trading");

export const runtime = "nodejs";

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
    const body = await req.json().catch(() => ({}));
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
