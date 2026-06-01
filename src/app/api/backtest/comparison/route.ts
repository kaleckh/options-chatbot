import { NextRequest } from "next/server";
import { getTruthLaneComparison } from "@/lib/python-bridge";
import { jsonError, jsonWithStrategyLabContract } from "../../_utils";

export async function GET(req: NextRequest) {
  try {
    const params = Object.fromEntries(req.nextUrl.searchParams.entries());
    const result = await getTruthLaneComparison(params);
    return jsonWithStrategyLabContract(result, "truth_lane_comparison_read");
  } catch (err) {
    return jsonError(err, "Failed to fetch truth-lane comparison");
  }
}
