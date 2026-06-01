import { NextRequest } from "next/server";
import { getBacktestReport } from "@/lib/python-bridge";
import { jsonError, jsonWithStrategyLabContract } from "../../_utils";

export async function GET(req: NextRequest) {
  try {
    const params = Object.fromEntries(req.nextUrl.searchParams.entries());
    const result = await getBacktestReport(params);
    return jsonWithStrategyLabContract(result, "backtest_report_read");
  } catch (err) {
    return jsonError(err, "Failed to fetch backtest report");
  }
}
