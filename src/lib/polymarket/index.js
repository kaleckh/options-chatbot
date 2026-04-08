/**
 * Polymarket Trading System — Main Orchestrator
 *
 * Combines scanner, market-maker, and arb engine into a single
 * run loop that scans for opportunities and executes trades.
 *
 * Modes:
 *   scan    - Scan only, report opportunities (no auth needed)
 *   dry-run - Full pipeline with order simulation (needs auth)
 *   live    - Real order placement (needs auth + funded wallet)
 */

const { scan } = require("./scanner");
const { MarketMaker } = require("./market-maker");
const { ArbEngine } = require("./arb-engine");
const { RiskManager } = require("./risk");
const { createAuthenticatedClient, loadState, saveState } = require("./client");

const DEFAULT_ORCHESTRATOR_CONFIG = {
  mode: "scan",                    // "scan", "dry-run", "live"
  scanIntervalMs: 60000,           // Re-scan every 60s
  mmEnabled: true,                 // Enable market-making
  arbEnabled: true,                // Enable arbitrage
  mmMaxMarkets: 5,                 // Max markets for MM
  arbMaxExecutions: 3,             // Max arb executions per scan cycle
  arbMinProfitPct: 0.05,           // Min 5% profit to execute arb
  mmMinVolume24h: 10000,           // Min daily volume for MM targets
  risk: {},                        // Risk manager overrides
  mm: {},                          // Market-maker overrides
  arb: {},                         // Arb engine overrides
};

class Orchestrator {
  constructor(options = {}) {
    this.config = { ...DEFAULT_ORCHESTRATOR_CONFIG, ...options };
    this.risk = new RiskManager(this.config.risk);
    this.mm = new MarketMaker(this.risk, this.config.mm);
    this.arb = new ArbEngine(this.risk, {
      ...this.config.arb,
      dryRun: this.config.mode !== "live",
    });
    this.client = null;
    this.running = false;
    this.cycleCount = 0;
    this.lastScan = null;
  }

  async initialize() {
    if (this.config.mode !== "scan") {
      console.log("Initializing authenticated client...");
      const auth = await createAuthenticatedClient();
      this.client = auth.client;
      console.log("Authenticated as: " + auth.address);

      // Check balance
      try {
        const balance = await this.client.getBalanceAllowance({ asset_type: "USDC" });
        console.log("USDC balance: $" + (Number(balance?.balance || 0) / 1e6).toFixed(2));
      } catch (err) {
        console.log("Could not fetch balance: " + err.message);
      }
    }
    console.log("Mode: " + this.config.mode);
    console.log("Risk limits: " + JSON.stringify(this.risk.config));
    console.log("");
  }

  async runOnce() {
    this.cycleCount++;
    console.log("\n--- Cycle " + this.cycleCount + " [" + new Date().toISOString() + "] ---\n");

    // Step 1: Scan
    const scanResult = await scan({
      mmMinVolume24h: this.config.mmMinVolume24h,
    });
    this.lastScan = scanResult;

    console.log("Scan: " + scanResult.eventCount + " events, " + scanResult.marketCount + " markets");
    console.log("  Arbs: " + scanResult.arbs.executable + " executable");
    console.log("  MM: " + scanResult.marketMaking.total + " opportunities");

    // Step 2: Execute arbs (if enabled)
    if (this.config.arbEnabled && scanResult.arbs.executable > 0) {
      console.log("\n[ARB] Processing top opportunities...");
      const topArbs = scanResult.arbs.items
        .filter((a) => a.executable && a.arbProfit >= this.config.arbMinProfitPct)
        .slice(0, this.config.arbMaxExecutions);

      for (const arb of topArbs) {
        const result = await this.arb.evaluateAndExecute(this.client, arb);
        console.log("  " + arb.title.slice(0, 45) + ": " + result.status);
      }
    }

    // Step 3: Update market-maker targets (if enabled)
    if (this.config.mmEnabled && this.config.mode !== "scan") {
      const topMM = scanResult.marketMaking.items
        .filter((m) => m.volume24h >= this.config.mmMinVolume24h)
        .slice(0, this.config.mmMaxMarkets);

      // Add new markets
      for (const opp of topMM) {
        if (!this.mm.activeMarkets.has(opp.yesTokenId)) {
          this.mm.addMarket(opp);
        }
      }

      // Run MM cycle
      if (this.mm.activeMarkets.size > 0) {
        console.log("\n[MM] Quoting " + this.mm.activeMarkets.size + " markets...");
        const mmResult = await this.mm.runCycle(this.client);
        for (const r of (mmResult?.results || [])) {
          if (r.actions?.length > 0) {
            const actionStr = r.actions.map((a) => a.side + "@" + (a.price || "err")).join(", ");
            console.log("  " + (r.question || "").slice(0, 40) + ": " + actionStr);
          }
        }
      }
    }

    // Step 4: Report
    const report = {
      cycle: this.cycleCount,
      timestamp: new Date().toISOString(),
      mode: this.config.mode,
      risk: this.risk.getStatus(),
      arb: this.arb.getStats(),
      mm: this.mm.getStats(),
      scan: {
        events: scanResult.eventCount,
        executableArbs: scanResult.arbs.executable,
        mmOpportunities: scanResult.marketMaking.total,
      },
    };

    // Save state
    if (this.config.mode !== "scan") {
      saveState({
        ...loadState(),
        lastCycle: report,
        lastScanAt: scanResult.scannedAt,
      });
    }

    return report;
  }

  async runLoop() {
    this.running = true;
    console.log("Starting run loop (interval: " + (this.config.scanIntervalMs / 1000) + "s)...\n");

    while (this.running) {
      try {
        const report = await this.runOnce();
        this._printSummary(report);
      } catch (err) {
        console.error("Cycle error:", err.message);
      }

      if (this.running) {
        await new Promise((r) => setTimeout(r, this.config.scanIntervalMs));
      }
    }
  }

  stop() {
    this.running = false;
    console.log("Stopping...");
  }

  _printSummary(report) {
    console.log("\n  Summary: " +
      "arbs=" + report.arb.executed + "/" + report.arb.attempted +
      " mm_markets=" + report.mm.activeMarkets +
      " exposure=$" + report.risk.totalExposure.toFixed(2) +
      " daily_pnl=$" + report.risk.dailyPnl.toFixed(2) +
      (report.risk.killed ? " [KILLED]" : "")
    );
  }
}

module.exports = { Orchestrator, DEFAULT_ORCHESTRATOR_CONFIG };
