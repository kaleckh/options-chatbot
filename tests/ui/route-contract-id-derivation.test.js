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
    { exports: module.exports, module, require },
    { filename: sourcePath }
  );
  return module.exports;
}

function assertCatalogMatchesRegistry(moduleExports, idsName, registryName) {
  const ids = moduleExports[idsName];
  const registry = moduleExports[registryName];

  assert.deepEqual([...ids].sort(), Object.keys(registry).sort());
  for (const id of ids) {
    assert.equal(registry[id].id, id);
  }
}

test("route contract id arrays derive existing route contract unions", () => {
  assertCatalogMatchesRegistry(
    loadTsModule("src/lib/trading-desk/storeOwnership.ts"),
    "TRADING_DESK_ROUTE_CONTRACT_IDS",
    "TRADING_DESK_ROUTE_CONTRACTS"
  );
  assertCatalogMatchesRegistry(
    loadTsModule("src/lib/strategy-lab/replayIntent.ts"),
    "STRATEGY_LAB_ROUTE_CONTRACT_IDS",
    "STRATEGY_LAB_ROUTE_CONTRACTS"
  );
  assertCatalogMatchesRegistry(
    loadTsModule("src/lib/route-lifecycle/routeContracts.ts"),
    "OPTIONS_ROUTE_LIFECYCLE_CONTRACT_IDS",
    "OPTIONS_ROUTE_LIFECYCLE_CONTRACTS"
  );
});

test("route contract id types are no longer manual string unions", () => {
  const sources = [
    ["src/lib/trading-desk/storeOwnership.ts", "TradingDeskRouteContractId"],
    ["src/lib/strategy-lab/replayIntent.ts", "StrategyLabRouteContractId"],
    ["src/lib/route-lifecycle/routeContracts.ts", "OptionsRouteLifecycleContractId"],
  ];

  for (const [relativePath, typeName] of sources) {
    const source = readRepoFile(relativePath);
    assert.match(source, new RegExp(`export const .*CONTRACT_IDS = \\[`));
    assert.match(source, new RegExp(`export type ${typeName} = \\(typeof .*CONTRACT_IDS\\)\\[number\\]`));
    assert.doesNotMatch(source, new RegExp(`export type ${typeName} =\\s*\\|`));
  }
});
