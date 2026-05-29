import { NextRequest, NextResponse } from "next/server";
import { BackendHttpError } from "@/lib/backend/transport";

export async function readJsonObject(
  req: NextRequest,
  options: { defaultValue?: Record<string, unknown> } = {}
): Promise<Record<string, unknown> | null> {
  const text = await req.text();
  if (!text.trim()) {
    return options.defaultValue ?? null;
  }
  try {
    const body = JSON.parse(text);
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
    const body = { error: error.message, details: error.payload };
    return NextResponse.json(
      body,
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
