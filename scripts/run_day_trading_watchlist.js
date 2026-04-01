const { buildMorningWatchlist } = require("../src/lib/day-trading/engine");

function parseArgs(argv) {
  const args = {
    bars: undefined,
    limit: undefined,
  };

  for (const raw of argv) {
    if (raw.startsWith("--bars=")) {
      const value = Number(raw.split("=")[1]);
      if (Number.isFinite(value) && value > 0) args.bars = value;
    }
    if (raw.startsWith("--limit=")) {
      const value = Number(raw.split("=")[1]);
      if (Number.isFinite(value) && value > 0) args.limit = value;
    }
  }

  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const watchlist = await buildMorningWatchlist(args);
  const summary = {
    generatedAt: watchlist.generatedAt,
    morningWindow: watchlist.morningWindow,
    selectedStrategies: watchlist.selectedStrategies,
    notifyNowCount: watchlist.notifyNowCount,
    items: watchlist.items.map((item) => ({
      strategyId: item.strategyId,
      symbol: item.symbol,
      liveStatus: item.liveStatus,
      notifyNow: item.notifyNow,
      alertEligible: item.alertEligible,
      currentDataTrusted: item.currentDataTrusted,
      barAgeMinutes: item.barAgeMinutes,
      currentSignalValue: item.currentSignalValue,
      signalThreshold: item.signalThreshold,
      winRate: item.replayEvidence?.winRate ?? null,
      profitFactor: item.replayEvidence?.profitFactor ?? null,
      tradeCount: item.replayEvidence?.tradeCount ?? null,
      latestSignalTimestamp: item.latestSignalTimestamp,
      marketDataSource: item.marketDataSource,
      marketDataWarning: item.marketDataWarning,
    })),
  };

  console.log(JSON.stringify(summary, null, 2));
}

main().catch((err) => {
  console.error(`daytrading:watch failed: ${err.message}`);
  process.exit(1);
});
