import { NextRequest, NextResponse } from "next/server";
import { isTruthyQueryParam, jsonError, readJsonObject } from "@/app/api/_utils";
import { createTrackedPosition, getGroupedTrackedPositions, getTrackedPositions } from "@/lib/python-bridge";

export async function GET(req: NextRequest) {
  try {
    const status = (req.nextUrl.searchParams.get("status") || "open") as "open" | "closed" | "all";
    const grouped = isTruthyQueryParam(req.nextUrl.searchParams.get("grouped"));
    if (grouped) {
      return NextResponse.json(await getGroupedTrackedPositions(status));
    }
    const result = await getTrackedPositions(status);
    return NextResponse.json(result);
  } catch (err) {
    return jsonError(err, "Failed to fetch tracked positions");
  }
}

export async function POST(req: NextRequest) {
  try {
    const body = await readJsonObject(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await createTrackedPosition(body);
    return NextResponse.json(result);
  } catch (err) {
    return jsonError(err, "Failed to create tracked position");
  }
}
