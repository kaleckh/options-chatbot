import { NextRequest, NextResponse } from "next/server";
import {
  jsonError,
  jsonWithStrategyLabContract,
  readJsonObject,
  requireStrategyLabMutationIntent,
} from "@/app/api/_utils";
import { getProfile, saveProfile } from "@/lib/python-bridge";

export async function GET(req: NextRequest) {
  try {
    const type = req.nextUrl.searchParams.get("type") || "equity";
    const profile = await getProfile(type as "equity" | "index");
    return jsonWithStrategyLabContract(profile, "profile_read");
  } catch (err) {
    return jsonError(err, "Failed");
  }
}

export async function PUT(req: NextRequest) {
  try {
    const intentError = requireStrategyLabMutationIntent(req, "save_strategy_profile");
    if (intentError) return intentError;
    const body = await readJsonObject(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const updates = Object.prototype.hasOwnProperty.call(body, "updates") ? body.updates : {};
    if (!updates || typeof updates !== "object" || Array.isArray(updates)) {
      return NextResponse.json({ error: "updates must be an object" }, { status: 400 });
    }
    await saveProfile(
      String(body.type || "equity"),
      updates as Record<string, unknown>,
      body.note != null ? String(body.note) : undefined
    );
    return jsonWithStrategyLabContract({ ok: true }, "profile_save");
  } catch (err) {
    return jsonError(err, "Failed");
  }
}
