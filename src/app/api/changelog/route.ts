import { NextRequest } from "next/server";
import { getChangelog } from "@/lib/python-bridge";
import { jsonError, jsonWithStrategyLabContract } from "../_utils";

export async function GET(req: NextRequest) {
  try {
    const profile = req.nextUrl.searchParams.get("profile") || "equity";
    const result = await getChangelog(profile);
    return jsonWithStrategyLabContract(result, "profile_changelog_read");
  } catch (err) {
    return jsonError(err, "Failed to fetch changelog");
  }
}
