import { NextRequest, NextResponse } from "next/server";
import { createTrackedPosition, getTrackedPositions } from "@/lib/python-bridge";

export async function GET(req: NextRequest) {
  try {
    const status = (req.nextUrl.searchParams.get("status") || "open") as "open" | "closed" | "all";
    const result = await getTrackedPositions(status);
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch tracked positions" },
      { status: 500 }
    );
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const result = await createTrackedPosition(body);
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create tracked position" },
      { status: 500 }
    );
  }
}
