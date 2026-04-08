import { NextRequest, NextResponse } from "next/server";

const {
  appendCryptoProfitabilityJournalEntry,
  getDayTradingSnapshot,
} = require("@/lib/day-trading");

export const runtime = "nodejs";

async function readJsonBody(req: NextRequest): Promise<Record<string, unknown> | null> {
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

export async function POST(req: NextRequest) {
  try {
    const body = await readJsonBody(req);
    if (!body) {
      return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
    }

    const result = await appendCryptoProfitabilityJournalEntry({
      ticketId: body.ticketId,
      tradeTimestamp: body.tradeTimestamp,
      sessionLabel: body.sessionLabel,
      symbol: body.symbol,
      regime: body.regime,
      setupId: body.setupId,
      side: body.side,
      setup_match_confirmed: body.setup_match_confirmed,
      headline_lockout_checked: body.headline_lockout_checked,
      maker_limit_plan_confirmed: body.maker_limit_plan_confirmed,
      plannedEntryPrice: body.plannedEntryPrice,
      actualEntryPrice: body.actualEntryPrice,
      stopPrice: body.stopPrice,
      targetPrice: body.targetPrice,
      actualExitPrice: body.actualExitPrice,
      orderType: body.orderType,
      entryLiquidityRole: body.entryLiquidityRole,
      exitLiquidityRole: body.exitLiquidityRole,
      entryFillRatio: body.entryFillRatio,
      exitFillRatio: body.exitFillRatio,
      exitReason: body.exitReason,
      stopExecutionQuality: body.stopExecutionQuality,
      sizeUsd: body.sizeUsd,
      feesUsd: body.feesUsd,
      spreadSlippageUsd: body.spreadSlippageUsd,
      pnlR: body.pnlR,
      pnlUsd: body.pnlUsd,
      screenshotPath: body.screenshotPath,
      ruleAdherenceScore: body.ruleAdherenceScore,
      mistakeTag: body.mistakeTag,
      note: body.note,
    });
    const snapshot = getDayTradingSnapshot();

    return NextResponse.json({
      entry: result.entry,
      summary: result.summary,
      snapshot,
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: err instanceof Error ? err.message : "Failed to log day-trading journal entry",
      },
      { status: 500 },
    );
  }
}
