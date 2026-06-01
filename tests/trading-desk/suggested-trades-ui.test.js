const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.join(__dirname, "..", "..");

test("Paper Ideas open rows surface review-required state before close state", () => {
  const source = fs.readFileSync(
    path.join(ROOT, "src", "components", "predictions", "SuggestedTradesTab.tsx"),
    "utf8"
  );

  assert.match(source, /getOpenReviewActionState/);
  assert.match(source, /reviewRequiredSuggestedTrades/);
  assert.match(source, /closeReadySuggestedTrades/);
  assert.match(source, /Needs Review/);
  assert.match(source, /Close-ready/);
  assert.match(source, /Status: renderPositionStatusCell\(trade\)/);
  assert.match(source, /mobileSubtitleCol=\{view === "open" \? "Status"/);
  assert.match(source, /actionState\.id === "executable_sell"/);
});
