import { NextResponse } from "next/server";
import { getPredictionHistory } from "@/lib/python-bridge";

export async function GET() {
  try {
    const result = await getPredictionHistory();
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch prediction history" },
      { status: 500 }
    );
  }
}
