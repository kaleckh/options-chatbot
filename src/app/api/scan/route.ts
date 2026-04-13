import { NextRequest, NextResponse } from "next/server";
import { jsonError, readJsonObject } from "@/app/api/_utils";
import { runScan } from "@/lib/python-bridge";

export async function POST(req: NextRequest) {
  try {
    const body = await readJsonObject(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await runScan(body);
    return NextResponse.json(result);
  } catch (err) {
    return jsonError(err, "Scan failed");
  }
}
