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

function runCommonJsModule(sourcePath, requireMap) {
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
      process: { env: { NODE_ENV: "test" } },
      require: localRequire,
    },
    { filename: sourcePath }
  );

  return module.exports;
}

function nextResponseMock() {
  return {
    NextResponse: {
      json: (body, init = {}) => {
        const response = {
          body,
          status: init.status ?? 200,
          headers: init.headers ?? {},
          cookiesSet: [],
          cookies: {
            set: (cookie) => response.cookiesSet.push(cookie),
          },
        };
        return response;
      },
    },
  };
}

function loadRouteContracts() {
  return runCommonJsModule(
    path.join(ROOT, "src", "lib", "route-lifecycle", "routeContracts.ts"),
    {}
  );
}

function createApiUtilsMock(routeContracts, nextServer) {
  return {
    readJsonObject: async (req, options = {}) => {
      const text = await req.text();
      if (!text.trim()) return options.defaultValue ?? null;
      try {
        const body = JSON.parse(text);
        if (!body || typeof body !== "object" || Array.isArray(body)) return null;
        return body;
      } catch {
        return null;
      }
    },
    requireLocalOperator: () => null,
    jsonError: (err, fallbackMessage) => nextServer.NextResponse.json(
      { error: err instanceof Error ? err.message : fallbackMessage },
      { status: 500 }
    ),
    jsonWithRouteLifecycle: (body, contractId, init = {}) => nextServer.NextResponse.json(
      body,
      {
        ...init,
        headers: {
          ...routeContracts.optionsRouteLifecycleHeaders(contractId),
          ...(init.headers || {}),
        },
      }
    ),
  };
}

function loadRouteModule(relativePath, bridgeMocks = {}, operatorAuthMocks = {}) {
  const routeContracts = loadRouteContracts();
  const nextServer = nextResponseMock();
  const apiUtils = createApiUtilsMock(routeContracts, nextServer);
  const operatorAuth = {
    createLocalOperatorSessionCookieValue: () => "signed-session-cookie",
    isLocalOperatorAuthorized: () => true,
    isLocalOperatorToken: (token) => token === "open-sesame",
    LOCAL_OPERATOR_SESSION_COOKIE: "options_local_operator_session",
    LOCAL_OPERATOR_SESSION_MAX_AGE_SECONDS: 86_400,
    LOCAL_OPERATOR_TOKEN_ENV: "OPTIONS_LOCAL_OPERATOR_TOKEN",
    localOperatorAuthConfigured: () => true,
    ...operatorAuthMocks,
  };

  return {
    route: runCommonJsModule(
      path.join(ROOT, relativePath),
      {
        "@/app/api/_utils": apiUtils,
        "../_utils": apiUtils,
        "../../_utils": apiUtils,
        "@/lib/operator-auth": operatorAuth,
        "@/lib/python-bridge": bridgeMocks,
        "next/server": nextServer,
      }
    ),
    routeContracts,
  };
}

