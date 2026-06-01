import { NextRequest } from "next/server";
import { getLiveTradePolicy } from "@/lib/python-bridge";
import { jsonError, jsonWithStrategyLabContract } from "../../_utils";

export async function GET(req: NextRequest) {
  try {
    const params = Object.fromEntries(req.nextUrl.searchParams.entries());
    const result = await getLiveTradePolicy(params);
    return jsonWithStrategyLabContract(result, "live_policy_read");
  } catch (err) {
    return jsonError(err, "Failed to fetch live trade policy");
  }
}
