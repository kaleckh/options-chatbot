const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "..");

function readRepoFile(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

function loadTsModule(relativePath) {
  const sourcePath = path.join(ROOT, relativePath);
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
    { exports: module.exports, module, require, Set },
    { filename: sourcePath }
  );
  return module.exports;
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

test("Trading Desk active and visible tab ids are separate typed catalogs", () => {
  const tabs = loadTsModule("src/components/predictions/tradingDeskTabs.ts");

  assert.ok(tabs.TRADING_DESK_CONTENT_TAB_IDS.includes("positions"));
  assert.ok(!tabs.TRADING_DESK_CONTENT_TAB_IDS.includes("closed-trades"));
  assert.ok(tabs.TRADING_DESK_VISIBLE_TAB_IDS.includes("closed-trades"));
  assert.deepEqual(
    plain(tabs.resolveTradingDeskVisibleTab("closed-trades")),
    { activeSubTab: "positions", positionsView: "closed" }
  );
  assert.deepEqual(
    plain(tabs.resolveTradingDeskVisibleTab("positions")),
    { activeSubTab: "positions", positionsView: "open" }
  );
  assert.equal(tabs.toTradingDeskVisibleTabId("positions", "closed"), "closed-trades");
  assert.equal(tabs.toTradingDeskVisibleTabId("positions", "open"), "positions");
});

test("Trading Desk legacy analytics ids exclude current scanner and paper workflows", () => {
  const tabs = loadTsModule("src/components/predictions/tradingDeskTabs.ts");

  assert.deepEqual(plain(tabs.LEGACY_PREDICTION_TAB_IDS), ["pending", "graded", "breakdown", "sim", "sectors"]);
  assert.equal(tabs.isLegacyPredictionTabId("pending"), true);
  assert.equal(tabs.isLegacyPredictionTabId("sectors"), true);
  assert.equal(tabs.isLegacyPredictionTabId("scanner"), false);
  assert.equal(tabs.isLegacyPredictionTabId("suggestions"), false);
});

test("PredictionsView consumes typed Trading Desk tab ids", () => {
  const source = readRepoFile("src/components/predictions/PredictionsView.tsx");

  assert.match(source, /useState<TradingDeskSubTabId>\("positions"\)/);
  assert.match(source, /useState<TradingDeskPositionsView>\("open"\)/);
  assert.match(source, /toTradingDeskVisibleTabId\(activeSubTab, positionsView\)/);
  assert.match(source, /resolveTradingDeskVisibleTab\(tabId\)/);
  assert.match(source, /isLegacyPredictionTabId\(activeSubTab\)/);
  assert.doesNotMatch(source, /LEGACY_PREDICTION_TABS\s*=\s*new Set/);
  assert.doesNotMatch(source, /useState\("positions"\)/);
});
