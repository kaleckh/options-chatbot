const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const ReactDOMServer = require("react-dom/server");

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

function loadTradingDeskCellsModule() {
  const sourcePath = path.join(ROOT, "src", "components", "predictions", "tradingDeskCells.tsx");
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
        getCloseNowPnlPct: () => null,
        getCloseNowPrice: () => null,
        getCurrentPolicyReplayState: () => ({ detail: "", label: "Unknown", tone: "muted" }),
        getMarkPnlPct: () => null,
        getMarkPrice: () => null,
        getOpenReviewActionState: () => ({ detail: "", id: "hold", label: "Hold", tone: "neutral" }),
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

const cells = loadTradingDeskCellsModule();

test("realized P&L cell exposes tiny rounded values with exact tooltip precision", () => {
  const html = ReactDOMServer.renderToStaticMarkup(cells.renderRealizedPnlCell(0.048));

  assert.match(html, /\+&lt;0\.1%/);
  assert.match(html, /Positive realized P&amp;L: \+&lt;0\.1% \(exact \+0\.0480%\)/);
  assert.match(html, /text-green/);
});

test("negative tiny realized P&L keeps sign in display and precision labels", () => {
  const html = ReactDOMServer.renderToStaticMarkup(cells.renderRealizedPnlCell(-0.048));

  assert.match(html, /-&lt;0\.1%/);
  assert.match(html, /Negative realized P&amp;L: -&lt;0\.1% \(exact -0\.0480%\)/);
  assert.match(html, /text-red/);
});
