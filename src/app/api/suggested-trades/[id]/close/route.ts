import { NextRequest, NextResponse } from "next/server";
import { closeSuggestedTrade } from "@/lib/python-bridge";
import {
  jsonError,
  jsonWithTradingDeskStore,
  readJsonObject,
  requireTradingDeskMutationIntent,
} from "../../../_utils";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const intentError = requireTradingDeskMutationIntent(req, "close_suggested_trade");
    if (intentError) return intentError;
    const body = await readJsonObject(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const { id } = await params;
    const tradeId = Number(id);
    if (!Number.isInteger(tradeId) || tradeId <= 0) {
      return NextResponse.json({ error: "Invalid suggested trade id" }, { status: 400 });
    }
    const result = await closeSuggestedTrade(tradeId, body);
    return jsonWithTradingDeskStore(result, "suggested_trades_close");
  } catch (err) {
    return jsonError(err, "Failed to close suggested trade");
  }
}
