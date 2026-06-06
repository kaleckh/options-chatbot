const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");
const ts = require("typescript");
const React = require("react");
const ReactDOMServer = require("react-dom/server");

const ROOT = path.join(__dirname, "..", "..");
const REQUIRED_MOBILE_CONTRACT_PROPS = [
  "mobileTitleCol",
  "mobileSubtitleCol",
  "mobilePriorityCols",
];

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

function collectTsxFiles(dir) {
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectTsxFiles(fullPath));
    } else if (entry.isFile() && fullPath.endsWith(".tsx")) {
      files.push(fullPath);
    }
  }
  return files;
}

function findProductionFinTableUsages() {
  const files = collectTsxFiles(path.join(ROOT, "src"));
  const usages = [];

  for (const file of files) {
    const source = fs.readFileSync(file, "utf8");
    if (!source.includes("<FinTable")) continue;

    const sourceFile = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    const visit = (node) => {
      if (
        (ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) &&
        node.tagName.getText(sourceFile) === "FinTable"
      ) {
        const props = new Set(
          node.attributes.properties
            .filter(ts.isJsxAttribute)
            .map((attribute) => attribute.name.getText(sourceFile))
        );
        const line = ts.getLineAndCharacterOfPosition(sourceFile, node.getStart(sourceFile)).line + 1;
        usages.push({ file, line, props });
      }
      ts.forEachChild(node, visit);
    };

    visit(sourceFile);
  }

  return usages;
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

test("production FinTable usages declare explicit mobile card contracts", () => {
  const usages = findProductionFinTableUsages();
  assert.equal(usages.length, 12);

  const missing = usages.flatMap((usage) => {
    const missingProps = REQUIRED_MOBILE_CONTRACT_PROPS.filter((prop) => !usage.props.has(prop));
    if (missingProps.length === 0) return [];
    const relativeFile = path.relative(ROOT, usage.file);
    return [`${relativeFile}:${usage.line} missing ${missingProps.join(", ")}`];
  });

  assert.deepEqual(missing, []);
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
