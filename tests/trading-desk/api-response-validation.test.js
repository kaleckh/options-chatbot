const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "..");

function loadValidationModule() {
  const sourcePath = path.join(ROOT, "src", "lib", "trading-desk", "apiResponseValidation.ts");
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

function row(overrides = {}) {
  return {
    id: 1,
    status: "open",
    ticker: "AAA",
    ...overrides,
  };
}

function assertValid(contractId, body) {
  const { validateTradingDeskApiResponse } = loadValidationModule();
  const result = validateTradingDeskApiResponse(contractId, body);
  assert.equal(result.ok, true);
}

function assertInvalid(contractId, body, pattern) {
  const { validateTradingDeskApiResponse } = loadValidationModule();
  const result = validateTradingDeskApiResponse(contractId, body);
  assert.equal(result.ok, false);
  assert.match(`${result.path}: ${result.reason}`, pattern);
}

test("Trading Desk response validation accepts valid read and mutation envelopes", () => {
  assertValid("tracked_positions_read", {
    positions: [row()],
    page: { limit: 25, offset: 0, returned: 1 },
  });
  assertValid("tracked_positions_read", {
    open: [row()],
    closed: [row({ id: 2, status: "closed" })],
    summary: { open: {}, closed: {}, all: {} },
  });
  assertValid("tracked_positions_create", {
    position: row(),
    position_event_persistence: { status: "recorded" },
  });
  assertValid("tracked_positions_review", {
    positions: [row()],
    position_event_persistence: { status: "recorded" },
  });
  assertValid("tracked_positions_close", {
    position: row({ status: "closed" }),
    position_event_persistence: { status: "recorded" },
  });
  assertValid("suggested_trades_read", {
    trades: [row()],
    page: { limit: 25, offset: 0, returned: 1 },
  });
  assertValid("suggested_trades_create", { trade: row() });
  assertValid("suggested_trades_review", { trades: [row()] });
  assertValid("suggested_trades_close", { trade: row({ status: "closed" }) });
});

test("Trading Desk response validation accepts unavailable error sentinels", () => {
  assertValid("tracked_positions_read", { error: "Tracked positions storage is unavailable." });
  assertValid("suggested_trades_create", { error: "Suggested trades storage is unavailable." });
});

test("Trading Desk response validation rejects malformed rows and pages", () => {
  assertInvalid(
    "tracked_positions_read",
    { positions: [{ id: "1", status: "open" }] },
    /body\.positions\[0\]\.id/
  );
  assertInvalid(
    "suggested_trades_read",
    { trades: [row()], page: { limit: "25", offset: 0, returned: 1 } },
    /body\.page\.limit/
  );
  assertInvalid(
    "tracked_positions_review",
    { positions: [{ id: 1, status: "pending" }], position_event_persistence: {} },
    /body\.positions\[0\]\.status/
  );
});

test("Trading Desk response validation rejects swapped tracked and suggested envelopes", () => {
  assertInvalid("tracked_positions_create", { trade: row() }, /body\.trade/);
  assertInvalid("tracked_positions_review", { positions: [row()] }, /position_event_persistence/);
  assertInvalid("suggested_trades_create", { position: row() }, /body\.position/);
  assertInvalid(
    "suggested_trades_review",
    { trades: [row()], position_event_persistence: { status: "recorded" } },
    /position_event_persistence/
  );
});
