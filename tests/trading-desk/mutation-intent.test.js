const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "..");
const TEST_OPERATOR_TOKEN = "operator-test-token";

function nextResponseMock() {
  return {
    NextResponse: {
      json: (body, init = {}) => ({
        body,
        status: init.status ?? 200,
        headers: init.headers ?? {},
      }),
    },
  };
}

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
      Buffer,
      console,
      exports: module.exports,
      module,
      process: { env: { OPTIONS_LOCAL_OPERATOR_TOKEN: TEST_OPERATOR_TOKEN } },
      require: localRequire,
    },
    { filename: sourcePath }
  );

  return module.exports;
}

function loadMutationIntentModule() {
  return runCommonJsModule(path.join(ROOT, "src", "lib", "trading-desk", "mutationIntent.ts"));
}

function readTradingDeskClientSources() {
  return [
    path.join(ROOT, "src", "components", "predictions", "PredictionsView.tsx"),
    path.join(ROOT, "src", "components", "predictions", "useTradingDeskCloseDialogs.ts"),
    path.join(ROOT, "src", "components", "predictions", "useTradingDeskRecords.ts"),
  ]
    .map((sourcePath) => fs.readFileSync(sourcePath, "utf8"))
    .join("\n");
}

function loadStoreOwnershipModule() {
  return runCommonJsModule(path.join(ROOT, "src", "lib", "trading-desk", "storeOwnership.ts"));
}

function loadStrategyLabIntentModule() {
  return runCommonJsModule(path.join(ROOT, "src", "lib", "strategy-lab", "replayIntent.ts"));
}

function loadRouteLifecycleModule() {
  return runCommonJsModule(path.join(ROOT, "src", "lib", "route-lifecycle", "routeContracts.ts"));
}

function loadOperatorAuthModule() {
  return runCommonJsModule(
    path.join(ROOT, "src", "lib", "operator-auth.ts"),
    {
      "next/server": nextResponseMock(),
    }
  );
}

function loadApiUtilsModule(mutationIntent) {
  const storeOwnership = loadStoreOwnershipModule();
  const strategyLabIntent = loadStrategyLabIntentModule();
  const routeLifecycle = loadRouteLifecycleModule();
  const operatorAuth = loadOperatorAuthModule();
  const responseValidation = runCommonJsModule(
    path.join(ROOT, "src", "lib", "trading-desk", "apiResponseValidation.ts")
  );
  return runCommonJsModule(
    path.join(ROOT, "src", "app", "api", "_utils.ts"),
    {
      "@/lib/backend/transport": {
        BackendHttpError: class BackendHttpError extends Error {},
      },
      "@/lib/trading-desk/apiResponseValidation": responseValidation,
      "@/lib/trading-desk/mutationIntent": mutationIntent,
      "@/lib/trading-desk/storeOwnership": storeOwnership,
      "@/lib/strategy-lab/replayIntent": strategyLabIntent,
      "@/lib/route-lifecycle/routeContracts": routeLifecycle,
      "@/lib/operator-auth": operatorAuth,
      "next/server": nextResponseMock(),
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
      "next/server": nextResponseMock(),
    }
  );
}

function requestWithIntent(intent, bodyText, options = {}) {
  const operatorToken = Object.prototype.hasOwnProperty.call(options, "operatorToken")
    ? options.operatorToken
    : TEST_OPERATOR_TOKEN;
  return {
    headers: {
      get: (name) => {
        const normalizedName = name.toLowerCase();
        if (normalizedName === "x-options-operator-token") return operatorToken ?? null;
        if (normalizedName === "x-trading-desk-mutation") return intent ?? null;
        return null;
      },
    },
    cookies: {
      get: () => undefined,
    },
    text: async () => {
      if (bodyText !== undefined) return bodyText;
      throw new Error("mutation guard should run before body parsing");
    },
  };
}

