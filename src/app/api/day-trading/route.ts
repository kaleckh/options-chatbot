import { NextRequest, NextResponse } from "next/server";

const { getDayTradingSnapshot, runDayTradingValidation } = require("@/lib/day-trading/engine");

export const runtime = "nodejs";

export async function GET() {
  try {
    const snapshot = getDayTradingSnapshot();
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
    const report = await runDayTradingValidation({
      bars: body.bars,
      startingCash: body.startingCash,
    });
    const snapshot = getDayTradingSnapshot();
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
