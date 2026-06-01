import { NextRequest } from "next/server";
import { getMetricTruthReport } from "@/lib/python-bridge";
import { jsonError, jsonWithStrategyLabContract } from "../../_utils";

export async function GET(req: NextRequest) {
  try {
    const params = Object.fromEntries(req.nextUrl.searchParams.entries());
    const result = await getMetricTruthReport(params);
    return jsonWithStrategyLabContract(result, "metric_truth_read");
  } catch (err) {
    return jsonError(err, "Failed to fetch metric truth report");
  }
}