function validTradingDeskRow(overrides = {}) {
  return {
    id: 7,
    status: "open",
    ticker: "AAA",
    ...overrides,
  };
}

function validBridgeResponse(name) {
  if (name === "getGroupedTrackedPositionsWithBackendHeaders") {
    return {
      body: {
        open: [validTradingDeskRow()],
        closed: [validTradingDeskRow({ id: 8, status: "closed" })],
        summary: { open: {}, closed: {}, all: {} },
      },
      headers: { "x-python-backend-duration-ms": "12.3" },
    };
  }
  if (name === "getGroupedSuggestedTradesWithBackendHeaders") {
    return {
      body: {
        open: [validTradingDeskRow()],
        closed: [validTradingDeskRow({ id: 8, status: "closed" })],
        summary: { open: {}, closed: {}, all: {} },
      },
      headers: { "x-python-backend-duration-ms": "12.3" },
    };
  }
  if (name === "createTrackedPosition" || name === "closeTrackedPosition") {
    return {
      position: validTradingDeskRow({ status: name === "closeTrackedPosition" ? "closed" : "open" }),
      position_event_persistence: { status: "recorded" },
    };
  }
  if (name === "reviewTrackedPositions") {
    return {
      positions: [validTradingDeskRow()],
      position_event_persistence: { status: "recorded" },
    };
  }
  if (name === "createSuggestedTrade" || name === "closeSuggestedTrade") {
    return {
      trade: validTradingDeskRow({ status: name === "closeSuggestedTrade" ? "closed" : "open" }),
    };
  }
  if (name === "reviewSuggestedTrades") {
    return { trades: [validTradingDeskRow()] };
  }
  return { error: `No test fixture for ${name}` };
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
    assert.match(source, /requireLocalOperator/);
    assert.match(source, /requireTradingDeskMutationIntent/);
    assert.match(source, new RegExp(`"${expectedIntent}"`));
  }
});

test("Trading Desk read routes declare read-only store ownership", async () => {
  const routeExpectations = [
    ["src/app/api/positions/route.ts", "getGroupedTrackedPositionsWithBackendHeaders", "postgres_tracked_positions", "tracked_position"],
    ["src/app/api/suggested-trades/route.ts", "getGroupedSuggestedTradesWithBackendHeaders", "sqlite_suggested_trades", "suggested_trade"],
  ];

  for (const [relativePath, expectedBridgeName, expectedStore, expectedRecordClass] of routeExpectations) {
    const calls = [];
    const bridgeMocks = new Proxy({}, {
      get: (_target, property) => async (...args) => {
        calls.push({ name: String(property), args });
        return validBridgeResponse(String(property));
      },
    });
    const route = loadRouteModule(relativePath, bridgeMocks);
    const response = await route.GET({
      nextUrl: new URL("http://localhost/api/test?status=closed&grouped=1&limit=25&offset=50&compact=1"),
    });

    assert.equal(response.status, 200);
    assert.deepEqual(response.body, validBridgeResponse(expectedBridgeName).body);
    assert.equal(response.headers["x-python-backend-duration-ms"], "12.3");
    assert.equal(response.headers["x-trading-desk-store"], expectedStore);
    assert.equal(response.headers["x-trading-desk-lifecycle"], "read");
    assert.equal(response.headers["x-trading-desk-record-class"], expectedRecordClass);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].name, expectedBridgeName);
    assert.equal(calls[0].args[0], "closed");
    assert.equal(calls[0].args[1].limit, "25");
    assert.equal(calls[0].args[1].offset, "50");
    assert.equal(calls[0].args[1].compact, "1");
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

test("Trading Desk mutation intent is not authorization", async () => {
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
      throw new Error("bridge mutation should not be called without operator auth");
    },
  });

  for (const [relativePath, expectedIntent] of routeExpectations) {
    const route = loadRouteModule(relativePath, bridgeMocks);
    const routeContext = relativePath.includes("[id]")
      ? { params: Promise.resolve({ id: "1" }) }
      : undefined;
    const request = requestWithIntent(expectedIntent, undefined, { operatorToken: null });
    const response = routeContext
      ? await route.POST(request, routeContext)
      : await route.POST(request);

    assert.equal(response.status, 401);
    assert.match(response.body.error, /Local operator authorization/);
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
        return validBridgeResponse(String(property));
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
    assert.deepEqual(response.body, validBridgeResponse(expectedBridgeName));
    assert.equal(response.headers["x-trading-desk-store"], expectedStore);
    assert.equal(response.headers["x-trading-desk-lifecycle"], expectedLifecycle);
    assert.equal(response.headers["x-trading-desk-record-class"], expectedRecordClass);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].name, expectedBridgeName);
  }
});

