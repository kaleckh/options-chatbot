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

function loadStrategyLabIntentModule() {
  return runCommonJsModule(path.join(ROOT, "src", "lib", "strategy-lab", "replayIntent.ts"));
}

function loadTradingDeskModule(relativePath) {
  return runCommonJsModule(path.join(ROOT, "src", "lib", "trading-desk", relativePath));
}

function loadApiUtilsModule(strategyLabIntent) {
  const tradingDeskMutationIntent = loadTradingDeskModule("mutationIntent.ts");
  const tradingDeskStoreOwnership = loadTradingDeskModule("storeOwnership.ts");
  return runCommonJsModule(
    path.join(ROOT, "src", "app", "api", "_utils.ts"),
    {
      "@/lib/backend/transport": {
        BackendHttpError: class BackendHttpError extends Error {},
      },
      "@/lib/trading-desk/mutationIntent": tradingDeskMutationIntent,
      "@/lib/trading-desk/storeOwnership": tradingDeskStoreOwnership,
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
  const strategyLabIntent = loadStrategyLabIntentModule();
  const apiUtils = loadApiUtilsModule(strategyLabIntent);
  return runCommonJsModule(
    path.join(ROOT, relativePath),
    {
      "@/app/api/_utils": apiUtils,
      "../_utils": apiUtils,
      "../../_utils": apiUtils,
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

function requestWithIntent(headerName, intent, bodyText) {
  return {
    headers: {
      get: (name) => {
        if (name.toLowerCase() !== headerName) return null;
        return intent ?? null;
      },
    },
    text: async () => {
      if (bodyText !== undefined) return bodyText;
      throw new Error("strategy lab mutation guard should run before body parsing");
    },
  };
}

function getRequest(query = "") {
  return {
    nextUrl: new URL(`http://localhost/api/test${query}`),
  };
}

test("Strategy Lab mutation headers declare a specific mutating intent", () => {
  const intent = loadStrategyLabIntentModule();
  const headers = intent.strategyLabMutationHeaders("run_replay_backtest");

  assert.equal(headers["Content-Type"], "application/json");
  assert.equal(headers[intent.STRATEGY_LAB_MUTATION_HEADER], "run_replay_backtest");
});

test("Strategy Lab route contract separates replay artifacts from profile files", () => {
  const intent = loadStrategyLabIntentModule();
  const replay = intent.getStrategyLabRouteContract("backtest_run");
  const summary = intent.getStrategyLabRouteContract("backtest_summary_read");
  const profileSave = intent.getStrategyLabRouteContract("profile_save");
  const changelog = intent.getStrategyLabRouteContract("profile_changelog_read");

  assert.equal(replay.store, "latest_replay_artifacts");
  assert.equal(replay.lifecycle, "replay_run");
  assert.match(replay.owner, /run_historical_backtest/);
  assert.equal(summary.lifecycle, "read");
  assert.equal(profileSave.store, "strategy_profile_files");
  assert.equal(profileSave.lifecycle, "profile_save");
  assert.match(profileSave.owner, /_save_profile/);
  assert.equal(changelog.store, "strategy_profile_files");
  assert.equal(changelog.lifecycle, "read");
  assert.match(changelog.owner, /CHANGELOG_FILES/);
});

test("Strategy Lab mutation routes require explicit mutation intent", () => {
  const routeExpectations = [
    ["src/app/api/backtest/route.ts", "run_replay_backtest"],
    ["src/app/api/profile/route.ts", "save_strategy_profile"],
  ];

  for (const [relativePath, expectedIntent] of routeExpectations) {
    const source = fs.readFileSync(path.join(ROOT, relativePath), "utf8");
    assert.match(source, /requireStrategyLabMutationIntent/);
    assert.match(source, new RegExp(`"${expectedIntent}"`));
  }
});

test("Strategy Lab passive read routes declare artifact ownership headers", async () => {
  const routeExpectations = [
    ["src/app/api/backtest/summary/route.ts", "getBacktestSummary", "latest_replay_artifacts", "read", "backtest_artifact_bundle"],
    ["src/app/api/backtest/last/route.ts", "getBacktestLast", "latest_replay_artifacts", "read", "backtest_result"],
    ["src/app/api/backtest/report/route.ts", "getBacktestReport", "latest_replay_artifacts", "read", "backtest_artifact_bundle"],
    ["src/app/api/backtest/metric-truth/route.ts", "getMetricTruthReport", "latest_replay_artifacts", "read", "backtest_artifact_bundle"],
    ["src/app/api/backtest/comparison/route.ts", "getTruthLaneComparison", "latest_replay_artifacts", "read", "backtest_artifact_bundle"],
    ["src/app/api/backtest/forward-evidence/route.ts", "getForwardEvidenceReport", "forward_evidence_artifacts", "read", "forward_evidence_report"],
    ["src/app/api/backtest/exit-audit/route.ts", "getPlaybookExitAudit", "latest_replay_artifacts", "read", "backtest_artifact_bundle"],
    ["src/app/api/backtest/live-policy/route.ts", "getLiveTradePolicy", "latest_replay_artifacts", "read", "backtest_artifact_bundle"],
    ["src/app/api/profile/route.ts", "getProfile", "strategy_profile_files", "read", "strategy_profile"],
    ["src/app/api/changelog/route.ts", "getChangelog", "strategy_profile_files", "read", "strategy_profile"],
  ];

  for (const [relativePath, expectedBridgeName, expectedStore, expectedLifecycle, expectedRecordClass] of routeExpectations) {
    const calls = [];
    const bridgeMocks = new Proxy({}, {
      get: (_target, property) => async (...args) => {
        calls.push({ name: String(property), args });
        return { ok: true, bridge: String(property) };
      },
    });
    const route = loadRouteModule(relativePath, bridgeMocks);
    const response = await route.GET(getRequest("?truth_lane=historical_imported&type=equity"));

    assert.equal(response.status, 200);
    assert.deepEqual(response.body, { ok: true, bridge: expectedBridgeName });
    assert.equal(response.headers["x-strategy-lab-store"], expectedStore);
    assert.equal(response.headers["x-strategy-lab-lifecycle"], expectedLifecycle);
    assert.equal(response.headers["x-strategy-lab-record-class"], expectedRecordClass);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].name, expectedBridgeName);
  }
});

test("Strategy Lab mutation routes reject missing or wrong intent before bridge calls", async () => {
  const intent = loadStrategyLabIntentModule();
  const routeExpectations = [
    ["src/app/api/backtest/route.ts", "POST", "run_replay_backtest"],
    ["src/app/api/profile/route.ts", "PUT", "save_strategy_profile"],
  ];
  const bridgeMocks = new Proxy({}, {
    get: () => () => {
      throw new Error("strategy lab mutation should not reach bridge without matching intent");
    },
  });

  for (const [relativePath, methodName, expectedIntent] of routeExpectations) {
    const route = loadRouteModule(relativePath, bridgeMocks);
    const missingIntentResponse = await route[methodName](
      requestWithIntent(intent.STRATEGY_LAB_MUTATION_HEADER, null)
    );
    assert.equal(missingIntentResponse.status, 428);
    assert.match(missingIntentResponse.body.error, new RegExp(expectedIntent));

    const wrongIntentResponse = await route[methodName](
      requestWithIntent(intent.STRATEGY_LAB_MUTATION_HEADER, "wrong_intent")
    );
    assert.equal(wrongIntentResponse.status, 428);
    assert.match(wrongIntentResponse.body.error, new RegExp(expectedIntent));
  }
});

test("Strategy Lab mutation routes reach the bridge only with matching intent", async () => {
  const intent = loadStrategyLabIntentModule();
  const routeExpectations = [
    ["src/app/api/backtest/route.ts", "POST", "run_replay_backtest", "runBacktest", "latest_replay_artifacts", "replay_run", "backtest_result"],
    ["src/app/api/profile/route.ts", "PUT", "save_strategy_profile", "saveProfile", "strategy_profile_files", "profile_save", "strategy_profile"],
  ];

  for (const [
    relativePath,
    methodName,
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
    const request = requestWithIntent(
      intent.STRATEGY_LAB_MUTATION_HEADER,
      expectedIntent,
      JSON.stringify({ type: "equity", updates: {}, truth_lane: "historical_imported" })
    );
    const response = await route[methodName](request);

    assert.equal(response.status, 200);
    if (expectedBridgeName === "saveProfile") {
      assert.equal(JSON.stringify(response.body), JSON.stringify({ ok: true }));
    } else {
      assert.equal(
        JSON.stringify(response.body),
        JSON.stringify({ ok: true, bridge: expectedBridgeName })
      );
    }
    assert.equal(response.headers["x-strategy-lab-store"], expectedStore);
    assert.equal(response.headers["x-strategy-lab-lifecycle"], expectedLifecycle);
    assert.equal(response.headers["x-strategy-lab-record-class"], expectedRecordClass);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].name, expectedBridgeName);
  }
});

test("Strategy Lab component POST and PUT use mutation intent headers", () => {
  const source = fs.readFileSync(
    path.join(ROOT, "src", "components", "strategy", "StrategyView.tsx"),
    "utf8"
  );

  assert.match(source, /strategyLabMutationHeaders\("run_replay_backtest"\)/);
  assert.match(source, /strategyLabMutationHeaders\("save_strategy_profile"\)/);
});
