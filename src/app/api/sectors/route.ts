import { NextResponse } from "next/server";
import { getSectorSentiments } from "@/lib/python-bridge";
import { jsonError } from "../_utils";

export async function GET() {
  try {
    const sectors = await getSectorSentiments();
    return NextResponse.json(sectors);
  } catch (err) {
    return jsonError(err, "Failed");
  }
}
