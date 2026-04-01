import { NextRequest, NextResponse } from "next/server";
import { runBacktest } from "@/lib/python-bridge";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json().catch(() => ({}));
    const result = await runBacktest(body as Record<string, unknown>);
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Backtest failed" },
      { status: 500 }
    );
  }
}
