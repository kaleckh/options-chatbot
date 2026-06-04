const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "..");
const TEST_ENV = {
  OPTIONS_LOCAL_OPERATOR_TOKEN: "operator-test-token",
  OPTIONS_LOCAL_OPERATOR_SESSION_SECRET: "operator-session-secret",
};

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

function loadOperatorAuthModule(env = TEST_ENV) {
  const sourcePath = path.join(ROOT, "src", "lib", "operator-auth.ts");
  const transpiled = transpileTsFile(sourcePath);
  const module = { exports: {} };
  const localRequire = (specifier) => {
    if (specifier === "next/server") return nextResponseMock();
    return require(specifier);
  };

  vm.runInNewContext(
    transpiled,
    {
      Buffer,
      console,
      Date,
      exports: module.exports,
      module,
      process: { env },
      require: localRequire,
    },
    { filename: sourcePath }
  );

  return module.exports;
}

function loadRouteLifecycleModule(env = TEST_ENV) {
  return runCommonJsModule(
    path.join(ROOT, "src", "lib", "route-lifecycle", "routeContracts.ts"),
    {},
    env
  );
}

async function readJsonObject(req, options = {}) {
  const text = await req.text();
  if (!text.trim()) return options.defaultValue ?? null;
  try {
    const body = JSON.parse(text);
    if (!body || typeof body !== "object" || Array.isArray(body)) return null;
    return body;
  } catch {
    return null;
  }
}

function runCommonJsModule(sourcePath, requireMap = {}, env = TEST_ENV) {
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
      Date,
      exports: module.exports,
      module,
      process: { env },
      require: localRequire,
    },
    { filename: sourcePath }
  );

  return module.exports;
}

