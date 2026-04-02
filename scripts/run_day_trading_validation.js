const { getDayTradingSnapshot, runDayTradingValidation, normalizeDayTradingMarket } = require("../src/lib/day-trading");

function parseArgs(argv) {
  const args = {
    market: "crypto",
    bars: "all",
    startingCash: 10000,
    windowMode: "scheduled_windows",
  };

  for (const raw of argv) {
    if (raw.startsWith("--bars=")) {
      const value = String(raw.split("=")[1] || "").trim().toLowerCase();
      if (value === "all") args.bars = "all";
      else {
        const numeric = Number(value);
        if (Number.isFinite(numeric) && numeric > 0) args.bars = Math.max(48, Math.round(numeric));
      }
    }
    if (raw.startsWith("--startingCash=")) {
      args.startingCash = Math.max(1000, Number(raw.split("=")[1]) || args.startingCash);
    }
    if (raw.startsWith("--window-mode=")) {
      const value = String(raw.split("=")[1] || "").trim();
      if (value) args.windowMode = value;
    }
    if (raw.startsWith("--market=")) {
      args.market = normalizeDayTradingMarket(raw.split("=")[1]);
    }
  }

  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const report = await runDayTradingValidation(args);
  const snapshot = getDayTradingSnapshot({ market: args.market });
  const summary = {
    generatedAt: report.generatedAt,
    profitabilityProfileId: report.profitabilityProfileId || null,
    market: report.market,
    windowMode: report.windowMode || args.windowMode,
    barsRequested: report.barsRequested ?? args.bars,
    strategiesScanned: report.strategiesScanned,
    marketDataUsage: report.marketDataUsage || null,
    tradeCountBySymbol: report.tradeCountBySymbol || {},
    tradeCountByWindowMode: report.tradeCountByWindowMode || {},
    pnlShareBySymbol: report.pnlShareBySymbol || {},
    pnlShareByWindowMode: report.pnlShareByWindowMode || {},
    leaders: report.scoreboard.leaders.map((item) => ({
      strategyId: item.strategyId,
      status: item.status,
      score: item.score,
      backtestReturn: item.backtest?.totalNetReturnFraction ?? null,
      paperPnl: item.paper?.realizedPnl ?? null,
      vetoReasons: item.vetoReasons,
    })),
    paperAccount: report.paperAccount,
    pilotSummary: snapshot.pilotSummary || null,
  };

  console.log(JSON.stringify(summary, null, 2));
}

main().catch((err) => {
  console.error(`daytrading:validate failed: ${err.message}`);
  process.exit(1);
});
