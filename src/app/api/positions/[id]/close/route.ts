import { NextRequest, NextResponse } from "next/server";
import { closeTrackedPosition } from "@/lib/python-bridge";

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const body = await req.json().catch(() => ({}));
    const { id } = await params;
    const result = await closeTrackedPosition(Number(id), body);
    return NextResponse.json(result);
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to close tracked position" },
      { status: 500 }
    );
  }
}
