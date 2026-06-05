const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "..");

function loadTradingDeskFormatModule() {
  const sourcePath = path.join(ROOT, "src", "components", "predictions", "tradingDeskFormat.ts");
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

function loadTrackedPositionUtilsModule() {
  const sourcePath = path.join(ROOT, "src", "components", "predictions", "trackedPositionUtils.tsx");
  const source = fs.readFileSync(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      esModuleInterop: true,
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: sourcePath,
  }).outputText;
  const module = { exports: {} };
  const localRequire = (specifier) => {
    if (specifier === "@/components/predictions/tradingDeskFormat") {
      return loadTradingDeskFormatModule();
    }
    if (specifier === "@/lib/trading-desk/positionEvidence") {
      return {
        getPositionEvidenceDescriptor: () => ({
          detail: "mocked evidence",
          label: "Legacy",
          tone: "muted",
        }),
      };
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

const utils = loadTrackedPositionUtilsModule();

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

test("displayLaneLabel canonicalizes regular source labels without observation wording", () => {
  assert.equal(utils.displayLaneLabel("", ""), "Source Missing");
  assert.equal(utils.displayLaneLabel("unlabeled"), "Source Missing");
  assert.equal(utils.displayLaneLabel("legacy_scheduled_scan"), "Historical Import");
  assert.equal(utils.displayLaneLabel("bullish_pullback_observation"), "Bullish Pullback");
  assert.equal(utils.displayLaneLabel("tracked_winner_primary"), "Tracked Winner");
  assert.equal(utils.displayLaneLabel("tracked_winner_observation"), "Tracked Winner Research");
  assert.equal(utils.displayLaneLabel("range_breakout_observation", "Range Breakout Observation"), "Range Breakout");
});

test("position source descriptors keep missing and legacy imported rows explicit", () => {
  const missing = utils.getPositionLaneDescriptor({
    id: 1,
    ticker: "SPY",
    direction: "call",
    notes: "",
    source_pick_snapshot: {},
  });
  const scheduledImport = utils.getPositionLaneDescriptor({
    id: 2,
    ticker: "QQQ",
    direction: "call",
    notes: "Created from scheduled daily scan backfill.",
    source_pick_snapshot: {},
  });

  assert.deepEqual(plain(missing), { id: "source_missing", label: "Source Missing", detail: null });
  assert.deepEqual(plain(scheduledImport), { id: "historical_import", label: "Historical Import", detail: null });
});

test("lane options and source mix summaries use source language", () => {
  const options = utils.buildPositionLaneOptions([
    {
      id: 1,
      ticker: "SPY",
      direction: "call",
      source_pick_snapshot: { playbook_id: "bullish_pullback_observation" },
    },
    {
      id: 2,
      ticker: "QQQ",
      direction: "call",
      source_pick_snapshot: { playbook_id: "bullish_pullback_observation" },
    },
    {
      id: 3,
      ticker: "IWM",
      direction: "call",
      source_pick_snapshot: { playbook_id: "tracked_winner_observation" },
    },
  ]);

  assert.deepEqual(plain(options), [
    { id: "bullish_pullback", label: "Bullish Pullback", count: 2 },
    { id: "tracked_winner_observation", label: "Tracked Winner Research", count: 1 },
  ]);
  assert.equal(utils.laneMixSummary(options), "Source mix: Bullish Pullback 2 / Tracked Winner Research 1.");
});
