import { NextRequest, NextResponse } from "next/server";
import { jsonError, jsonWithRouteLifecycle, readJsonObject, requireLocalOperator } from "@/app/api/_utils";
import { runScan } from "@/lib/python-bridge";

export async function POST(req: NextRequest) {
  try {
    const authError = requireLocalOperator(req);
    if (authError) return authError;
    const body = await readJsonObject(req, { defaultValue: {} });
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await runScan(body);
    return jsonWithRouteLifecycle(result, "scan_run");
  } catch (err) {
    return jsonError(err, "Scan failed");
  }
}
