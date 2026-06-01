import { NextRequest } from "next/server";
import { getBacktestLast } from "@/lib/python-bridge";
import { jsonError, jsonWithStrategyLabContract } from "../../_utils";

export async function GET(req: NextRequest) {
  try {
    const params = Object.fromEntries(req.nextUrl.searchParams.entries());
    const result = await getBacktestLast(params);
    return jsonWithStrategyLabContract(result, "backtest_last_read");
  } catch (err) {
    return jsonError(err, "Failed to fetch latest backtest");
  }
}
