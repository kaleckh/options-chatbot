import { NextRequest } from "next/server";
import { getPlaybookExitAudit } from "@/lib/python-bridge";
import { jsonError, jsonWithStrategyLabContract } from "../../_utils";

export async function GET(req: NextRequest) {
  try {
    const params = Object.fromEntries(req.nextUrl.searchParams.entries());
    const result = await getPlaybookExitAudit(params);
    return jsonWithStrategyLabContract(result, "exit_audit_read");
  } catch (err) {
    return jsonError(err, "Failed to fetch playbook exit audit");
  }
}
