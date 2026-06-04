import { NextRequest, NextResponse } from "next/server";
import {
  isTruthyQueryParam,
  jsonError,
  jsonWithValidatedTradingDeskStore,
  readJsonObject,
  requireLocalOperator,
  requireTradingDeskMutationIntent,
} from "@/app/api/_utils";
import {
  createSuggestedTrade,
  getGroupedSuggestedTradesWithBackendHeaders,
  getSuggestedTradesWithBackendHeaders,
} from "@/lib/python-bridge";
import type { CreateSuggestedTradeRequest } from "@/lib/trading-desk/apiContracts";

export async function GET(req: NextRequest) {
  try {
    const status = (req.nextUrl.searchParams.get("status") || "open") as "open" | "closed" | "all";
    const grouped = isTruthyQueryParam(req.nextUrl.searchParams.get("grouped"));
    const window = {
      limit: req.nextUrl.searchParams.get("limit"),
      offset: req.nextUrl.searchParams.get("offset"),
      compact: req.nextUrl.searchParams.get("compact"),
    };
    if (grouped) {
      const result = await getGroupedSuggestedTradesWithBackendHeaders(status, window);
      return jsonWithValidatedTradingDeskStore(result.body, "suggested_trades_read", { headers: result.headers });
    }
    const result = await getSuggestedTradesWithBackendHeaders(status, window);
    return jsonWithValidatedTradingDeskStore(result.body, "suggested_trades_read", { headers: result.headers });
  } catch (err) {
    return jsonError(err, "Failed to fetch suggested trades");
  }
}

export async function POST(req: NextRequest) {
  try {
    const authError = requireLocalOperator(req);
    if (authError) return authError;
    const intentError = requireTradingDeskMutationIntent(req, "create_suggested_trade");
    if (intentError) return intentError;
    const body = await readJsonObject<CreateSuggestedTradeRequest>(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await createSuggestedTrade(body);
    return jsonWithValidatedTradingDeskStore(result, "suggested_trades_create");
  } catch (err) {
    return jsonError(err, "Failed to create suggested trade");
  }
}
