import { NextRequest, NextResponse } from "next/server";
import { reviewSuggestedTrades } from "@/lib/python-bridge";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const result = await reviewSuggestedTrades(body);
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to review suggested trades" },
      { status: 500 }
    );
  }
}
