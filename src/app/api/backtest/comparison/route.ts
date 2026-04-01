import { NextRequest, NextResponse } from "next/server";
import { getTruthLaneComparison } from "@/lib/python-bridge";

export async function GET(req: NextRequest) {
  try {
    const params = Object.fromEntries(req.nextUrl.searchParams.entries());
    const result = await getTruthLaneComparison(params);
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch truth-lane comparison" },
      { status: 500 }
    );
  }
}