function request(body = {}) {
  return {
    headers: { get: () => null },
    cookies: { get: () => undefined },
    text: async () => JSON.stringify(body),
  };
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function assertRouteHeaders(response, routeContracts, contractId) {
  const contract = routeContracts.getOptionsRouteLifecycleContract(contractId);
  assert.equal(response.headers["x-options-route-contract"], contractId);
  assert.equal(response.headers["x-options-route-family"], contract.family);
  assert.equal(response.headers["x-options-route-store"], contract.store);
  assert.equal(response.headers["x-options-route-lifecycle"], contract.lifecycle);
  assert.equal(response.headers["x-options-route-record-class"], contract.recordClass);
}

const EXPECTED_ROUTE_CONTRACTS = [
  ["src/app/api/scan/route.ts", "scan_run"],
  ["src/app/api/predictions/route.ts", "predictions_read"],
  ["src/app/api/predictions/grade/route.ts", "predictions_grade"],
  ["src/app/api/risk-settings/route.ts", "risk_settings_read"],
  ["src/app/api/options-profit/status/route.ts", "options_profit_status_read"],
  ["src/app/api/operator/session/route.ts", "operator_session_status"],
  ["src/app/api/operator/session/route.ts", "operator_session_unlock"],
  ["src/app/api/sectors/route.ts", "sectors_read"],
  ["src/app/api/tools/[name]/route.ts", "tool_dispatch"],
];

test("generic route lifecycle manifest covers every mounted non-domain route once", () => {
  const routeContracts = loadRouteContracts();
  const contracts = Object.values(routeContracts.OPTIONS_ROUTE_LIFECYCLE_CONTRACTS);
  const ids = contracts.map((contract) => contract.id);

  assert.deepEqual(new Set(ids).size, ids.length);
  assert.deepEqual(
    ids.sort(),
    EXPECTED_ROUTE_CONTRACTS.map(([, contractId]) => contractId).sort()
  );
});

test("generic route lifecycle routes return through jsonWithRouteLifecycle", () => {
  for (const [relativePath, contractId] of EXPECTED_ROUTE_CONTRACTS) {
    const source = readRepoFile(relativePath);
    assert.match(source, /jsonWithRouteLifecycle/);
    assert.match(
      source,
      new RegExp(`jsonWithRouteLifecycle\\([\\s\\S]*?,\\s*"${contractId}"`)
    );
  }
});

test("generic route lifecycle success responses keep bodies and add headers", async () => {
  const cases = [
    {
      path: "src/app/api/scan/route.ts",
      contractId: "scan_run",
      bridge: { runScan: async (body) => ({ echoed: body, picks: [] }) },
      call: (route) => route.POST(request({ universe: "regular-options" })),
      expectedBody: { echoed: { universe: "regular-options" }, picks: [] },
    },
    {
      path: "src/app/api/predictions/route.ts",
      contractId: "predictions_read",
      bridge: { getPredictions: async () => [{ ticker: "AAPL" }] },
      call: (route) => route.GET(),
      expectedBody: [{ ticker: "AAPL" }],
    },
    {
      path: "src/app/api/predictions/grade/route.ts",
      contractId: "predictions_grade",
      bridge: { gradePredictions: async (body) => ({ graded: body }) },
      call: (route) => route.POST(request({ ids: [1] })),
      expectedBody: { graded: { ids: [1] } },
    },
    {
      path: "src/app/api/risk-settings/route.ts",
      contractId: "risk_settings_read",
      bridge: { getRiskSettings: async () => ({ equity: { max_risk: 0.02 } }) },
      call: (route) => route.GET(),
      expectedBody: {
        current_settings: { max_risk: 0.02 },
        profiles: { equity: { max_risk: 0.02 } },
      },
    },
    {
      path: "src/app/api/sectors/route.ts",
      contractId: "sectors_read",
      bridge: { getSectorSentiments: async () => ({ technology: "bullish" }) },
      call: (route) => route.GET(),
      expectedBody: { technology: "bullish" },
    },
    {
      path: "src/app/api/tools/[name]/route.ts",
      contractId: "tool_dispatch",
      bridge: { callTool: async (name, body) => ({ name, body, ok: true }) },
      call: (route) => route.POST(
        request({ args: { ticker: "MSFT" } }),
        { params: Promise.resolve({ name: "diagnose" }) }
      ),
      expectedBody: {
        result: { name: "diagnose", body: { args: { ticker: "MSFT" } }, ok: true },
      },
    },
  ];

  for (const routeCase of cases) {
    const { route, routeContracts } = loadRouteModule(routeCase.path, routeCase.bridge);
    const response = await routeCase.call(route);

    assert.equal(response.status, 200, routeCase.path);
    assert.deepEqual(plain(response.body), routeCase.expectedBody, routeCase.path);
    assertRouteHeaders(response, routeContracts, routeCase.contractId);
  }
});

test("options profit route keeps backend timing headers with lifecycle headers", async () => {
  const { route, routeContracts } = loadRouteModule(
    "src/app/api/options-profit/status/route.ts",
    {
      getOptionsProfitStatusWithBackendHeaders: async () => ({
        body: { status: "ready" },
        headers: { "x-python-backend-duration-ms": "4.2" },
      }),
    }
  );

  const response = await route.GET();

  assert.deepEqual(plain(response.body), { status: "ready" });
  assert.equal(response.headers["x-python-backend-duration-ms"], "4.2");
  assertRouteHeaders(response, routeContracts, "options_profit_status_read");
});

test("operator session routes keep session cookie behavior with lifecycle headers", async () => {
  const { route, routeContracts } = loadRouteModule("src/app/api/operator/session/route.ts");

  const status = await route.GET(request({}));
  assert.deepEqual(plain(status.body), { configured: true, authorized: true });
  assertRouteHeaders(status, routeContracts, "operator_session_status");

  const unlock = await route.POST(request({ token: "open-sesame" }));
  assert.equal(unlock.body.ok, true);
  assertRouteHeaders(unlock, routeContracts, "operator_session_unlock");
  assert.equal(unlock.cookiesSet.length, 1);
  assert.equal(unlock.cookiesSet[0].name, "options_local_operator_session");
  assert.equal(unlock.cookiesSet[0].value, "signed-session-cookie");
  assert.equal(unlock.cookiesSet[0].httpOnly, true);
});
