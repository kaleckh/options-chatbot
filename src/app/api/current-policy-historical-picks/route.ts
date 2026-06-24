import { promises as fs } from "fs";
import path from "path";
import { NextResponse } from "next/server";
import { jsonError } from "@/app/api/_utils";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const CURRENT_POLICY_HISTORICAL_PICKS_PATH = path.join(
  process.cwd(),
  "data",
  "forward-tracking",
  "current_policy_historical_picks_latest.json"
);

export async function GET() {
  try {
    const raw = await fs.readFile(CURRENT_POLICY_HISTORICAL_PICKS_PATH, "utf8");
    return NextResponse.json(JSON.parse(raw));
  } catch (err) {
    return jsonError(err, "Failed to fetch current-policy historical picks");
  }
}
