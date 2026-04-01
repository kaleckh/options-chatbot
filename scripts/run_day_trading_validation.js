const { runDayTradingValidation } = require("../src/lib/day-trading/engine");

function parseArgs(argv) {
  const args = {
    bars: 780,
    startingCash: 10000,
  };

  for (const raw of argv) {
    if (raw.startsWith("--bars=")) {
      args.bars = Math.max(48, Number(raw.split("=")[1]) || args.bars);
    }
    if (raw.startsWith("--startingCash=")) {
      args.startingCash = Math.max(1000, Number(raw.split("=")[1]) || args.startingCash);
    }
  }

  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const report = await runDayTradingValidation(args);
  const summary = {
    generatedAt: report.generatedAt,
    strategiesScanned: report.strategiesScanned,
    leaders: report.scoreboard.leaders.map((item) => ({
      strategyId: item.strategyId,
      status: item.status,
      score: item.score,
      backtestReturn: item.backtest?.totalNetReturnFraction ?? null,
      paperPnl: item.paper?.realizedPnl ?? null,
      vetoReasons: item.vetoReasons,
    })),
    paperAccount: report.paperAccount,
  };

  console.log(JSON.stringify(summary, null, 2));
}

main().catch((err) => {
  console.error(`daytrading:validate failed: ${err.message}`);
  process.exit(1);
});
