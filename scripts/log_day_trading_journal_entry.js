const { appendCryptoProfitabilityJournalEntry } = require("../src/lib/day-trading");

function parseArgs(argv) {
  const parsed = {};
  for (const raw of argv) {
    if (!raw.startsWith("--")) continue;
    const [flag, ...rest] = raw.slice(2).split("=");
    parsed[flag] = rest.join("=");
  }
  return parsed;
}

function requireString(args, key, label) {
  const value = String(args[key] || "").trim();
  if (!value) {
    throw new Error(`${label} is required (--${key}=...)`);
  }
  return value;
}

function requireNumber(args, key, label) {
  const value = Number(args[key]);
  if (!Number.isFinite(value)) {
    throw new Error(`${label} must be numeric (--${key}=...)`);
  }
  return value;
}

function requireBoolean(args, key, label) {
  const raw = String(args[key] || "").trim().toLowerCase();
  if (["true", "1", "yes", "y"].includes(raw)) return true;
  if (["false", "0", "no", "n"].includes(raw)) return false;
  throw new Error(`${label} must be true or false (--${key}=true|false)`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const payload = {
    ticketId: requireString(args, "ticket-id", "ticket id"),
    tradeTimestamp: requireString(args, "timestamp", "timestamp"),
    sessionLabel: String(args.session || "Denver Core").trim(),
    symbol: requireString(args, "symbol", "symbol").toUpperCase(),
    regime: requireString(args, "regime", "regime").toLowerCase(),
    setupId: requireString(args, "setup", "setup"),
    side: requireString(args, "side", "side").toLowerCase(),
    setup_match_confirmed: requireBoolean(args, "setup-match-confirmed", "setup match confirmed"),
    headline_lockout_checked: requireBoolean(args, "headline-lockout-checked", "headline lockout checked"),
    maker_limit_plan_confirmed: requireBoolean(args, "maker-limit-plan-confirmed", "maker limit plan confirmed"),
    plannedEntryPrice: requireNumber(args, "entry", "entry"),
    actualEntryPrice: requireNumber(args, "actual-entry", "actual entry"),
    stopPrice: requireNumber(args, "stop", "stop"),
    targetPrice: requireNumber(args, "target", "target"),
    actualExitPrice: requireNumber(args, "actual-exit", "actual exit"),
    orderType: requireString(args, "order-type", "order type"),
    entryLiquidityRole: requireString(args, "entry-liquidity-role", "entry liquidity role"),
    exitLiquidityRole: requireString(args, "exit-liquidity-role", "exit liquidity role"),
    entryFillRatio: requireNumber(args, "entry-fill-ratio", "entry fill ratio"),
    exitFillRatio: requireNumber(args, "exit-fill-ratio", "exit fill ratio"),
    exitReason: requireString(args, "exit-reason", "exit reason").toLowerCase(),
    stopExecutionQuality: requireString(args, "stop-execution-quality", "stop execution quality").toLowerCase(),
    sizeUsd: requireNumber(args, "size-usd", "size usd"),
    feesUsd: requireNumber(args, "fees-usd", "fees usd"),
    spreadSlippageUsd: requireNumber(args, "slippage-usd", "slippage usd"),
    pnlR: requireNumber(args, "pnl-r", "pnl r"),
    pnlUsd: requireNumber(args, "pnl-usd", "pnl usd"),
    screenshotPath: requireString(args, "screenshot", "screenshot"),
    ruleAdherenceScore: requireNumber(args, "rule-adherence", "rule adherence"),
    mistakeTag: requireString(args, "mistake-tag", "mistake tag"),
    note: requireString(args, "note", "note"),
  };

  const result = await appendCryptoProfitabilityJournalEntry(payload);
  console.log(JSON.stringify({
    entry: result.entry,
    summary: result.summary,
  }, null, 2));
}

main().catch((error) => {
  console.error(`daytrading:journal:add failed: ${error instanceof Error ? error.message : "unknown error"}`);
  process.exit(1);
});
