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
    progress: pilot.progress || null,
    journalStats: pilot.journalStats || null,
    gates: pilot.gates || [],
    nextUnlock: pilot.nextUnlock || null,
    journalPath: snapshot.profitabilityJournal?.path || null,
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
