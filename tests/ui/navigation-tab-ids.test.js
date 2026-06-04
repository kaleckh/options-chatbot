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

function plain(value) {
  return JSON.parse(JSON.stringify(value));
}

test("main app tab ids are exported from one typed catalog", () => {
  const tabs = loadTsModule("src/lib/navigation/tabs.ts");

  assert.deepEqual(plain(tabs.MAIN_APP_TAB_IDS), ["predictions", "strategy"]);
  assert.equal(tabs.DEFAULT_MAIN_APP_TAB_ID, "predictions");
  assert.deepEqual(
    plain(tabs.MAIN_APP_TAB_LIST.map((tab) => tab.id)),
    plain(tabs.MAIN_APP_TAB_IDS)
  );
  assert.equal(tabs.getMainAppTab("predictions").title, "Trading Desk");
  assert.equal(tabs.getMainAppTab("strategy").subtitle, "Replay validation and policy tuning");
});

test("main shell components consume typed app tab ids", () => {
  const appShell = readRepoFile("src/components/layout/AppShell.tsx");
  const sidebar = readRepoFile("src/components/layout/Sidebar.tsx");
  const header = readRepoFile("src/components/layout/Header.tsx");

  assert.match(appShell, /useState<MainAppTabId>\(DEFAULT_MAIN_APP_TAB_ID\)/);
  assert.doesNotMatch(appShell, /useState<string>\("predictions"\)/);

  assert.match(sidebar, /activeTab: MainAppTabId/);
  assert.match(sidebar, /onTabChange: \(tab: MainAppTabId\) => void/);
  assert.match(sidebar, /MAIN_APP_TAB_LIST\.map/);
  assert.doesNotMatch(sidebar, /activeTab: string/);

  assert.match(header, /activeTab: MainAppTabId/);
  assert.match(header, /getMainAppTab\(activeTab\)/);
  assert.doesNotMatch(header, /activeTab: string/);
});
