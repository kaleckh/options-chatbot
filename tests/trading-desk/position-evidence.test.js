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
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
  assert.equal(evidence.matchesClosedDataView(position, "historical_paper"), true);
});

test("research backfill rows with trusted executable exits do not enter truth-grade summaries", () => {
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
  assert.equal(evidence.isTruthGradeClosedPosition(position), false);
  assert.equal(evidence.matchesClosedDataView(position, "truth_grade"), false);
  assert.equal(evidence.matchesClosedDataView(position, "research_backfill"), true);
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
  assert.equal(evidence.isTruthGradeClosedPosition(lifecycleOnly), false);
  assert.equal(evidence.hasTrustedExecutableExit(markExit), false);
  assert.equal(evidence.isTruthGradeClosedPosition(markExit), false);
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
