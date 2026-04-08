#!/usr/bin/env node
/**
 * Polymarket Trading Bot — Entry Point
 *
 * Usage:
 *   node scripts/polymarket-run.js                    # Scan mode (default, no auth)
 *   node scripts/polymarket-run.js --mode=dry-run     # Simulate orders (needs credentials)
 *   node scripts/polymarket-run.js --mode=live        # Real trading (needs credentials + USDC)
 *   node scripts/polymarket-run.js --loop             # Continuous scanning
 *   node scripts/polymarket-run.js --loop --mode=live # Continuous live trading
 *
 * Credentials:
 *   Create data/polymarket/credentials.json:
 *   {
 *     "privateKey": "0xYOUR_POLYGON_WALLET_PRIVATE_KEY",
 *     "funderAddress": "0xYOUR_WALLET_ADDRESS"
 *   }
 *
 * The bot will derive Polymarket API keys from your wallet on first run.
 */

const { Orchestrator } = require("../src/lib/polymarket");

const args = process.argv.slice(2);
const flags = {};
for (const arg of args) {
  if (arg.startsWith("--")) {
    const [key, val] = arg.slice(2).split("=");
    flags[key] = val || "true";
  }
}

const mode = flags.mode || "scan";
const loop = flags.loop === "true";

const config = {
  mode,
  scanIntervalMs: Number(flags.interval || 60) * 1000,
  mmEnabled: flags.mm !== "false",
  arbEnabled: flags.arb !== "false",
  arbMinProfitPct: Number(flags.arbMinProfit || 0.05),
  mmMinVolume24h: Number(flags.mmMinVol || 10000),
  mmMaxMarkets: Number(flags.mmMax || 5),
  arbMaxExecutions: Number(flags.arbMax || 3),
  risk: {
    maxTotalExposureUsd: Number(flags.maxExposure || 1000),
    maxSinglePositionUsd: Number(flags.maxPosition || 200),
    maxDailyLossUsd: Number(flags.maxDailyLoss || 100),
  },
};

console.log("Polymarket Trading Bot");
console.log("Mode: " + mode + (loop ? " (continuous)" : " (single scan)"));
console.log("");

async function main() {
  const orchestrator = new Orchestrator(config);

  try {
    await orchestrator.initialize();
  } catch (err) {
    if (mode === "scan") {
      console.log("No credentials needed for scan mode.\n");
    } else {
      console.error("Initialization failed: " + err.message);
      process.exit(1);
    }
  }

  if (loop) {
    // Handle graceful shutdown
    process.on("SIGINT", () => {
      console.log("\nShutting down...");
      orchestrator.stop();
    });
    process.on("SIGTERM", () => {
      orchestrator.stop();
    });

    await orchestrator.runLoop();
  } else {
    const report = await orchestrator.runOnce();
    console.log("\nFinal report:");
    console.log(JSON.stringify(report, null, 2));
  }
}

main().catch((err) => {
  console.error("Fatal:", err.message);
  process.exit(1);
});
