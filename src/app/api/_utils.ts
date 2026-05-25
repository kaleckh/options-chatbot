import { NextRequest, NextResponse } from "next/server";
import { BackendHttpError } from "@/lib/backend/transport";

export async function readJsonObject(
  req: NextRequest
): Promise<Record<string, unknown> | null> {
  try {
    const body = await req.json();
    if (!body || typeof body !== "object" || Array.isArray(body)) {
      return null;
    }
    return body as Record<string, unknown>;
  } catch {
    return null;
  }
}

export function jsonError(
  error: unknown,
  fallbackMessage: string,
  status: number = 500
) {
  if (error instanceof BackendHttpError) {
    return NextResponse.json(
      { error: error.message },
      { status: error.status }
    );
  }
  return NextResponse.json(
    { error: error instanceof Error ? error.message : fallbackMessage },
    { status }
  );
}

export function isTruthyQueryParam(value: string | null): boolean {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized === "1" || normalized === "true" || normalized === "yes" || normalized === "on";
}
