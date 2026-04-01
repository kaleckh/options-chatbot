import { NextResponse } from "next/server";
import { getSectorSentiments } from "@/lib/python-bridge";

export async function GET() {
  try {
    const sectors = await getSectorSentiments();
    return NextResponse.json(sectors);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed" },
      { status: 500 }
    );
  }
}
