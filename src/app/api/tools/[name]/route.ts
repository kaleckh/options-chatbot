import { NextRequest, NextResponse } from "next/server";
import { jsonError, readJsonObject } from "@/app/api/_utils";
import { callTool } from "@/lib/python-bridge";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  const { name } = await params;
  const body = await readJsonObject(req, { defaultValue: {} });
  if (!body) {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  try {
    const result = await callTool(name, body);
    return NextResponse.json({ result });
  } catch (err) {
    return jsonError(err, "Tool call failed");
  }
}
