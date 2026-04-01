import { NextRequest, NextResponse } from "next/server";
import { createSuggestedTrade, getSuggestedTrades } from "@/lib/python-bridge";

export async function GET(req: NextRequest) {
  try {
    const status = (req.nextUrl.searchParams.get("status") || "open") as "open" | "closed" | "all";
    const result = await getSuggestedTrades(status);
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch suggested trades" },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const result = await createSuggestedTrade(body);
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create suggested trade" },
      { status: 500 }
    );
  }
}
