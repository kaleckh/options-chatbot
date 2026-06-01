const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");

const ROOT = path.join(__dirname, "..", "..");

function loadClientJsonModule() {
  const sourcePath = path.join(ROOT, "src", "lib", "client-json.ts");
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
      console,
      DOMException,
      exports: module.exports,
      fetch,
      module,
      require,
      window: {
        clearTimeout,
        setTimeout,
      },
    },
    { filename: sourcePath }
  );
  return module.exports;
}

test("readJsonResponseOrThrow returns successful JSON", async () => {
  const { readJsonResponseOrThrow } = loadClientJsonModule();
  const response = new Response(JSON.stringify({ ok: true }), {
    headers: { "content-type": "application/json" },
    status: 200,
  });

  const payload = await readJsonResponseOrThrow(response, "Route");
  assert.equal(payload.ok, true);
});

test("readJsonResponseOrThrow uses payload error messages", async () => {
  const { readJsonResponseOrThrow } = loadClientJsonModule();
  const response = new Response(JSON.stringify({ error: "Backend down" }), {
    headers: { "content-type": "application/json" },
    status: 503,
  });

  await assert.rejects(
    () => readJsonResponseOrThrow(response, "Route"),
    /Backend down/
  );
});

test("readJsonResponseOrThrow describes HTML proxy failures", async () => {
  const { readJsonResponseOrThrow } = loadClientJsonModule();
  const response = new Response("<!DOCTYPE html><html><body>Not Found</body></html>", {
    headers: { "content-type": "text/html; charset=utf-8" },
    status: 404,
  });

  await assert.rejects(
    () => readJsonResponseOrThrow(response, "Tracked open positions"),
    /Tracked open positions received HTML instead of JSON with status 404/
  );
});
