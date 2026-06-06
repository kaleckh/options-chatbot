const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "..");

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function loadTrackedPaperModule() {
  const sourcePath = path.join(ROOT, "src/components/predictions/TrackedPaperPositionsTab.tsx");
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
  const localRequire = (id) => {
    if (id === "react") return { memo: (component) => component, useEffect: () => undefined, useMemo: (fn) => fn(), useState: (value) => [value, () => undefined] };
    if (id === "react/jsx-runtime") return { jsx: () => null, jsxs: () => null, Fragment: Symbol("Fragment") };
    if (id === "lucide-react") return { LineChart: () => null, RefreshCw: () => null };
    if (id === "@/components/ui/Button") return () => null;
    if (id === "@/components/ui/FinTable") return () => null;
    if (id === "@/components/predictions/TradingDeskCompactStat") return { CompactStat: () => null };
    if (id === "@/components/predictions/tradingDeskFormat") {
      return {
        fmtDateTime: (value) => value,
        fmtMoney: (value) => value == null ? "n/a" : `$${value}`,
        fmtPct: (value) => value == null ? "n/a" : `${value}%`,
        metricToneClass: () => "tone",
      };
    }
    if (id === "@/components/predictions/trackedPositionUtils") {
      return {
        fmtContractCoreLabel: (position) => position.contract_symbol || position.ticker || "contract",
        fmtTakenDate: (position) => position.filled_at || "",
        getPositionLaneDescriptor: () => ({ label: "Regular Options" }),
        renderTickerCell: (position) => position.ticker,
      };
    }
    if (id === "@/lib/trading-desk/positionEvidence") {
      return {
        getCloseNowPnlPct: (position) => position.close_now_pnl_pct ?? null,
        getCloseNowPrice: (position) => position.close_now_price ?? null,
        getEntryExecutionPrice: (position) => position.entry_execution_price ?? position.entry_option_price ?? null,
        getMarkPnlPct: (position) => position.mark_pnl_pct ?? null,
        getMarkPrice: (position) => position.mark_price ?? null,
        getRealizedExitPrice: (position) => position.realized_exit_price ?? null,
        getRealizedPnlPct: (position) => position.realized_pnl_pct ?? null,
      };
    }
    return require(id);
  };
  vm.runInNewContext(
    transpiled,
    { exports: module.exports, module, require: localRequire, Symbol },
    { filename: sourcePath }
  );
  return module.exports;
}

test("tracked paper helpers identify Alpaca paper rows", () => {
  const paper = loadTrackedPaperModule();

  assert.equal(paper.isAlpacaPaperTrackedPosition({
    source_pick_snapshot: { alpaca_paper_order: { client_order_id: "opt-paper-1" } },
  }), true);
  assert.equal(paper.isAlpacaPaperTrackedPosition({
    source_pick_snapshot: { broker_execution_mode: "alpaca_paper" },
  }), true);
  assert.equal(paper.isAlpacaPaperTrackedPosition({
    source_pick_snapshot: { alpaca_paper_order: {} },
  }), false);
});

test("tracked paper chart points prefer executable exit P&L and include close results", () => {
  const paper = loadTrackedPaperModule();
  const points = paper.buildTrackedPositionChartPoints({
    id: 7,
    ticker: "MSFT",
    status: "closed",
    filled_at: "2026-06-05T14:00:00Z",
    latest_review: { reviewed_at: "2026-06-05T15:00:00Z" },
    closed_at: "2026-06-05T16:00:00Z",
    entry_execution_price: 4,
    close_now_price: 4.8,
    close_now_pnl_pct: 20,
    mark_price: 4.9,
    mark_pnl_pct: 22.5,
    realized_exit_price: 5,
    realized_pnl_pct: 25,
  });

  assert.deepEqual(plain(points.map((point) => point.label)), ["Entry", "Executable Exit", "Paper Mark", "Closed"]);
  assert.deepEqual(plain(points.map((point) => point.pnlPct)), [0, 20, 22.5, 25]);
  assert.equal(points[1].price, 4.8);
  assert.equal(points[3].timestamp, "2026-06-05T16:00:00Z");
});
