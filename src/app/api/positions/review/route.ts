import { NextRequest, NextResponse } from "next/server";
import {
  jsonError,
  jsonWithValidatedTradingDeskStore,
  readJsonObject,
  requireLocalOperator,
  requireTradingDeskMutationIntent,
} from "@/app/api/_utils";
import { reviewTrackedPositions } from "@/lib/python-bridge";
import type { ReviewTrackedPositionsRequest } from "@/lib/trading-desk/apiContracts";

export async function POST(req: NextRequest) {
  try {
    const authError = requireLocalOperator(req);
    if (authError) return authError;
    const intentError = requireTradingDeskMutationIntent(req, "review_tracked_positions");
    if (intentError) return intentError;
    const body = await readJsonObject<ReviewTrackedPositionsRequest>(req, { defaultValue: {} });
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await reviewTrackedPositions(body);
    return jsonWithValidatedTradingDeskStore(result, "tracked_positions_review");
  } catch (err) {
    return jsonError(err, "Failed to review tracked positions");
  }
}
