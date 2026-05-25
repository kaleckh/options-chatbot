import { NextResponse } from "next/server";
import { getRiskSettings } from "@/lib/python-bridge";
import { jsonError } from "../_utils";

export async function GET() {
  try {
    const result = await getRiskSettings();
    const equityRisk = (result?.equity as Record<string, unknown> | undefined) || {};
    return NextResponse.json({
      current_settings: equityRisk,
      profiles: result,
    });
  } catch (err) {
    return jsonError(err, "Failed to fetch risk settings");
  }
}
