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
  const localRequire = (specifier) => {
    if (specifier === "@/lib/trading-desk/proofContract") {
      return loadProofContractModule();
    }
    return require(specifier);
  };

  vm.runInNewContext(
    transpiled,
    {
      console,
      exports: module.exports,
      module,
      require: localRequire,
    },
    { filename: sourcePath }
  );

  return module.exports;
}

function loadProofContractModule() {
  const sourcePath = path.join(__dirname, "..", "..", "src", "lib", "trading-desk", "proofContract.ts");
  const source = fs.readFileSync(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      esModuleInterop: true,
      module: ts.ModuleKind.CommonJS,
      resolveJsonModule: true,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: sourcePath,
  }).outputText;
  const module = { exports: {} };
  const localRequire = (specifier) => {
    if (specifier === "@/lib/generated/proofEvidenceContract") {
      return loadGeneratedProofEvidenceContractModule();
    }
    return require(specifier);
  };

  vm.runInNewContext(
    transpiled,
    {
      console,
      exports: module.exports,
      module,
      require: localRequire,
    },
    { filename: sourcePath }
  );

  return module.exports;
}

function loadGeneratedProofEvidenceContractModule() {
  const sourcePath = path.join(__dirname, "..", "..", "src", "lib", "generated", "proofEvidenceContract.ts");
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
const proofContract = loadProofContractModule();

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

function liveExactClosedPosition(overrides = {}) {
  const sourceOverrides = overrides.source_pick_snapshot || {};
  const rest = { ...overrides };
  delete rest.source_pick_snapshot;
  return closedPosition({
    proof_eligible: true,
    proof_class: "live_scan_exact_contract",
    contract_symbol: "SPY260619C00600000",
    entry_execution_price: 1,
    entry_execution_basis: "ask",
    source_scan_session_id: 55,
    source_scan_event_key: "short_term:rank_1",
    source_scan_run_id: "api_scan_20260406T100000Z",
    source_scan_recorded_at_utc: "2026-04-06T14:00:00Z",
    source_pick_snapshot: {
      selection_source: "live_chain_exact_contract",
      options_data_source: "alpaca_opra",
      quote_time_et: "2026-04-06T10:00:00-04:00",
      quote_freshness_status: "fresh",
      entry_execution_price: 1,
      entry_execution_basis: "ask",
      source_scan_lineage_verified: true,
      ...sourceOverrides,
    },
    ...rest,
  });
}

test("proof contract declares production group and display precedence", () => {
  assert.deepEqual(Array.from(proofContract.PRODUCTION_EVIDENCE_GROUP_IDS), ["live_exact"]);
  assert.deepEqual(Array.from(proofContract.EVIDENCE_DISPLAY_PRECEDENCE), [
    "lifecycle_only",
    "historical_paper",
    "research_backfill",
    "proof_ineligible",
    "manual_exact",
    "live_exact",
    "legacy_unclassified",
  ]);
  assert.equal(proofContract.PROOF_CLASSES.liveScanExact, "live_scan_exact_contract");
  assert.equal(proofContract.REQUIRED_LIVE_SELECTION_SOURCE, "live_chain_exact_contract");
  assert.ok(proofContract.REQUIRED_SOURCE_SCAN_LINEAGE_FIELDS.includes("source_scan_event_key"));
  assert.ok(proofContract.RESEARCH_BACKFILL_IDENTITY_FIELDS.includes("backfill_audit_id"));
  assert.equal(proofContract.QUOTE_FRESHNESS_REQUIRED, true);
  assert.ok(proofContract.UNTRUSTED_QUOTE_FRESHNESS_TOKENS.includes("stale"));
});

test("production live exact rows qualify for truth-grade closed outcomes", () => {
  const position = liveExactClosedPosition();

  assert.equal(evidence.getPositionEvidenceGroup(position).id, "live_exact");
  assert.equal(evidence.isProductionProofPosition(position), true);
  assert.equal(evidence.isTruthGradeClosedPosition(position), true);
});

test("live exact rows can carry research profitability calibration labels", () => {
  const position = liveExactClosedPosition({
    source_pick_snapshot: {
      pricing_evidence_class: "proof_live_opra_exact_contract",
      profitability_evidence_class: "research_profitability_calibration",
      source_separation: "pricing_proof_profitability_research",
      promotion_class: "research_bootstrap",
    },
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "live_exact");
  assert.equal(group.productionProof, true);
  assert.equal(evidence.isProductionProofPosition(position), true);
  assert.equal(evidence.isTruthGradeClosedPosition(position), true);
});

test("bare live proof class without persisted entry proof gates is not production proof", () => {
  const position = closedPosition({
    proof_eligible: true,
    proof_class: "live_scan_exact_contract",
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "proof_ineligible");
  assert.equal(group.productionProof, false);
  assert.equal(evidence.isProductionProofPosition(position), false);
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
});

test("stale quote freshness blocks frontend production proof", () => {
  const position = liveExactClosedPosition({
    source_pick_snapshot: {
      quote_freshness_status: "stale",
    },
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "proof_ineligible");
  assert.equal(group.productionProof, false);
  assert.equal(evidence.isProductionProofPosition(position), false);
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
});

test("missing quote freshness blocks frontend production proof", () => {
  const position = liveExactClosedPosition({
    source_pick_snapshot: {
      quote_freshness_status: null,
    },
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "proof_ineligible");
  assert.equal(group.productionProof, false);
  assert.equal(evidence.isProductionProofPosition(position), false);
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
});

test("research identity fields block frontend production proof even with opaque ids", () => {
  const position = liveExactClosedPosition({
    source_pick_snapshot: {
      backfill_audit_id: "audit-1",
    },
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "research_backfill");
  assert.equal(group.productionProof, false);
  assert.equal(evidence.isProductionProofPosition(position), false);
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
});

test("top-level research_only blocks frontend production proof", () => {
  const position = liveExactClosedPosition({
    research_only: true,
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "research_backfill");
  assert.equal(group.productionProof, false);
  assert.equal(evidence.isProductionProofPosition(position), false);
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
});

test("manual exact rows are visible but not production proof", () => {
  const position = closedPosition({
    proof_class: "manual_broker_exact_contract",
    proof_eligible: false,
    exit_execution_basis: "broker_fill",
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "manual_exact");
  assert.equal(group.productionProof, false);
  assert.equal(evidence.hasTrustedExecutableExit(position), true);
  assert.equal(evidence.isRealizedPnlClosedPosition(position), true);
  assert.equal(evidence.isProductionProofPosition(position), false);
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
});

test("stale proof eligible flags without live proof class do not become production proof", () => {
  const position = closedPosition({
    proof_eligible: true,
    source_pick_snapshot: {
      options_data_source: "alpaca_opra",
    },
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "legacy_unclassified");
  assert.equal(group.productionProof, false);
  assert.equal(evidence.isProductionProofPosition(position), false);
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
});

test("manual closes without broker or executable bid ask evidence are not trusted exits", () => {
  const position = closedPosition({
    proof_class: "live_scan_exact_contract",
    exit_execution_basis: "manual_close",
  });

  assert.equal(evidence.hasTrustedExecutableExit(position), false);
  assert.equal(evidence.isRealizedPnlClosedPosition(position), false);
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
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

test("current compact backend readback can classify live exact after display compaction", () => {
  const position = closedPosition({
    proof_eligible: true,
    proof_class: "live_scan_exact_contract",
    compact_evidence: {
      proof_contract_version: proofContract.PROOF_EVIDENCE_CONTRACT_VERSION,
      evidence_group: "live_exact",
      production_proof: true,
      quote_evidence_class: "trusted_intraday_opra_nbbo",
      quote_evidence_label: "Trusted intraday OPRA/NBBO",
      production_proof_source_eligible: true,
    },
    source_pick_snapshot: {
      playbook_id: "short_term",
    },
  });

  const group = evidence.getPositionEvidenceGroup(position);
  const quote = evidence.getQuoteEvidenceDescriptor(position);
  assert.equal(group.id, "live_exact");
  assert.equal(group.productionProof, true);
  assert.equal(evidence.isProductionProofPosition(position), true);
  assert.equal(quote.id, "trusted_intraday_opra_nbbo");
  assert.equal(quote.productionProofSourceEligible, true);
});

test("stale compact backend live labels do not promote proof", () => {
  const position = closedPosition({
    proof_eligible: true,
    proof_class: "live_scan_exact_contract",
    compact_evidence: {
      proof_contract_version: proofContract.PROOF_EVIDENCE_CONTRACT_VERSION + 1,
      evidence_group: "live_exact",
      production_proof: true,
    },
    source_pick_snapshot: {
      playbook_id: "short_term",
    },
  });

  const group = evidence.getPositionEvidenceGroup(position);
  assert.equal(group.id, "proof_ineligible");
  assert.equal(group.productionProof, false);
  assert.equal(evidence.isProductionProofPosition(position), false);
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
