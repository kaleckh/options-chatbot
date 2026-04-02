import { NextResponse } from "next/server";
import { getOptionsProfitStatus } from "@/lib/python-bridge";

export async function GET() {
  try {
    const result = await getOptionsProfitStatus();
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to fetch options profit status" },
      { status: 500 }
    );
  }
}
