import { NextRequest, NextResponse } from "next/server";
import { jsonError, readJsonObject } from "@/app/api/_utils";
import { reviewSuggestedTrades } from "@/lib/python-bridge";

export async function POST(req: NextRequest) {
  try {
    const body = await readJsonObject(req, { defaultValue: {} });
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await reviewSuggestedTrades(body);
    return NextResponse.json(result);
  } catch (err) {
    return jsonError(err, "Failed to review suggested trades");
  }
}
