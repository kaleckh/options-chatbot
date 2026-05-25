import { NextResponse } from "next/server";
import { getOptionsProfitStatus } from "@/lib/python-bridge";
import { jsonError } from "../../_utils";

export async function GET() {
  try {
    const result = await getOptionsProfitStatus();
    return NextResponse.json(result);
  } catch (err) {
    return jsonError(err, "Failed to fetch options profit status");
  }
}
