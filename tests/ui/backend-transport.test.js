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
  class BackendTransportError extends Error {
    constructor(message, status) {
      super(message);
      this.name = "BackendTransportError";
      this.status = status;
    }
  }
  class BackendHttpError extends Error {
    constructor(message, status) {
      super(message);
      this.name = "BackendHttpError";
      this.status = status;
    }
  }

  vm.runInNewContext(
    transpiled,
    {
      AbortController,
      clearTimeout,
      console,
      DOMException,
      exports: module.exports,
      Headers,
      module,
      process: { env: {} },
      require: (specifier) => {
        if (specifier === "@/lib/backend/transport") {
          return { BackendHttpError, BackendTransportError };
        }
        if (specifier === "@/lib/trading-desk/mutationIntent") {
          return { TRADING_DESK_MUTATION_HEADER: "x-trading-desk-mutation" };
        }
        if (specifier === "@/lib/trading-desk/storeOwnership") {
          return { tradingDeskStoreHeaders: () => ({}), validateTradingDeskApiResponse: () => ({ ok: true }) };
        }
        if (specifier === "@/lib/trading-desk/apiResponseValidation") {
          return { validateTradingDeskApiResponse: () => ({ ok: true }) };
        }
        if (specifier === "@/lib/strategy-lab/replayIntent") {
          return {
            STRATEGY_LAB_MUTATION_HEADER: "x-strategy-lab-mutation",
            strategyLabRouteHeaders: () => ({}),
          };
        }
        if (specifier === "@/lib/route-lifecycle/routeContracts") {
          return { optionsRouteLifecycleHeaders: () => ({}) };
        }
        if (specifier === "@/lib/operator-auth") {
          return {};
        }
        if (specifier === "next/server") {
          return {
            NextResponse: {
              json: (body, init = {}) => ({ body, status: init.status ?? 200, headers: init.headers ?? {} }),
            },
          };
        }
        return require(specifier);
      },
      setTimeout,
    },
    { filename: sourcePath }
  );

  return { ...module.exports, BackendHttpError, BackendTransportError };
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

test("backend mutation helpers preserve explicit intent headers", async () => {
  const calls = [];
  const transport = loadTransportModule(
    { PYTHON_BACKEND_URL: "http://backend.test", OPTIONS_BACKEND_API_TOKEN: "" },
    async (_url, init = {}) => {
      calls.push({ method: init.method, headers: new Headers(init.headers) });
      return new Response("{}", { status: 200 });
    }
  );

  await transport.postBackendJson("/api/positions", { ok: true }, "failed", {
    "x-trading-desk-mutation": "create_tracked_position",
  });
  await transport.putBackendJson("/api/profile", { ok: true }, "failed", {
    "x-strategy-lab-mutation": "save_strategy_profile",
  });

  assert.equal(calls.length, 2);
  assert.equal(calls[0].method, "POST");
  assert.equal(calls[0].headers.get("x-trading-desk-mutation"), "create_tracked_position");
  assert.equal(calls[1].method, "PUT");
  assert.equal(calls[1].headers.get("x-strategy-lab-mutation"), "save_strategy_profile");
});

test("backend transport raises typed timeout errors with 504 status", async () => {
  const transport = loadTransportModule(
    {
      PYTHON_BACKEND_URL: "http://backend.test",
      PYTHON_BACKEND_TIMEOUT_MS: "5",
    },
    async (_url, init = {}) => {
      await new Promise((_resolve, reject) => {
        init.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
      });
      return new Response("{}", { status: 200 });
    }
  );

  await assert.rejects(
    () => transport.fetchBackendResponse("/api/slow"),
    (error) => {
      assert.equal(error.name, "BackendTransportError");
      assert.equal(error.status, 504);
      assert.match(error.message, /timed out/);
      return true;
    }
  );
});

test("backend transport raises typed network errors with 502 status", async () => {
  const transport = loadTransportModule(
    {
      PYTHON_BACKEND_URL: "http://backend.test",
    },
    async () => {
      throw new TypeError("fetch failed");
    }
  );

  await assert.rejects(
    () => transport.fetchBackendResponse("/api/downstream"),
    (error) => {
      assert.equal(error.name, "BackendTransportError");
      assert.equal(error.status, 502);
      assert.match(error.message, /fetch failed/);
      return true;
    }
  );
});

test("backend transport propagates caller aborts as typed 499 errors", async () => {
  const controller = new AbortController();
  const transport = loadTransportModule(
    {
      PYTHON_BACKEND_URL: "http://backend.test",
      PYTHON_BACKEND_TIMEOUT_MS: "5000",
    },
    async (_url, init = {}) => {
      await new Promise((resolve, reject) => {
        init.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
        setTimeout(resolve, 50);
      });
      return new Response("{}", { status: 200 });
    }
  );

  const pending = transport.fetchBackendResponse("/api/abort", { signal: controller.signal });
  controller.abort();

  await assert.rejects(
    () => pending,
    (error) => {
      assert.equal(error.name, "BackendTransportError");
      assert.equal(error.status, 499);
      assert.match(error.message, /aborted by caller/);
      return true;
    }
  );
});

test("backend transport treats plain AbortError objects as caller aborts", async () => {
  const controller = new AbortController();
  const transport = loadTransportModule(
    {
      PYTHON_BACKEND_URL: "http://backend.test",
      PYTHON_BACKEND_TIMEOUT_MS: "5000",
    },
    async (_url, init = {}) => {
      await new Promise((resolve, reject) => {
        init.signal.addEventListener("abort", () => {
          const error = new Error("Aborted");
          error.name = "AbortError";
          reject(error);
        });
        setTimeout(resolve, 50);
      });
      return new Response("{}", { status: 200 });
    }
  );

  const pending = transport.fetchBackendResponse("/api/abort", { signal: controller.signal });
  controller.abort();

  await assert.rejects(
    () => pending,
    (error) => {
      assert.equal(error.name, "BackendTransportError");
      assert.equal(error.status, 499);
      assert.match(error.message, /aborted by caller/);
      return true;
    }
  );
});

test("api jsonError preserves deliberate backend 503 messages while sanitizing 500s", () => {
  const apiUtils = loadApiUtilsModule();

  const unavailable = apiUtils.jsonError(
    new apiUtils.BackendHttpError("Tracked positions storage unavailable: DATABASE_URL is not configured.", 503),
    "Failed to fetch tracked positions"
  );
  const internal = apiUtils.jsonError(
    new apiUtils.BackendHttpError("traceback details", 500),
    "Failed to fetch tracked positions"
  );

  assert.equal(unavailable.status, 503);
  assert.equal(unavailable.body.error, "Tracked positions storage unavailable: DATABASE_URL is not configured.");
  assert.equal(internal.status, 500);
  assert.equal(internal.body.error, "Failed to fetch tracked positions");
});

test("current-policy historical picks route uses backend transport instead of direct artifact reads", () => {
  const routeSource = readRepoFile("src/app/api/current-policy-historical-picks/route.ts");
  const supportSource = readRepoFile("src/lib/backend/support.ts");

  assert.match(routeSource, /getCurrentPolicyHistoricalPicks/);
  assert.doesNotMatch(routeSource, /from "fs"/);
  assert.doesNotMatch(routeSource, /current_policy_historical_picks_latest\.json/);
  assert.match(supportSource, /\/api\/current-policy-historical-picks/);
});
