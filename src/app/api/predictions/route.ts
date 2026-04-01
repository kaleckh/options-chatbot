import { NextResponse } from "next/server";
import { getPredictions } from "@/lib/python-bridge";

export async function GET() {
  try {
    const predictions = await getPredictions();
    return NextResponse.json(predictions);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch predictions" },
      { status: 500 }
    );
  }
}
