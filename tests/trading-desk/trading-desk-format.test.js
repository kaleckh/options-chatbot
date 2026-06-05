const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

function loadTradingDeskFormatModule() {
  const sourcePath = path.join(__dirname, "..", "..", "src", "components", "predictions", "tradingDeskFormat.ts");
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

test("fmtPct preserves tiny non-zero P&L instead of rounding it to zero", () => {
  const { fmtPct } = loadTradingDeskFormatModule();

  assert.equal(fmtPct(0.048), "+<0.1%");
  assert.equal(fmtPct(-0.048), "-<0.1%");
  assert.equal(fmtPct(0.0048, 2), "+<0.01%");
  assert.equal(fmtPct(-0.0048, 2), "-<0.01%");
});

test("fmtPct keeps ordinary signed percentages and exact zero readable", () => {
  const { fmtPct } = loadTradingDeskFormatModule();

  assert.equal(fmtPct(0), "0.0%");
  assert.equal(fmtPct(1.24), "+1.2%");
  assert.equal(fmtPct(-1.24), "-1.2%");
  assert.equal(fmtPct(null), "\u2014");
});

test("metricToneClass still treats tiny non-zero values by their true sign", () => {
  const { metricToneClass } = loadTradingDeskFormatModule();

  assert.equal(metricToneClass(0.048), "text-green");
  assert.equal(metricToneClass(-0.048), "text-red");
  assert.equal(metricToneClass(0), "text-text-2");
});
