import { NextRequest } from "next/server";
import { getForwardEvidenceReport } from "@/lib/python-bridge";
import { jsonError, jsonWithStrategyLabContract } from "../../_utils";

export async function GET(req: NextRequest) {
  try {
    const params = Object.fromEntries(req.nextUrl.searchParams.entries());
    const result = await getForwardEvidenceReport(params);
    return jsonWithStrategyLabContract(result, "forward_evidence_read");
  } catch (err) {
    return jsonError(err, "Failed to fetch forward evidence report");
  }
}
