const { getDayTradingSnapshot } = require("../src/lib/day-trading");

function main() {
  const snapshot = getDayTradingSnapshot({ market: "crypto" });
  const pilot = snapshot.pilotSummary || {};
  const plan = snapshot.operatingPlan || {};

  const summary = {
    generatedAt: snapshot.generatedAt,
    profitabilityProfileId: snapshot.profitabilityProfileId || null,
    market: snapshot.market,
    marketLabel: snapshot.marketLabel,
    activeSetup: plan.activeSetupLabel || null,
    objective: plan.objective || null,
    defaultRegimeBias: plan.defaultRegimeBias || null,
    session: plan.session || null,
    instruments: plan.instruments || null,
    risk: plan.risk || null,
    dailyTradeCap: plan.dailyTradeCap || null,
    preTradeChecklist: plan.preTradeChecklist || [],
    progress: pilot.progress || null,
    reviewCheckpointTrades: pilot.reviewCheckpointTrades || null,
    advanceGateTrades: pilot.advanceGateTrades || null,
    todayGate: pilot.todayGate || null,
    milestones: pilot.milestones || [],
    journalStats: pilot.journalStats || null,
    disqualificationReasons: pilot.disqualificationReasons || [],
    executionStats: pilot.executionStats || null,
    gates: pilot.gates || [],
    nextUnlock: pilot.nextUnlock || null,
    journalPath: snapshot.profitabilityJournal?.path || null,
    ticketPath: snapshot.profitabilityJournal?.ticketPath || null,
    journalFields: snapshot.profitabilityJournal?.schema || [],
  };

  console.log(JSON.stringify(summary, null, 2));
}

try {
  main();
} catch (error) {
  console.error(`daytrading:pilot failed: ${error instanceof Error ? error.message : "unknown error"}`);
  process.exit(1);
}
