import { NextRequest, NextResponse } from "next/server";
import { getChangelog } from "@/lib/python-bridge";

export async function GET(req: NextRequest) {
  try {
    const profile = req.nextUrl.searchParams.get("profile") || "equity";
    const result = await getChangelog(profile);
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch changelog" },
      { status: 500 }
    );
  }
}
