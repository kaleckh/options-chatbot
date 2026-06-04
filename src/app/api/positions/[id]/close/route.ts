import { NextRequest, NextResponse } from "next/server";
import { closeTrackedPosition } from "@/lib/python-bridge";
import {
  jsonError,
  jsonWithValidatedTradingDeskStore,
  readJsonObject,
  requireLocalOperator,
  requireTradingDeskMutationIntent,
} from "../../../_utils";
import type { CloseTrackedPositionRequest } from "@/lib/trading-desk/apiContracts";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const authError = requireLocalOperator(req);
    if (authError) return authError;
    const intentError = requireTradingDeskMutationIntent(req, "close_tracked_position");
    if (intentError) return intentError;
    const body = await readJsonObject<CloseTrackedPositionRequest>(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const { id } = await params;
    const positionId = Number(id);
    if (!Number.isInteger(positionId) || positionId <= 0) {
      return NextResponse.json({ error: "Invalid tracked position id" }, { status: 400 });
    }
    const result = await closeTrackedPosition(positionId, body);
    return jsonWithValidatedTradingDeskStore(result, "tracked_positions_close");
  } catch (err) {
    return jsonError(err, "Failed to close tracked position");
  }
}
