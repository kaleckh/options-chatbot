import { NextRequest, NextResponse } from "next/server";
import { jsonError, readJsonObject } from "@/app/api/_utils";
import { getProfile, saveProfile } from "@/lib/python-bridge";

export async function GET(req: NextRequest) {
  try {
    const type = req.nextUrl.searchParams.get("type") || "equity";
    const profile = await getProfile(type as "equity" | "index");
    return NextResponse.json(profile);
  } catch (err) {
    return jsonError(err, "Failed");
  }
}

export async function PUT(req: NextRequest) {
  try {
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
    return NextResponse.json({ ok: true });
  } catch (err) {
    return jsonError(err, "Failed");
  }
}
