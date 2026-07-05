import { NextResponse } from "next/server";
import { jsonError } from "@/app/api/_utils";
import { getCurrentPolicyHistoricalPicks } from "@/lib/backend/support";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    return NextResponse.json(await getCurrentPolicyHistoricalPicks());
  } catch (err) {
    return jsonError(err, "Failed to fetch current-policy historical picks");
  }
}
