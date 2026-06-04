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
