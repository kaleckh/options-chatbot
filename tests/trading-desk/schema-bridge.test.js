const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.join(__dirname, "..", "..");

function readRepoFile(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

function walkFiles(root) {
  const files = [];
  const pending = [root];
  while (pending.length) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const entryPath = path.join(current, entry.name);
      if (entry.isDirectory()) pending.push(entryPath);
      if (entry.isFile()) files.push(entryPath);
    }
  }
  return files;
}

test("Trading Desk schema bridge maps generated ids to manual TypeScript contracts", () => {
  const bridge = JSON.parse(readRepoFile("data/contracts/trading-desk-api-schema-bridge.json"));
  const tsContracts = readRepoFile("src/lib/trading-desk/apiContracts.ts");
  const routeIds = bridge.route_contracts.map((route) => route.route_id);

  assert.deepEqual(routeIds.sort(), [
    "suggested_trades_close",
    "suggested_trades_create",
    "suggested_trades_read",
    "suggested_trades_review",
    "tracked_positions_close",
    "tracked_positions_create",
    "tracked_positions_read",
    "tracked_positions_review",
  ].sort());

  for (const route of bridge.route_contracts) {
    assert.match(tsContracts, new RegExp(`id:\\s*"${route.route_id}"`));
    if (route.typescript.request) {
      assert.match(tsContracts, new RegExp(`\\b${route.typescript.request}\\b`));
    }
    for (const responseName of route.typescript.response.split("|").map((value) => value.trim())) {
      assert.match(tsContracts, new RegExp(`\\b${responseName}\\b`));
    }
  }
});

test("Trading Desk schema bridge is documentation-only and not imported by runtime source", () => {
  const docs = readRepoFile("docs/trading-desk-schema-bridge.md");

  assert.match(docs, /runtime_use` is `false`/);
  assert.match(docs, /not FastAPI `response_model`/);
  assert.match(docs, /Zod\/AJV validation/);
  assert.match(docs, /No OpenAPI generation/);

  const runtimeImports = walkFiles(path.join(ROOT, "src"))
    .filter((sourcePath) => /\.(ts|tsx|js|jsx)$/.test(sourcePath))
    .filter((sourcePath) => fs.readFileSync(sourcePath, "utf8").includes("trading-desk-api-schema-bridge"));

  assert.deepEqual(runtimeImports, []);
});

test("Trading Desk schema bridge keeps schemas shallow and Trading Desk scoped", () => {
  const bridge = JSON.parse(readRepoFile("data/contracts/trading-desk-api-schema-bridge.json"));
  const serialized = JSON.stringify(bridge);

  assert.equal(bridge.runtime_use, false);
  assert.equal(bridge.route_contracts.filter((route) => route.schema_status === "pydantic_adapter_schema").length, 6);
  assert.equal(bridge.route_contracts.filter((route) => route.schema_status === "typescript_contract_only").length, 2);
  assert.doesNotMatch(serialized, /\/api\/scan/);
  assert.doesNotMatch(serialized, /\/api\/backtest/);
  assert.doesNotMatch(serialized, /proof_class/);
  assert.doesNotMatch(serialized, /source_scan_session_id/);
});
