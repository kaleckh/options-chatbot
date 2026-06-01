const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");
const ReactDOMServer = require("react-dom/server");

const ROOT = path.join(__dirname, "..", "..");

function loadFinTable() {
  const sourcePath = path.join(ROOT, "src", "components", "ui", "FinTable.tsx");
  const source = fs.readFileSync(sourcePath, "utf8");
  const transpiled = ts.transpileModule(source, {
    compilerOptions: {
      esModuleInterop: true,
      jsx: ts.JsxEmit.ReactJSX,
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
    },
    fileName: sourcePath,
  }).outputText;
  const module = { exports: {} };

  vm.runInNewContext(
    transpiled,
    {
      console,
      exports: module.exports,
      module,
      require,
    },
    { filename: sourcePath }
  );

  return module.exports.default;
}

test("FinTable mobile cards use explicit title, subtitle, priority, and hidden columns", () => {
  const FinTable = loadFinTable();
  const html = ReactDOMServer.renderToStaticMarkup(
    React.createElement(FinTable, {
      data: [
        {
          Ticker: "AAPL",
          Trade: "CALL",
          Entry: "$1.20",
          "Live P&L": "+12.0%",
          Source: "desktop-only source detail",
          Action: React.createElement("button", null, "Review"),
        },
      ],
      mobileTitleCol: "Ticker",
      mobileSubtitleCol: "Live P&L",
      mobilePriorityCols: ["Trade", "Entry"],
      mobileHiddenCols: ["Source"],
      renderMode: "mobile",
    })
  );
  const mobileHtml = html;

  assert.match(mobileHtml, /ft-mobile-title[^>]*>AAPL/);
  assert.match(mobileHtml, /ft-mobile-subtitle[^>]*>\+12\.0%/);
  assert.ok(mobileHtml.indexOf(">Trade<") < mobileHtml.indexOf(">Entry<"));
  assert.doesNotMatch(mobileHtml, /desktop-only source detail/);
  assert.match(mobileHtml, /<button>Review<\/button>/);
});

test("FinTable renders only one responsive surface at a time", () => {
  const FinTable = loadFinTable();
  const data = [
    {
      Ticker: "AAPL",
      Trade: "CALL",
      Action: React.createElement("button", null, "Review"),
    },
  ];

  const desktopHtml = ReactDOMServer.renderToStaticMarkup(
    React.createElement(FinTable, { data, renderMode: "desktop" })
  );
  assert.match(desktopHtml, /<table class="ft-table"/);
  assert.doesNotMatch(desktopHtml, /ft-mobile-card/);
  assert.equal((desktopHtml.match(/<button>Review<\/button>/g) || []).length, 1);

  const mobileHtml = ReactDOMServer.renderToStaticMarkup(
    React.createElement(FinTable, { data, renderMode: "mobile" })
  );
  assert.match(mobileHtml, /ft-mobile-card/);
  assert.doesNotMatch(mobileHtml, /<table class="ft-table"/);
  assert.equal((mobileHtml.match(/<button>Review<\/button>/g) || []).length, 1);
});
