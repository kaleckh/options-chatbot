const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "..");

function loadTransportModule(env, fetchImpl) {
  const sourcePath = path.join(ROOT, "src", "lib", "backend", "transport.ts");
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
      AbortController,
      clearTimeout,
      console,
      DOMException,
      exports: module.exports,
      fetch: fetchImpl,
      Headers,
      module,
      process: { env },
      require,
      setTimeout,
    },
    { filename: sourcePath }
  );

  return module.exports;
}

function loadApiUtilsModule() {
  const sourcePath = path.join(ROOT, "src", "app", "api", "_utils.ts");
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
  const BackendHttpError = loadTransportModule(
    { PYTHON_BACKEND_URL: "http://backend.test" },
    async () => new Response("{}")
  ).BackendHttpError;
  const localRequire = (specifier) => {
    if (specifier === "next/server") {
      return {
        NextResponse: {
          json: (body, init = {}) => ({ body, status: init.status ?? 200, headers: init.headers ?? {} }),
        },
      };
    }
    if (specifier === "@/lib/backend/transport") return { BackendHttpError };
    if (specifier === "@/lib/operator-auth") return {};
    if (specifier === "@/lib/trading-desk/mutationIntent") return {};
    if (specifier === "@/lib/trading-desk/storeOwnership") {
      return { tradingDeskStoreHeaders: () => ({}) };
    }
    if (specifier === "@/lib/trading-desk/apiResponseValidation") {
      return { validateTradingDeskApiResponse: () => ({ ok: true }) };
    }
    if (specifier === "@/lib/strategy-lab/replayIntent") {
      return { strategyLabRouteHeaders: () => ({}) };
    }
    if (specifier === "@/lib/route-lifecycle/routeContracts") {
      return { optionsRouteLifecycleHeaders: () => ({}) };
    }
    return require(specifier);
  };

  vm.runInNewContext(
    transpiled,
    {
      console: { error: () => {} },
      exports: module.exports,
      module,
      require: localRequire,
    },
    { filename: sourcePath }
  );

  return { ...module.exports, BackendHttpError };
}

test("backend transport forwards configured backend API token", async () => {
  const calls = [];
  const transport = loadTransportModule(
    {
      PYTHON_BACKEND_URL: "http://backend.test",
      OPTIONS_BACKEND_API_TOKEN: "secret-token",
    },
    async (url, init = {}) => {
      calls.push({ url, headers: new Headers(init.headers) });
      return new Response("{}", { status: 200 });
    }
  );

  await transport.fetchBackendResponse("/api/health", {
    headers: { "Content-Type": "application/json" },
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://backend.test/api/health");
  assert.equal(calls[0].headers.get("Content-Type"), "application/json");
  assert.equal(calls[0].headers.get("x-options-backend-token"), "secret-token");
});

test("backend transport omits backend API token when unset", async () => {
  const calls = [];
  const transport = loadTransportModule(
    { PYTHON_BACKEND_URL: "http://backend.test", OPTIONS_BACKEND_API_TOKEN: "" },
    async (_url, init = {}) => {
      calls.push({ headers: new Headers(init.headers) });
      return new Response("{}", { status: 200 });
    }
  );

  await transport.fetchBackendResponse("/api/health");

  assert.equal(calls.length, 1);
  assert.equal(calls[0].headers.get("x-options-backend-token"), null);
});

test("jsonError masks generic server exception details", () => {
  const apiUtils = loadApiUtilsModule();

  const response = apiUtils.jsonError(
    new Error("C:\\secret\\provider detail"),
    "Failed to fetch backend data"
  );

  assert.equal(response.status, 500);
  assert.equal(response.body.error, "Failed to fetch backend data");
});

test("jsonError masks backend server exception details", () => {
  const apiUtils = loadApiUtilsModule();

  const response = apiUtils.jsonError(
    new apiUtils.BackendHttpError(
      "C:\\secret\\provider detail",
      500,
      { detail: "C:\\secret\\provider detail" }
    ),
    "Failed to fetch backend data"
  );

  assert.equal(response.status, 500);
  assert.equal(response.body.error, "Failed to fetch backend data");
  assert.equal(response.body.details, undefined);
});
