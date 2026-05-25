import { NextRequest, NextResponse } from "next/server";
import { getChangelog } from "@/lib/python-bridge";
import { jsonError } from "../_utils";

export async function GET(req: NextRequest) {
  try {
    const profile = req.nextUrl.searchParams.get("profile") || "equity";
    const result = await getChangelog(profile);
    return NextResponse.json(result);
  } catch (err) {
    return jsonError(err, "Failed to fetch changelog");
  }
}
