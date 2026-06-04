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
  createTrackedPosition,
  getGroupedTrackedPositionsWithBackendHeaders,
  getTrackedPositionsWithBackendHeaders,
} from "@/lib/python-bridge";
import type { CreateTrackedPositionRequest } from "@/lib/trading-desk/apiContracts";

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
      const result = await getGroupedTrackedPositionsWithBackendHeaders(status, window);
      return jsonWithValidatedTradingDeskStore(result.body, "tracked_positions_read", { headers: result.headers });
    }
    const result = await getTrackedPositionsWithBackendHeaders(status, window);
    return jsonWithValidatedTradingDeskStore(result.body, "tracked_positions_read", { headers: result.headers });
  } catch (err) {
    return jsonError(err, "Failed to fetch tracked positions");
  }
}

export async function POST(req: NextRequest) {
  try {
    const authError = requireLocalOperator(req);
    if (authError) return authError;
    const intentError = requireTradingDeskMutationIntent(req, "create_tracked_position");
    if (intentError) return intentError;
    const body = await readJsonObject<CreateTrackedPositionRequest>(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await createTrackedPosition(body);
    return jsonWithValidatedTradingDeskStore(result, "tracked_positions_create");
  } catch (err) {
    return jsonError(err, "Failed to create tracked position");
  }
}
