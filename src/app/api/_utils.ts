import { NextRequest, NextResponse } from "next/server";
import { BackendHttpError } from "@/lib/backend/transport";
import {
  TRADING_DESK_MUTATION_HEADER,
  type TradingDeskMutationIntent,
} from "@/lib/trading-desk/mutationIntent";
import {
  tradingDeskStoreHeaders,
  type TradingDeskRouteContractId,
} from "@/lib/trading-desk/storeOwnership";
import {
  STRATEGY_LAB_MUTATION_HEADER,
  strategyLabRouteHeaders,
  type StrategyLabMutationIntent,
  type StrategyLabRouteContractId,
} from "@/lib/strategy-lab/replayIntent";

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

export function requireTradingDeskMutationIntent(
  req: NextRequest,
  expectedIntent: TradingDeskMutationIntent
) {
  const actualIntent = String(req.headers.get(TRADING_DESK_MUTATION_HEADER) || "").trim();
  if (actualIntent === expectedIntent) return null;
  return NextResponse.json(
    {
      error: `Trading Desk mutation requires ${TRADING_DESK_MUTATION_HEADER}: ${expectedIntent}`,
    },
    { status: 428 }
  );
}

export function jsonWithTradingDeskStore(
  body: unknown,
  contractId: TradingDeskRouteContractId,
  init: ResponseInit = {}
) {
  return NextResponse.json(
    body,
    {
      ...init,
      headers: {
        ...tradingDeskStoreHeaders(contractId),
        ...(init.headers as Record<string, string> | undefined),
      },
    }
  );
}

export function requireStrategyLabMutationIntent(
  req: NextRequest,
  expectedIntent: StrategyLabMutationIntent
) {
  const actualIntent = String(req.headers.get(STRATEGY_LAB_MUTATION_HEADER) || "").trim();
  if (actualIntent === expectedIntent) return null;
  return NextResponse.json(
    {
      error: `Strategy Lab mutation requires ${STRATEGY_LAB_MUTATION_HEADER}: ${expectedIntent}`,
    },
    { status: 428 }
  );
}

export function jsonWithStrategyLabContract(
  body: unknown,
  contractId: StrategyLabRouteContractId,
  init: ResponseInit = {}
) {
  return NextResponse.json(
    body,
    {
      ...init,
      headers: {
        ...strategyLabRouteHeaders(contractId),
        ...(init.headers as Record<string, string> | undefined),
      },
    }
  );
}
