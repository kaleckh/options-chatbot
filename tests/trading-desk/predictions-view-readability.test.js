const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.join(__dirname, "..", "..");

function readRepoFile(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

test("PredictionsView delegates close dialogs to focused components", () => {
  const predictionsView = readRepoFile("src/components/predictions/PredictionsView.tsx");
  const lineCount = predictionsView.split(/\r?\n/).length;

  assert.ok(lineCount < 950, `PredictionsView.tsx should stay below 950 lines, found ${lineCount}`);
  assert.match(predictionsView, /useTradingDeskCloseDialogs/);
  assert.match(predictionsView, /<CloseTradeModal \{\.\.\.trackedCloseModalProps\} \/>/);
  assert.match(predictionsView, /<CloseTradeModal \{\.\.\.suggestedCloseModalProps\} \/>/);
  assert.doesNotMatch(predictionsView, /function CloseTradeModal/);
  assert.doesNotMatch(predictionsView, /close_tracked_position/);
  assert.doesNotMatch(predictionsView, /close_suggested_trade/);
});

test("CloseTradeModal owns close dialog copy and preview-only calculations", () => {
  const modal = readRepoFile("src/components/predictions/CloseTradeModal.tsx");

  assert.match(modal, /Close Tracked Trade/);
  assert.match(modal, /Close Suggested Trade/);
  assert.match(modal, /Confirm Hypothetical Close/);
  assert.match(modal, /calcNetOptionPnlPct/);
  assert.match(modal, /Escape/);
});

test("useTradingDeskCloseDialogs owns close POSTs without scanner creation behavior", () => {
  const hook = readRepoFile("src/components/predictions/useTradingDeskCloseDialogs.ts");

  assert.match(hook, /tradingDeskMutationHeaders\("close_tracked_position"\)/);
  assert.match(hook, /tradingDeskMutationHeaders\("close_suggested_trade"\)/);
  assert.match(hook, /\/api\/positions\/\$\{closingPosition\.id\}\/close/);
  assert.match(hook, /\/api\/suggested-trades\/\$\{closingSuggestedTrade\.id\}\/close/);
  assert.match(hook, /parseNonnegativePriceInput/);
  assert.doesNotMatch(hook, /create_tracked_position/);
  assert.doesNotMatch(hook, /create_suggested_trade/);
});
