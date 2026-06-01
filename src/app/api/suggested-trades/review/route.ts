import { NextRequest, NextResponse } from "next/server";
import {
  jsonError,
  jsonWithTradingDeskStore,
  readJsonObject,
  requireTradingDeskMutationIntent,
} from "@/app/api/_utils";
import { reviewSuggestedTrades } from "@/lib/python-bridge";

export async function POST(req: NextRequest) {
  try {
    const intentError = requireTradingDeskMutationIntent(req, "review_suggested_trades");
    if (intentError) return intentError;
    const body = await readJsonObject(req, { defaultValue: {} });
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await reviewSuggestedTrades(body);
    return jsonWithTradingDeskStore(result, "suggested_trades_review");
  } catch (err) {
    return jsonError(err, "Failed to review suggested trades");
  }
}