test("Trading Desk routes fail closed when backend response envelope is invalid", async () => {
  const bridgeMocks = {
    createSuggestedTrade: async () => ({
      trade: validTradingDeskRow(),
      position_event_persistence: { status: "recorded" },
    }),
  };
  const route = loadRouteModule("src/app/api/suggested-trades/route.ts", bridgeMocks);
  const response = await route.POST(
    requestWithIntent("create_suggested_trade", JSON.stringify({ scan_pick: {}, fill_price: 1 }))
  );

  assert.equal(response.status, 502);
  assert.equal(response.body.route_contract, "suggested_trades_create");
  assert.match(response.body.error, /failed validation/);
  assert.match(response.body.reason, /position_event_persistence/);
  assert.equal(response.headers["x-trading-desk-store"], "sqlite_suggested_trades");
  assert.equal(response.headers["x-trading-desk-lifecycle"], "create");
  assert.equal(response.headers["x-trading-desk-record-class"], "suggested_trade");
});

test("Trading Desk component POSTs use mutation intent headers", () => {
  const source = readTradingDeskClientSources();
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

test("Trading Desk component lazy-loads closed rows through paged read routes", () => {
  const source = readTradingDeskClientSources();

  assert.ok(!source.includes("status=all&grouped=1"));
  assert.ok(source.includes("/api/positions?status=open"));
  assert.ok(source.includes("/api/suggested-trades?status=open"));
  assert.ok(source.includes("status=closed&limit=${CLOSED_POSITION_PAGE_SIZE}&offset="));
  assert.ok(source.includes("status=closed&limit=${CLOSED_SUGGESTED_TRADE_PAGE_SIZE}&offset="));
  assert.ok(source.includes("CLOSED_POSITION_PAGE_SIZE = 50"));
  assert.ok(source.includes("compact=1"));
  assert.ok(source.includes("fetchClosedPositionsPage"));
  assert.ok(source.includes("fetchClosedSuggestedTradesPage"));
});

test("Tracked position closed view loads the next batch as the operator scrolls", () => {
  const source = fs.readFileSync(
    path.join(ROOT, "src", "components", "predictions", "TrackedPositionsTab.tsx"),
    "utf8"
  );

  assert.match(source, /IntersectionObserver/);
  assert.match(source, /shouldAutoLoadNextClosedBatch/);
  assert.match(source, /More closed history is available/);
  assert.match(source, /onLoadClosedRows\(\)/);
  assert.match(source, /onClick=\{\(\) => onLoadClosedRows\(\{ notify: true \}\)\}/);
  assert.match(source, /: "none"/);
});

test("Tracked position current policy view shows cohort health rather than raw recent negativity alone", () => {
  const source = fs.readFileSync(
    path.join(ROOT, "src", "components", "predictions", "TrackedPositionsTab.tsx"),
    "utf8"
  );

  assert.match(source, /buildCurrentPolicyCohortHealth/);
  assert.match(source, /Showcase Month/);
  assert.match(source, /Recent Month/);
  assert.match(source, /Recent Median/);
  assert.match(source, /Cohort State/);
  assert.match(source, /policyCohortHealthStatusLabel/);
});
