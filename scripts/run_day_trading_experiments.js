const { runDayTradingExperiments, normalizeDayTradingMarket } = require("../src/lib/day-trading");

function parseArgs(argv) {
  const args = {
    market: "crypto",
    bars: "all",
    top: 10,
    strictMarketData: true,
    preset: undefined,
    windowMode: undefined,
  };

  for (const raw of argv) {
    if (raw.startsWith("--bars=")) {
      const value = String(raw.split("=")[1] || "").trim().toLowerCase();
      if (value === "all") args.bars = "all";
      else {
        const numeric = Number(value);
        if (Number.isFinite(numeric) && numeric > 0) args.bars = Math.round(numeric);
      }
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
  const report = await runDayTradingExperiments(args);
  const summary = {
    generatedAt: report.generatedAt,
    market: report.market,
    researchMode: report.researchMode || null,
    windowModesEvaluated: report.windowModesEvaluated || (args.windowMode ? [args.windowMode] : null),
    barsRequested: report.barsRequested ?? args.bars,
    recommendation: report.recommendation,
    nextSprintDefault: report.nextSprintDefault || null,
    strategiesTested: report.strategiesTested,
    controlStrategiesTested: report.controlStrategiesTested ?? null,
    variantsTested: report.variantsTested,
    eligibleVariantCount: report.eligibleVariantCount,
    trustedVariantCount: report.trustedVariantCount,
    untrustedVariantCount: report.untrustedVariantCount,
    preset: report.preset || args.preset || null,
    marketDataUsage: report.marketDataUsage || null,
    tradeCountBySymbol: report.tradeCountBySymbol || {},
    tradeCountByWindowMode: report.tradeCountByWindowMode || {},
    pnlShareBySymbol: report.pnlShareBySymbol || {},
    pnlShareByWindowMode: report.pnlShareByWindowMode || {},
    phaseA: report.phaseA ? {
      familyWindowReviews: report.phaseA.familyWindowReviews,
      controlCount: Array.isArray(report.phaseA.controlResults) ? report.phaseA.controlResults.length : 0,
    } : null,
    phaseB: report.phaseB ? {
      unlocked: report.phaseB.unlocked,
      selectedFamilyWindow: report.phaseB.selectedFamilyWindow,
      selectedControlStrategyId: report.phaseB.selectedControlStrategyId,
      batchShape: report.phaseB.batchShape,
      resultCount: Array.isArray(report.phaseB.results) ? report.phaseB.results.length : 0,
    } : null,
    leaders: report.leaders.map((item) => ({
      variantId: item.variantId,
      strategyId: item.strategyId || item.baseStrategyId,
      baseStrategyId: item.baseStrategyId,
      symbol: item.symbol,
      strategyFamily: item.strategyFamily,
      windowMode: item.windowMode || null,
      parameters: item.parameters,
      challengerKind: item.challengerKind || null,
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
