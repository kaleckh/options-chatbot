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

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const payload = {
    tradeTimestamp: requireString(args, "timestamp", "timestamp"),
    sessionLabel: String(args.session || "Denver Core").trim(),
    symbol: requireString(args, "symbol", "symbol").toUpperCase(),
    regime: requireString(args, "regime", "regime").toLowerCase(),
    setupId: requireString(args, "setup", "setup"),
    side: requireString(args, "side", "side").toLowerCase(),
    plannedEntryPrice: requireNumber(args, "entry", "entry"),
    stopPrice: requireNumber(args, "stop", "stop"),
    targetPrice: requireNumber(args, "target", "target"),
    orderType: requireString(args, "order-type", "order type"),
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
