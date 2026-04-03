import { NextRequest, NextResponse } from "next/server";

const {
  getDayTradingSnapshot,
  normalizeDayTradingMarket,
  requestCryptoProfitabilityPreflightTicket,
} = require("@/lib/day-trading");

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

export async function POST(req: NextRequest) {
  try {
    const body = await readJsonBody(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }

    const market = normalizeDayTradingMarket(body.market);
    if (market !== "crypto") {
      return NextResponse.json(
        { error: "Preflight tickets are only available for the crypto pilot." },
        { status: 400 },
      );
    }

    const result = await requestCryptoProfitabilityPreflightTicket({
      strategyId: body.strategyId,
      bars: body.bars,
      now: body.now,
      setup_match_confirmed: body.setup_match_confirmed,
      headline_lockout_checked: body.headline_lockout_checked,
      maker_limit_plan_confirmed: body.maker_limit_plan_confirmed,
    });
    const snapshot = getDayTradingSnapshot({ market: "crypto" });

    return NextResponse.json({ result, snapshot });
  } catch (err) {
    return NextResponse.json(
      {
        error: err instanceof Error ? err.message : "Failed to request day-trading preflight ticket",
      },
      { status: 500 },
    );
  }
}
