import { NextRequest, NextResponse } from "next/server";

const { buildMorningWatchlist, normalizeDayTradingMarket } = require("@/lib/day-trading");

export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const market = normalizeDayTradingMarket(searchParams.get("market"));
    const limit = searchParams.get("limit");
    const bars = searchParams.get("bars");
    const watchlist = await buildMorningWatchlist({
      market,
      limit: limit == null ? undefined : Number(limit),
      bars: bars == null ? undefined : Number(bars),
    });
    return NextResponse.json(watchlist);
  } catch (err) {
    return NextResponse.json(
      {
        error: err instanceof Error ? err.message : "Failed to build day-trading watchlist",
      },
      { status: 500 },
    );
  }
}
