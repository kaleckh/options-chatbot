const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "..");

function transpileTsFile(sourcePath) {
  const source = fs.readFileSync(sourcePath, "utf8");
  return ts.transpileModule(source, {
    compilerOptions: {
      esModuleInterop: true,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: sourcePath,
  }).outputText;
}

function runCommonJsModule(sourcePath, requireMap = {}) {
  const transpiled = transpileTsFile(sourcePath);
  const module = { exports: {} };
  const localRequire = (specifier) => {
    if (specifier in requireMap) return requireMap[specifier];
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

function loadMutationIntentModule() {
  return runCommonJsModule(path.join(ROOT, "src", "lib", "trading-desk", "mutationIntent.ts"));
}

function loadStoreOwnershipModule() {
  return runCommonJsModule(path.join(ROOT, "src", "lib", "trading-desk", "storeOwnership.ts"));
}

function loadStrategyLabIntentModule() {
  return runCommonJsModule(path.join(ROOT, "src", "lib", "strategy-lab", "replayIntent.ts"));
}

function loadApiUtilsModule(mutationIntent) {
  const storeOwnership = loadStoreOwnershipModule();
  const strategyLabIntent = loadStrategyLabIntentModule();
  return runCommonJsModule(
    path.join(ROOT, "src", "app", "api", "_utils.ts"),
    {
      "@/lib/backend/transport": {
        BackendHttpError: class BackendHttpError extends Error {},
      },
      "@/lib/trading-desk/mutationIntent": mutationIntent,
      "@/lib/trading-desk/storeOwnership": storeOwnership,
      "@/lib/strategy-lab/replayIntent": strategyLabIntent,
      "next/server": {
        NextResponse: {
          json: (body, init = {}) => ({
            body,
            status: init.status ?? 200,
            headers: init.headers ?? {},
          }),
        },
      },
    }
  );
}

function loadRouteModule(relativePath, bridgeMocks) {
  const mutationIntent = loadMutationIntentModule();
  const apiUtils = loadApiUtilsModule(mutationIntent);
  return runCommonJsModule(
    path.join(ROOT, relativePath),
    {
      "@/app/api/_utils": apiUtils,
      "../../../_utils": apiUtils,
      "@/lib/python-bridge": bridgeMocks,
      "next/server": {
        NextResponse: {
          json: (body, init = {}) => ({
            body,
            status: init.status ?? 200,
            headers: init.headers ?? {},
          }),
        },
      },
    }
  );
}

function requestWithIntent(intent, bodyText) {
  return {
    headers: {
      get: (name) => {
        if (name.toLowerCase() !== "x-trading-desk-mutation") return null;
        return intent ?? null;
      },
    },
    text: async () => {
      if (bodyText !== undefined) return bodyText;
      throw new Error("mutation guard should run before body parsing");
    },
  };
}

test("Trading Desk mutation headers declare a specific mutating intent", () => {
  const mutationIntent = loadMutationIntentModule();
  const headers = mutationIntent.tradingDeskMutationHeaders("review_tracked_positions");

  assert.equal(headers["Content-Type"], "application/json");
  assert.equal(
    headers[mutationIntent.TRADING_DESK_MUTATION_HEADER],
    "review_tracked_positions"
  );
});

test("Trading Desk store ownership catalog separates tracked positions from paper ideas", () => {
  const storeOwnership = loadStoreOwnershipModule();
  const trackedRead = storeOwnership.getTradingDeskRouteContract("tracked_positions_read");
  const suggestedRead = storeOwnership.getTradingDeskRouteContract("suggested_trades_read");

  assert.equal(trackedRead.store, "postgres_tracked_positions");
  assert.equal(trackedRead.recordClass, "tracked_position");
  assert.match(trackedRead.owner, /positions_repository\.py/);
  assert.match(trackedRead.owner, /DATABASE_URL/);
  assert.equal(suggestedRead.store, "sqlite_suggested_trades");
  assert.equal(suggestedRead.recordClass, "suggested_trade");
  assert.match(suggestedRead.owner, /suggested_trades_repository\.py/);
  assert.match(suggestedRead.owner, /chat_history\.db/);
});

test("Trading Desk mutation routes require explicit mutation intent", () => {
  const routeExpectations = [
    ["src/app/api/positions/route.ts", "create_tracked_position"],
    ["src/app/api/positions/review/route.ts", "review_tracked_positions"],
    ["src/app/api/positions/[id]/close/route.ts", "close_tracked_position"],
    ["src/app/api/suggested-trades/route.ts", "create_suggested_trade"],
    ["src/app/api/suggested-trades/review/route.ts", "review_suggested_trades"],
    ["src/app/api/suggested-trades/[id]/close/route.ts", "close_suggested_trade"],
  ];

  for (const [relativePath, expectedIntent] of routeExpectations) {
    const source = fs.readFileSync(path.join(ROOT, relativePath), "utf8");
    assert.match(source, /requireTradingDeskMutationIntent/);
    assert.match(source, new RegExp(`"${expectedIntent}"`));
  }
});

test("Trading Desk read routes declare read-only store ownership", async () => {
  const routeExpectations = [
    ["src/app/api/positions/route.ts", "getGroupedTrackedPositions", "postgres_tracked_positions", "tracked_position"],
    ["src/app/api/suggested-trades/route.ts", "getGroupedSuggestedTrades", "sqlite_suggested_trades", "suggested_trade"],
  ];

  for (const [relativePath, expectedBridgeName, expectedStore, expectedRecordClass] of routeExpectations) {
    const calls = [];
    const bridgeMocks = new Proxy({}, {
      get: (_target, property) => async (...args) => {
        calls.push({ name: String(property), args });
        return { ok: true, bridge: String(property) };
      },
    });
    const route = loadRouteModule(relativePath, bridgeMocks);
    const response = await route.GET({
      nextUrl: new URL("http://localhost/api/test?status=all&grouped=1"),
    });

    assert.equal(response.status, 200);
    assert.deepEqual(response.body, { ok: true, bridge: expectedBridgeName });
    assert.equal(response.headers["x-trading-desk-store"], expectedStore);
    assert.equal(response.headers["x-trading-desk-lifecycle"], "read");
    assert.equal(response.headers["x-trading-desk-record-class"], expectedRecordClass);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].name, expectedBridgeName);
  }
});

test("Trading Desk mutation routes reject missing or wrong intent before bridge calls", async () => {
  const routeExpectations = [
    ["src/app/api/positions/route.ts", "create_tracked_position"],
    ["src/app/api/positions/review/route.ts", "review_tracked_positions"],
    ["src/app/api/positions/[id]/close/route.ts", "close_tracked_position"],
    ["src/app/api/suggested-trades/route.ts", "create_suggested_trade"],
    ["src/app/api/suggested-trades/review/route.ts", "review_suggested_trades"],
    ["src/app/api/suggested-trades/[id]/close/route.ts", "close_suggested_trade"],
  ];
  const bridgeMocks = new Proxy({}, {
    get: () => () => {
      throw new Error("bridge mutation should not be called without matching intent");
    },
  });

  for (const [relativePath, expectedIntent] of routeExpectations) {
    const route = loadRouteModule(relativePath, bridgeMocks);
    const routeContext = relativePath.includes("[id]")
      ? { params: Promise.resolve({ id: "1" }) }
      : undefined;

    const missingIntentResponse = routeContext
      ? await route.POST(requestWithIntent(null), routeContext)
      : await route.POST(requestWithIntent(null));
    assert.equal(missingIntentResponse.status, 428);
    assert.match(missingIntentResponse.body.error, new RegExp(expectedIntent));

    const wrongIntentResponse = routeContext
      ? await route.POST(requestWithIntent("wrong_intent"), routeContext)
      : await route.POST(requestWithIntent("wrong_intent"));
    assert.equal(wrongIntentResponse.status, 428);
    assert.match(wrongIntentResponse.body.error, new RegExp(expectedIntent));
  }
});

test("Trading Desk mutation routes reach the bridge only with matching intent", async () => {
  const routeExpectations = [
    ["src/app/api/positions/route.ts", "create_tracked_position", "createTrackedPosition", "postgres_tracked_positions", "create", "tracked_position"],
    ["src/app/api/positions/review/route.ts", "review_tracked_positions", "reviewTrackedPositions", "postgres_tracked_positions", "review", "tracked_position"],
    ["src/app/api/positions/[id]/close/route.ts", "close_tracked_position", "closeTrackedPosition", "postgres_tracked_positions", "close", "tracked_position"],
    ["src/app/api/suggested-trades/route.ts", "create_suggested_trade", "createSuggestedTrade", "sqlite_suggested_trades", "create", "suggested_trade"],
    ["src/app/api/suggested-trades/review/route.ts", "review_suggested_trades", "reviewSuggestedTrades", "sqlite_suggested_trades", "review", "suggested_trade"],
    ["src/app/api/suggested-trades/[id]/close/route.ts", "close_suggested_trade", "closeSuggestedTrade", "sqlite_suggested_trades", "close", "suggested_trade"],
  ];

  for (const [
    relativePath,
    expectedIntent,
    expectedBridgeName,
    expectedStore,
    expectedLifecycle,
    expectedRecordClass,
  ] of routeExpectations) {
    const calls = [];
    const bridgeMocks = new Proxy({}, {
      get: (_target, property) => async (...args) => {
        calls.push({ name: String(property), args });
        return { ok: true, bridge: String(property) };
      },
    });
    const route = loadRouteModule(relativePath, bridgeMocks);
    const routeContext = relativePath.includes("[id]")
      ? { params: Promise.resolve({ id: "7" }) }
      : undefined;
    const request = requestWithIntent(expectedIntent, JSON.stringify({ position_ids: [7], exit_price: 1.23 }));
    const response = routeContext
      ? await route.POST(request, routeContext)
      : await route.POST(request);

    assert.equal(response.status, 200);
    assert.deepEqual(response.body, { ok: true, bridge: expectedBridgeName });
    assert.equal(response.headers["x-trading-desk-store"], expectedStore);
    assert.equal(response.headers["x-trading-desk-lifecycle"], expectedLifecycle);
    assert.equal(response.headers["x-trading-desk-record-class"], expectedRecordClass);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].name, expectedBridgeName);
  }
});

test("Trading Desk component POSTs use mutation intent headers", () => {
  const source = fs.readFileSync(
    path.join(ROOT, "src", "components", "predictions", "PredictionsView.tsx"),
    "utf8"
  );
  const expectedIntents = [
    "create_tracked_position",
    "review_tracked_positions",
    "close_tracked_position",
    "create_suggested_trade",
    "review_suggested_trades",
    "close_suggested_trade",
  ];

  for (const expectedIntent of expectedIntents) {
    assert.match(source, new RegExp(`tradingDeskMutationHeaders\\("${expectedIntent}"\\)`));
  }
});
