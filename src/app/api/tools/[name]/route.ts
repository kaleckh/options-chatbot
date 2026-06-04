import { NextRequest, NextResponse } from "next/server";
import { jsonError, jsonWithRouteLifecycle, readJsonObject, requireLocalOperator } from "@/app/api/_utils";
import { callTool } from "@/lib/python-bridge";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  try {
    const authError = requireLocalOperator(req);
    if (authError) return authError;
    const { name } = await params;
    const body = await readJsonObject(req, { defaultValue: {} });
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }
    const result = await callTool(name, body);
    return jsonWithRouteLifecycle({ result }, "tool_dispatch");
  } catch (err) {
    return jsonError(err, "Tool call failed");
  }
}
