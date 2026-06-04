import { NextRequest, NextResponse } from "next/server";
import {
  jsonError,
  jsonWithValidatedTradingDeskStore,
  readJsonObject,
  requireLocalOperator,
  requireTradingDeskMutationIntent,
} from "@/app/api/_utils";
import { reviewSuggestedTrades } from "@/lib/python-bridge";
import type { ReviewSuggestedTradesRequest } from "@/lib/trading-desk/apiContracts";

export async function POST(req: NextRequest) {
  try {
    const authError = requireLocalOperator(req);
    if (authError) return authError;
    const intentError = requireTradingDeskMutationIntent(req, "review_suggested_trades");
    if (intentError) return intentError;
    const body = await readJsonObject<ReviewSuggestedTradesRequest>(req, { defaultValue: {} });
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await reviewSuggestedTrades(body);
    return jsonWithValidatedTradingDeskStore(result, "suggested_trades_review");
  } catch (err) {
    return jsonError(err, "Failed to review suggested trades");
  }
}
