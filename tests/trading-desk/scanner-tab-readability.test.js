const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.join(__dirname, "..", "..");

function readRepoFile(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

test("ScannerTab delegates scanner evidence and record form rendering", () => {
  const scannerTab = readRepoFile("src/components/predictions/ScannerTab.tsx");
  const lineCount = scannerTab.split(/\r?\n/).length;

  assert.ok(lineCount < 350, `ScannerTab.tsx should stay below 350 lines, found ${lineCount}`);
  assert.match(scannerTab, /ScannerEvidencePanel/);
  assert.match(scannerTab, /ScannerPickRecordForm/);
  assert.match(scannerTab, /<ScannerEvidencePanel/);
  assert.match(scannerTab, /<ScannerPickRecordForm/);
  assert.doesNotMatch(scannerTab, /Options Truth Health/);
  assert.doesNotMatch(scannerTab, /Contract And Quote Provenance/);
});

test("ScannerTab keeps explicit scanner table mobile contracts", () => {
  const scannerTab = readRepoFile("src/components/predictions/ScannerTab.tsx");

  assert.match(scannerTab, /const SCANNER_MOBILE_PRIORITY_COLS/);
  assert.match(scannerTab, /const SCANNER_MOBILE_HIDDEN_COLS/);
  assert.match(scannerTab, /<FinTable/);
  assert.match(scannerTab, /mobilePriorityCols=\{SCANNER_MOBILE_PRIORITY_COLS\}/);
  assert.match(scannerTab, /mobileHiddenCols=\{SCANNER_MOBILE_HIDDEN_COLS\}/);
});

test("ScannerEvidencePanel owns scanner evidence copy without mutations", () => {
  const evidencePanel = readRepoFile("src/components/predictions/ScannerEvidencePanel.tsx");

  assert.match(evidencePanel, /Evidence & guardrails/);
  assert.match(evidencePanel, /Options Truth Health/);
  assert.match(evidencePanel, /Replay-Backed Policy State/);
  assert.match(evidencePanel, /Tracked DB/);
  assert.doesNotMatch(evidencePanel, /fetchWithTimeout/);
  assert.doesNotMatch(evidencePanel, /readJsonResponseOrThrow/);
  assert.doesNotMatch(evidencePanel, /tradingDeskMutationHeaders/);
  assert.doesNotMatch(evidencePanel, /\/api\/scan/);
  assert.doesNotMatch(evidencePanel, /\/api\/positions/);
  assert.doesNotMatch(evidencePanel, /\/api\/suggested-trades/);
});

test("ScannerPickRecordForm owns selected-pick form copy without route behavior", () => {
  const recordForm = readRepoFile("src/components/predictions/ScannerPickRecordForm.tsx");

  assert.match(recordForm, /Save Real Tracked Position/);
  assert.match(recordForm, /Save Paper Idea/);
  assert.match(recordForm, /Eligible scheduled scanner picks are auto-tracked/);
  assert.match(recordForm, /selectedPick\.guardrail_decision === "blocked" \|\| savingSuggestedTrade/);
  assert.doesNotMatch(recordForm, /fetchWithTimeout/);
  assert.doesNotMatch(recordForm, /readJsonResponseOrThrow/);
  assert.doesNotMatch(recordForm, /tradingDeskMutationHeaders/);
  assert.doesNotMatch(recordForm, /create_tracked_position/);
  assert.doesNotMatch(recordForm, /create_suggested_trade/);
  assert.doesNotMatch(recordForm, /\/api\/scan/);
  assert.doesNotMatch(recordForm, /\/api\/positions/);
  assert.doesNotMatch(recordForm, /\/api\/suggested-trades/);
});
