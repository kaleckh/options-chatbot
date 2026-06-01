const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function loadPositionEvidenceModule() {
  const sourcePath = path.join(__dirname, "..", "..", "src", "lib", "trading-desk", "positionEvidence.ts");
  const source = fs.readFileSync(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      esModuleInterop: true,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: sourcePath,
  }).outputText;
  const module = { exports: {} };

  vm.runInNewContext(
    transpiled,
    {
      console,
      exports: module.exports,
      module,
      require,
    },
    { filename: sourcePath }
  );

  return module.exports;
}

const evidence = loadPositionEvidenceModule();

function closedPosition(overrides = {}) {
  return {
    id: "position-1",
    ticker: "SPY",
    status: "closed",
    direction: "call",
    contracts: 1,
    entry_execution_price: 1,
    exit_execution_price: 1.3,
    exit_execution_basis: "spread_bid_ask_exact",
    source_pick_snapshot: {},
    ...overrides,
  };
}

test("production live exact rows qualify for truth-grade closed outcomes", () => {
  const position = closedPosition({
    proof_class: "live_scan_exact_contract",
  });

  assert.equal(evidence.getPositionEvidenceGroup(position).id, "live_exact");
  assert.equal(evidence.isProductionProofPosition(position), true);
  assert.equal(evidence.isTruthGradeClosedPosition(position), true);
});

