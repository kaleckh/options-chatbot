import { NextResponse } from "next/server";
import { getRiskSettings } from "@/lib/python-bridge";

export async function GET() {
  try {
    const result = await getRiskSettings();
    const equityRisk = (result?.equity as Record<string, unknown> | undefined) || {};
    return NextResponse.json({
      current_settings: equityRisk,
      profiles: result,
    });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch risk settings" },
      { status: 500 }
    );
  }
}
