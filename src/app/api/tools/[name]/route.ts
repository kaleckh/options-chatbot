import { NextRequest, NextResponse } from "next/server";
import { callTool } from "@/lib/python-bridge";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  const { name } = await params;
  const body = await req.json();

  try {
    const result = await callTool(name, body);
    return NextResponse.json({ result });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Tool call failed" },
      { status: 500 }
    );
  }
}
