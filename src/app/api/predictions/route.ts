import { NextResponse } from "next/server";
import { getPredictions } from "@/lib/python-bridge";
import { jsonError } from "../_utils";

export async function GET() {
  try {
    const predictions = await getPredictions();
    return NextResponse.json(predictions);
  } catch (err) {
    return jsonError(err, "Failed to fetch predictions");
  }
}