function createRouteLifecycleApiUtils(routeContracts, nextServer, operatorAuth, options = {}) {
  const routeReadJsonObject = options.readJsonObject || readJsonObject;
  return {
    requireLocalOperator: operatorAuth.requireLocalOperator,
    readJsonObject: routeReadJsonObject,
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

function loadProtectedRouteModule(relativePath, bridgeMocks, options = {}) {
  const env = options.env || TEST_ENV;
  const operatorAuth = loadOperatorAuthModule(env);
  const routeContracts = loadRouteLifecycleModule(env);
  const nextServer = nextResponseMock();
  const apiUtils = createRouteLifecycleApiUtils(routeContracts, nextServer, operatorAuth, {
    ...options,
    readJsonObject: options.readJsonObject || (() => {
      throw new Error("request body should not be parsed before local operator auth");
    }),
  });

  return {
    route: runCommonJsModule(
      path.join(ROOT, relativePath),
      {
        "@/app/api/_utils": apiUtils,
        "@/lib/python-bridge": bridgeMocks,
        "next/server": nextServer,
      },
      env
    ),
    routeContracts,
  };
}

function loadOperatorSessionRouteModule(env = TEST_ENV) {
  const operatorAuth = loadOperatorAuthModule(env);
  const routeContracts = loadRouteLifecycleModule(env);
  const nextServer = nextResponseMock();
  const apiUtils = createRouteLifecycleApiUtils(routeContracts, nextServer, operatorAuth);

  return {
    route: runCommonJsModule(
      path.join(ROOT, "src", "app", "api", "operator", "session", "route.ts"),
      {
        "@/app/api/_utils": apiUtils,
        "@/lib/operator-auth": operatorAuth,
        "next/server": nextServer,
      },
      env
    ),
    routeContracts,
    operatorAuth,
  };
}

function request(headers = {}, cookieValue = "", bodyText = "") {
  const normalizedHeaders = Object.entries(headers).reduce((acc, [name, value]) => {
    acc[name.toLowerCase()] = value;
    return acc;
  }, {});
  return {
    headers: {
      get: (name) => normalizedHeaders[name.toLowerCase()] ?? null,
    },
    cookies: {
      get: (name) => {
        if (name !== "options_local_operator_session" || !cookieValue) return undefined;
        return { value: cookieValue };
      },
    },
    text: async () => bodyText,
  };
}

function jsonRequest(body, headers = {}, cookieValue = "") {
  return request(headers, cookieValue, JSON.stringify(body));
}

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

function assertOptionsRouteHeaders(response, routeContracts, contractId) {
  const contract = routeContracts.getOptionsRouteLifecycleContract(contractId);
  assert.equal(response.headers["x-options-route-contract"], contractId);
  assert.equal(response.headers["x-options-route-family"], contract.family);
  assert.equal(response.headers["x-options-route-store"], contract.store);
  assert.equal(response.headers["x-options-route-lifecycle"], contract.lifecycle);
  assert.equal(response.headers["x-options-route-record-class"], contract.recordClass);
}

test("local operator auth fails closed when the token is not configured", () => {
  const operatorAuth = loadOperatorAuthModule({});

  const response = operatorAuth.requireLocalOperator(
    request({ "x-options-operator-token": "operator-test-token" })
  );

  assert.equal(response.status, 401);
  assert.match(response.body.error, /OPTIONS_LOCAL_OPERATOR_TOKEN/);
});

test("local operator auth accepts the private header or bearer token", () => {
  const operatorAuth = loadOperatorAuthModule();

  assert.equal(
    operatorAuth.requireLocalOperator(
      request({ "x-options-operator-token": "operator-test-token" })
    ),
    null
  );
  assert.equal(
    operatorAuth.requireLocalOperator(
      request({ authorization: "Bearer operator-test-token" })
    ),
    null
  );

  const wrong = operatorAuth.requireLocalOperator(
    request({ "x-options-operator-token": "wrong-token" })
  );
  assert.equal(wrong.status, 401);
  assert.match(wrong.body.error, /Local operator authorization/);
});

test("local operator auth accepts signed session cookies without exposing the token", () => {
  const operatorAuth = loadOperatorAuthModule();
  const cookieValue = operatorAuth.createLocalOperatorSessionCookieValue();

  assert.equal(operatorAuth.requireLocalOperator(request({}, cookieValue)), null);

  const tampered = operatorAuth.requireLocalOperator(request({}, `${cookieValue}x`));
  assert.equal(tampered.status, 401);
});

test("all browser-facing mutation and tool routes require local operator auth", () => {
  const routeRoot = path.join(ROOT, "src", "app", "api");
  const routeFiles = [];
  const pending = [routeRoot];
  while (pending.length) {
    const current = pending.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const entryPath = path.join(current, entry.name);
      if (entry.isDirectory()) pending.push(entryPath);
      if (entry.isFile() && entry.name === "route.ts") routeFiles.push(entryPath);
    }
  }

  const unguarded = [];
  for (const routeFile of routeFiles) {
    const source = fs.readFileSync(routeFile, "utf8");
    if (!/export\s+async\s+function\s+(POST|PUT|PATCH|DELETE)\b/.test(source)) {
      continue;
    }
    const relativePath = path.relative(ROOT, routeFile).replace(/\\/g, "/");
    if (relativePath === "src/app/api/operator/session/route.ts") {
      continue;
    }
    if (!/requireLocalOperator\s*\(\s*req\s*\)/.test(source)) {
      unguarded.push(relativePath);
    }
  }

  assert.deepEqual(unguarded, []);
});

test("generic mutating proxy routes reject missing auth before body parsing or bridge calls", async () => {
  const routeExpectations = [
    ["src/app/api/scan/route.ts", ({ route }, req) => route.POST(req)],
    ["src/app/api/predictions/grade/route.ts", ({ route }, req) => route.POST(req)],
    [
      "src/app/api/tools/[name]/route.ts",
      ({ route }, req) => route.POST(req, { params: Promise.resolve({ name: "scan" }) }),
    ],
  ];

  for (const [relativePath, callRoute] of routeExpectations) {
    const bridgeCalls = [];
    const bridgeMocks = new Proxy({}, {
      get: (_target, property) => async (...args) => {
        bridgeCalls.push({ name: String(property), args });
        throw new Error("bridge should not be called before local operator auth");
      },
    });
    const loadedRoute = loadProtectedRouteModule(relativePath, bridgeMocks);

    for (const authHeaders of [{}, { "x-options-operator-token": "wrong-token" }]) {
      const response = await callRoute(loadedRoute, request(authHeaders));
      assert.equal(response.status, 401, relativePath);
      assert.match(response.body.error, /Local operator authorization/, relativePath);
      assert.deepEqual(bridgeCalls, [], relativePath);
    }
  }
});

test("generic mutating proxy routes allow valid local operator auth to reach bridge once", async () => {
  const routeExpectations = [
    {
      relativePath: "src/app/api/scan/route.ts",
      contractId: "scan_run",
      bridgeName: "runScan",
      requestBody: { universe: "regular-options" },
      callRoute: ({ route }, req) => route.POST(req),
      assertArgs: (args, body) => assert.deepEqual(plain(args), [body]),
    },
    {
      relativePath: "src/app/api/predictions/grade/route.ts",
      contractId: "predictions_grade",
      bridgeName: "gradePredictions",
      requestBody: { ids: [1, 2] },
      callRoute: ({ route }, req) => route.POST(req),
      assertArgs: (args, body) => assert.deepEqual(plain(args), [body]),
    },
    {
      relativePath: "src/app/api/tools/[name]/route.ts",
      contractId: "tool_dispatch",
      bridgeName: "callTool",
      requestBody: { args: { ticker: "MSFT" } },
      callRoute: ({ route }, req) => route.POST(
        req,
        { params: Promise.resolve({ name: "scan" }) }
      ),
      assertArgs: (args, body) => assert.deepEqual(plain(args), ["scan", body]),
    },
  ];

  for (const routeCase of routeExpectations) {
    const bridgeCalls = [];
    const bridgeMocks = new Proxy({}, {
      get: (_target, property) => async (...args) => {
        bridgeCalls.push({ name: String(property), args });
        return { ok: true, bridge: String(property) };
      },
    });
    const loadedRoute = loadProtectedRouteModule(routeCase.relativePath, bridgeMocks, {
      readJsonObject,
    });
    const response = await routeCase.callRoute(
      loadedRoute,
      jsonRequest(
        routeCase.requestBody,
        { "x-options-operator-token": TEST_ENV.OPTIONS_LOCAL_OPERATOR_TOKEN }
      )
    );

    assert.equal(response.status, 200, routeCase.relativePath);
    assertOptionsRouteHeaders(response, loadedRoute.routeContracts, routeCase.contractId);
    assert.equal(bridgeCalls.length, 1, routeCase.relativePath);
    assert.equal(bridgeCalls[0].name, routeCase.bridgeName, routeCase.relativePath);
    routeCase.assertArgs(bridgeCalls[0].args, routeCase.requestBody);
    if (routeCase.bridgeName === "callTool") {
      assert.deepEqual(plain(response.body), { result: { ok: true, bridge: "callTool" } });
    } else {
      assert.deepEqual(plain(response.body), { ok: true, bridge: routeCase.bridgeName });
    }
  }
});

test("operator session unlock rejects unconfigured or invalid token attempts", async () => {
  const unconfigured = loadOperatorSessionRouteModule({});
  const unconfiguredResponse = await unconfigured.route.POST(
    jsonRequest({ token: TEST_ENV.OPTIONS_LOCAL_OPERATOR_TOKEN })
  );
  assert.equal(unconfiguredResponse.status, 401);
  assert.match(unconfiguredResponse.body.error, /OPTIONS_LOCAL_OPERATOR_TOKEN/);
  assert.deepEqual(unconfiguredResponse.cookiesSet, []);

  const { route } = loadOperatorSessionRouteModule();
  for (const body of [{}, { token: "" }, { token: "wrong-token" }]) {
    const response = await route.POST(jsonRequest(body));
    assert.equal(response.status, 401);
    assert.equal(response.body.error, "Invalid local operator token.");
    assert.deepEqual(response.cookiesSet, []);
  }
});

test("operator session unlock sets only the expected local session cookie on valid token", async () => {
  const { route, routeContracts, operatorAuth } = loadOperatorSessionRouteModule();
  const response = await route.POST(
    jsonRequest({ token: TEST_ENV.OPTIONS_LOCAL_OPERATOR_TOKEN })
  );

  assert.equal(response.status, 200);
  assert.deepEqual(plain(response.body), { ok: true });
  assertOptionsRouteHeaders(response, routeContracts, "operator_session_unlock");
  assert.equal(response.cookiesSet.length, 1);

  const cookie = response.cookiesSet[0];
  assert.equal(cookie.name, "options_local_operator_session");
  assert.equal(cookie.httpOnly, true);
  assert.equal(cookie.sameSite, "strict");
  assert.equal(cookie.secure, false);
  assert.equal(cookie.path, "/");
  assert.equal(cookie.maxAge, 8 * 60 * 60);
  assert.notEqual(cookie.value, TEST_ENV.OPTIONS_LOCAL_OPERATOR_TOKEN);
  assert.equal(
    operatorAuth.requireLocalOperator(request({}, cookie.value)),
    null
  );
});

test("mutating browser route auth behavior has explicit test anchors", () => {
  const inventory = JSON.parse(
    fs.readFileSync(path.join(ROOT, "data", "contracts", "route-mutation-inventory.json"), "utf8")
  );
  const coverageByContract = new Map(Object.entries({
    scan_run: "tests/ui/operator-auth.test.js",
    predictions_grade: "tests/ui/operator-auth.test.js",
    tool_dispatch: "tests/ui/operator-auth.test.js",
    operator_session_unlock: "tests/ui/operator-auth.test.js",
    backtest_run: "tests/strategy-lab/replay-intent.test.js",
    profile_save: "tests/strategy-lab/replay-intent.test.js",
    tracked_positions_create: "tests/trading-desk/mutation-intent.test.js",
    tracked_positions_review: "tests/trading-desk/mutation-intent.test.js",
    tracked_positions_close: "tests/trading-desk/mutation-intent.test.js",
    suggested_trades_create: "tests/trading-desk/mutation-intent.test.js",
    suggested_trades_review: "tests/trading-desk/mutation-intent.test.js",
    suggested_trades_close: "tests/trading-desk/mutation-intent.test.js",
  }));

  const missingCoverage = [];
  for (const route of inventory.mounted_browser_routes) {
    if (!route.mutating) continue;
    for (const contractId of route.contract_ids) {
      if (!coverageByContract.has(contractId)) {
        missingCoverage.push(`${route.method} ${route.browser_path} ${contractId}`);
      }
    }
    assert.ok(
      ["local_operator", "next_only_session"].includes(route.auth_boundary),
      `${route.method} ${route.browser_path} should declare an auth boundary`
    );
  }

  assert.deepEqual(missingCoverage, []);
});
