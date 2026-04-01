const { runDayTradingExperiments } = require("../src/lib/day-trading/engine");

function parseArgs(argv) {
  const args = {
    bars: undefined,
    top: 10,
    strictMarketData: true,
    preset: undefined,
  };

  for (const raw of argv) {
    if (raw.startsWith("--bars=")) {
      const value = Number(raw.split("=")[1]);
      if (Number.isFinite(value) && value > 0) args.bars = value;
    }
    if (raw.startsWith("--top=")) {
      const value = Number(raw.split("=")[1]);
      if (Number.isFinite(value) && value > 0) args.top = Math.round(value);
    }
    if (raw === "--allow-fallback") {
      args.strictMarketData = false;
    }
    if (raw.startsWith("--preset=")) {
      const value = String(raw.split("=")[1] || "").trim();
      if (value) args.preset = value;
    }
  }

  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const report = await runDayTradingExperiments(args);
  const summary = {
    generatedAt: report.generatedAt,
    recommendation: report.recommendation,
    strategiesTested: report.strategiesTested,
    variantsTested: report.variantsTested,
    eligibleVariantCount: report.eligibleVariantCount,
    trustedVariantCount: report.trustedVariantCount,
    untrustedVariantCount: report.untrustedVariantCount,
    preset: report.preset || null,
    baseStrategies: report.baseStrategies,
    leaders: report.leaders.map((item) => ({
      variantId: item.variantId,
      baseStrategyId: item.baseStrategyId,
      symbol: item.symbol,
      strategyFamily: item.strategyFamily,
      parameters: item.parameters,
      trustedMarketData: item.trustedMarketData,
      marketDataSource: item.marketDataSource,
      totalNetReturnFraction: item.summary?.totalNetReturnFraction ?? null,
      winRate: item.summary?.winRate ?? null,
      profitFactor: item.summary?.profitFactor ?? null,
      tradeCount: item.summary?.tradeCount ?? null,
      eligibleForPromotion: item.summary?.eligibleForPromotion ?? null,
      vetoReasons: item.summary?.vetoReasons ?? [],
      experimentScore: item.experimentScore,
    })),
  };

  console.log(JSON.stringify(summary, null, 2));
}

main().catch((err) => {
  console.error(`daytrading:experiments failed: ${err.message}`);
  process.exit(1);
});
