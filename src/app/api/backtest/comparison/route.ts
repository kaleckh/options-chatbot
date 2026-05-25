import { NextRequest, NextResponse } from "next/server";
import { getTruthLaneComparison } from "@/lib/python-bridge";
import { jsonError } from "../../_utils";

export async function GET(req: NextRequest) {
  try {
    const params = Object.fromEntries(req.nextUrl.searchParams.entries());
    const result = await getTruthLaneComparison(params);
    return NextResponse.json(result);
  } catch (err) {
    return jsonError(err, "Failed to fetch truth-lane comparison");
  }
}
