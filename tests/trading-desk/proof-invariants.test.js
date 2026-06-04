const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "..");
const MANIFEST_PATH = path.join(ROOT, "data", "contracts", "proof-invariant-cases.json");

function loadTsModule(relativePath, requireMap = {}) {
  const sourcePath = path.join(ROOT, relativePath);
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
    if (specifier in requireMap) return requireMap[specifier];
    return require(specifier);
  };

  vm.runInNewContext(
    transpiled,
    { console, exports: module.exports, module, require: localRequire },
    { filename: sourcePath }
  );

  return module.exports;
}

function loadGeneratedProofEvidenceContractModule() {
  return loadTsModule("src/lib/generated/proofEvidenceContract.ts");
}

function loadProofContractModule() {
  return loadTsModule(
    "src/lib/trading-desk/proofContract.ts",
    {
      "@/lib/generated/proofEvidenceContract": loadGeneratedProofEvidenceContractModule(),
    }
  );
}

function loadPositionEvidenceModule() {
  return loadTsModule(
    "src/lib/trading-desk/positionEvidence.ts",
    {
      "@/lib/trading-desk/proofContract": loadProofContractModule(),
    }
  );
}

function loadManifest() {
  return JSON.parse(fs.readFileSync(MANIFEST_PATH, "utf8"));
}

const evidence = loadPositionEvidenceModule();

test("proof invariant manifest is test-only and deterministic", () => {
  const manifest = loadManifest();
  const ids = manifest.cases.map((entry) => entry.id);

  assert.equal(manifest.artifact, "proof_invariant_cases");
  assert.equal(manifest.runtime_use, false);
  assert.equal(new Set(ids).size, ids.length);
  assert.ok(manifest.non_goals.some((entry) => entry.includes("Does not define runtime behavior")));
});

test("proof invariant table matches frontend evidence and closed-view predicates", () => {
  const manifest = loadManifest();

  for (const invariantCase of manifest.cases) {
    const expected = invariantCase.expected.frontend;
    const position = JSON.parse(JSON.stringify(invariantCase.row));
    const group = evidence.getPositionEvidenceGroup(position);

    assert.equal(group.id, expected.evidence_group, invariantCase.id);
    assert.equal(evidence.isProductionProofPosition(position), expected.production_proof, invariantCase.id);
    assert.equal(evidence.isTruthGradeClosedPosition(position), expected.truth_grade_closed, invariantCase.id);
    assert.equal(evidence.isRealizedPnlClosedPosition(position), expected.realized_pnl_closed, invariantCase.id);
    assert.equal(evidence.matchesClosedDataView(position, "truth_grade"), expected.matches_truth_grade, invariantCase.id);
    assert.equal(evidence.matchesClosedDataView(position, "realized_pnl"), expected.matches_realized_pnl, invariantCase.id);
  }
});
