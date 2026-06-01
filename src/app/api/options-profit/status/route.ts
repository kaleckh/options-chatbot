import { NextResponse } from "next/server";
import { getOptionsProfitStatusWithBackendHeaders } from "@/lib/python-bridge";
import { jsonError } from "../../_utils";

export async function GET() {
  try {
    const result = await getOptionsProfitStatusWithBackendHeaders();
    return NextResponse.json(result.body, { headers: result.headers });
  } catch (err) {
    return jsonError(err, "Failed to fetch options profit status");
  }
}
