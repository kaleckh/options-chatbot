import { NextRequest, NextResponse } from "next/server";
import {
  jsonError,
  jsonWithStrategyLabContract,
  readJsonObject,
  requireStrategyLabMutationIntent,
} from "@/app/api/_utils";
import { runBacktest } from "@/lib/python-bridge";

export async function POST(req: NextRequest) {
  try {
    const intentError = requireStrategyLabMutationIntent(req, "run_replay_backtest");
    if (intentError) return intentError;
    const body = await readJsonObject(req, { defaultValue: {} });
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await runBacktest(body);
    return jsonWithStrategyLabContract(result, "backtest_run");
  } catch (err) {
    return jsonError(err, "Backtest failed");
  }
}