test("migrated historical paper rows stay out of production and truth-grade views", () => {
  const position = closedPosition({
    proof_eligible: true,
    source_pick_snapshot: {
      position_migration_id: "migration-1",
    },
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "historical_paper");
  assert.equal(group.productionProof, false);
  assert.equal(group.researchLearning, true);
  assert.equal(evidence.isProductionProofPosition(position), false);
  assert.equal(evidence.isRealizedPnlClosedPosition(position), true);
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
  assert.equal(evidence.matchesClosedDataView(position, "realized_pnl"), true);
  assert.equal(evidence.matchesClosedDataView(position, "historical_paper"), true);
});

test("compact evidence summary preserves closed-row provenance without bulky source fields", () => {
  const position = closedPosition({
    proof_eligible: true,
    source_pick_snapshot: {
      playbook_id: "short_term",
    },
    compact_evidence: {
      migrated_paper: true,
      research_backfill: true,
    },
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "historical_paper");
  assert.equal(group.productionProof, false);
  assert.equal(evidence.matchesClosedDataView(position, "historical_paper"), true);
  assert.equal(evidence.matchesClosedDataView(position, "truth_grade"), false);
});

test("research backfill rows with trusted executable exits enter realized P&L but not truth-grade", () => {
  const position = closedPosition({
    proof_eligible: true,
    source_pick_snapshot: {
      backfill_audit_id: "audit-1",
      research_only: true,
    },
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "research_backfill");
  assert.equal(group.productionProof, false);
  assert.equal(group.researchLearning, true);
  assert.equal(evidence.hasTrustedExecutableExit(position), true);
  assert.ok(Math.abs(evidence.getRealizedPnlPct(position) - 30) < 0.000001);
  assert.equal(evidence.isRealizedPnlClosedPosition(position), true);
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
  assert.equal(evidence.matchesClosedDataView(position, "realized_pnl"), true);
  assert.equal(evidence.matchesClosedDataView(position, "truth_grade"), false);
  assert.equal(evidence.matchesClosedDataView(position, "research_backfill"), true);
});

test("current policy view separates rows still allowed from learned-away guardrail hits", () => {
  const currentPolicyRow = closedPosition({
    ticker: "ORCL",
    source_pick_snapshot: {
      playbook_id: "short_term",
      spread_width: 10,
      net_debit: 3,
      ret5: 0,
    },
  });
  const learnedAwayRow = closedPosition({
    ticker: "MSFT",
    source_pick_snapshot: {
      playbook_id: "short_term",
      spread_width: 10,
      net_debit: 5,
      ret5: 0,
    },
  });
  const bullishPullbackRejected = closedPosition({
    ticker: "SPY",
    source_pick_snapshot: {
      playbook_id: "bullish_pullback_observation",
      spread_width: 10,
      net_debit: 3,
      ret5: 0,
    },
  });

  assert.equal(evidence.getCurrentPolicyReplayState(currentPolicyRow).id, "would_take_today");
  assert.equal(evidence.matchesClosedDataView(currentPolicyRow, "current_policy"), true);
  assert.equal(evidence.matchesClosedDataView(currentPolicyRow, "learned_away"), false);

  assert.equal(evidence.getCurrentPolicyReplayState(learnedAwayRow).id, "blocked_by_current_policy");
  assert.deepEqual(Array.from(evidence.currentPolicyGuardrailHits(learnedAwayRow)), ["debit_gt_45_width"]);
  assert.equal(evidence.matchesClosedDataView(learnedAwayRow, "current_policy"), false);
  assert.equal(evidence.matchesClosedDataView(learnedAwayRow, "learned_away"), true);

  assert.equal(evidence.getCurrentPolicyReplayState(bullishPullbackRejected).id, "blocked_by_current_policy");
  assert.deepEqual(Array.from(evidence.currentPolicyGuardrailHits(bullishPullbackRejected)), [
    "bullish_pullback_not_keep_bucket",
  ]);
});

test("current policy cohort health keeps April showcase separate from recent break", () => {
  const cohort = [
    closedPosition({ id: "apr-1", ticker: "AMD", filled_at: "2026-04-13T14:30:00Z", net_pnl_pct: 110 }),
    closedPosition({ id: "apr-2", ticker: "AMZN", filled_at: "2026-04-14T14:30:00Z", net_pnl_pct: 70 }),
    closedPosition({ id: "apr-3", ticker: "QQQ", filled_at: "2026-04-15T14:30:00Z", net_pnl_pct: 82 }),
    closedPosition({ id: "apr-4", ticker: "MSFT", filled_at: "2026-04-16T14:30:00Z", net_pnl_pct: 65 }),
    closedPosition({ id: "apr-5", ticker: "AAPL", filled_at: "2026-04-17T14:30:00Z", net_pnl_pct: 95 }),
    closedPosition({ id: "may-1", ticker: "TSLA", filled_at: "2026-05-13T14:30:00Z", net_pnl_pct: 20 }),
    closedPosition({ id: "may-2", ticker: "QQQ", filled_at: "2026-05-14T14:30:00Z", net_pnl_pct: 10 }),
    closedPosition({ id: "may-3", ticker: "WMT", filled_at: "2026-05-20T14:30:00Z", net_pnl_pct: -99 }),
    closedPosition({ id: "may-4", ticker: "GOOGL", filled_at: "2026-05-21T14:30:00Z", net_pnl_pct: -83 }),
    closedPosition({ id: "may-5", ticker: "UNH", filled_at: "2026-05-22T14:30:00Z", net_pnl_pct: -63 }),
  ].map((position) => ({
    ...position,
    source_pick_snapshot: {
      playbook_id: "short_term",
      spread_width: 10,
      net_debit: 3,
      ret5: 0,
    },
  }));

  const health = evidence.buildCurrentPolicyCohortHealth(cohort);

  assert.equal(health.showcaseMonth.key, "2026-04");
  assert.equal(health.showcaseMonth.status, "healthy");
  assert.equal(health.recentMonth.key, "2026-05");
  assert.equal(health.recentMonth.status, "paper_only_recent_break");
  assert.equal(health.recentWeek.key, "2026-W21");
  assert.equal(health.recentWeek.status, "paper_only_recent_break");
  assert.equal(health.overallStatus, "paper_only_recent_week_break");
  assert.equal(evidence.policyCohortHealthStatusLabel(health.overallStatus), "Paper-only");
});

test("lifecycle-only and untrusted mark exits are excluded from truth-grade", () => {
  const lifecycleOnly = closedPosition({
    exit_execution_price: null,
    exit_option_price: null,
    latest_review: {
      exit_execution_price: null,
    },
  });
  const markExit = closedPosition({
    exit_execution_basis: "mark",
  });

  assert.equal(evidence.getPositionEvidenceGroup(lifecycleOnly).id, "lifecycle_only");
  assert.equal(evidence.isRealizedPnlClosedPosition(lifecycleOnly), false);
  assert.equal(evidence.isTruthGradeClosedPosition(lifecycleOnly), false);
  assert.equal(evidence.hasTrustedExecutableExit(markExit), false);
  assert.equal(evidence.isRealizedPnlClosedPosition(markExit), false);
  assert.equal(evidence.isTruthGradeClosedPosition(markExit), false);
  assert.equal(evidence.matchesClosedDataView(markExit, "realized_pnl"), false);
  assert.equal(evidence.matchesClosedDataView(markExit, "unpriced"), true);
});

test("fee-adjusted net P&L uses fees in numerator and denominator", () => {
  assert.equal(
    evidence.calcNetOptionPnlPct({
      contracts: 1,
      entryPrice: 1,
      exitPrice: 1.3,
      feeTotalUsd: 2,
    }),
    (28 / 102) * 100
  );
});

test("open SELL state distinguishes executable close evidence from display-only marks", () => {
  const displayOnlySell = {
    id: "open-1",
    status: "open",
    ticker: "SBUX",
    direction: "call",
    contracts: 1,
    entry_option_price: 1,
    last_recommendation: "SELL",
    latest_review: {
      reviewed_at: "2026-05-31T18:00:00Z",
      recommendation: "SELL",
      current_option_price: 0.47,
      exit_execution_price: null,
      exit_execution_basis: null,
      reason: "Indicator exit triggered.",
      warnings: ["Using display-only spread marks."],
      metrics_snapshot: {
        pricing_state: "priced_display_only_last",
        price_trigger_ok: false,
      },
    },
    source_pick_snapshot: {},
  };

  const executableSell = {
    ...displayOnlySell,
    id: "open-2",
    latest_review: {
      ...displayOnlySell.latest_review,
      exit_execution_price: 0,
      exit_execution_basis: "spread_bid_ask_exact",
      metrics_snapshot: {
        price_trigger_ok: true,
      },
    },
  };

  assert.equal(evidence.hasExecutableLatestReviewExit(displayOnlySell), false);
  assert.equal(evidence.getOpenReviewActionState(displayOnlySell).id, "non_executable_sell");
  assert.equal(evidence.getOpenReviewActionState(displayOnlySell).label, "Review quote");
  assert.equal(evidence.hasExecutableLatestReviewExit(executableSell), true);
  assert.equal(evidence.getOpenReviewActionState(executableSell).id, "executable_sell");
  assert.equal(evidence.getOpenReviewActionState(executableSell).label, "Close now");
});
