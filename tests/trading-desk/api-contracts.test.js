const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const ROOT = path.join(__dirname, "..", "..");

function readRepoFile(relativePath) {
  return fs.readFileSync(path.join(ROOT, relativePath), "utf8");
}

test("Trading Desk API contracts name request and response envelopes", () => {
  const source = readRepoFile("src/lib/trading-desk/apiContracts.ts");
  const expectedContracts = [
    "TradingDeskListWindow",
    "TrackedPositionsListResponse",
    "GroupedTrackedPositionsResponse",
    "SuggestedTradesListResponse",
    "GroupedSuggestedTradesResponse",
    "CreateTrackedPositionRequest",
    "CreateTrackedPositionResponse",
    "ReviewTrackedPositionsRequest",
    "ReviewTrackedPositionsResponse",
    "CloseTrackedPositionRequest",
    "CloseTrackedPositionResponse",
    "CreateSuggestedTradeRequest",
    "CreateSuggestedTradeResponse",
    "ReviewSuggestedTradesRequest",
    "ReviewSuggestedTradesResponse",
    "CloseSuggestedTradeRequest",
    "CloseSuggestedTradeResponse",
    "TRADING_DESK_API_CONTRACTS",
  ];

  for (const contractName of expectedContracts) {
    assert.match(source, new RegExp(`\\b${contractName}\\b`));
  }
  assert.doesNotMatch(source, /CreateSuggestedTradeRequest\s*=\s*CreateTrackedPositionRequest/);
  assert.match(source, /export type CreateSuggestedTradeRequest = \{[\s\S]*contracts\?: number \| null;/);
});

test("Trading Desk response contracts preserve tracked versus suggested envelope split", () => {
  const source = readRepoFile("src/lib/trading-desk/apiContracts.ts");

  for (const responseName of [
    "CreateTrackedPositionResponse",
    "ReviewTrackedPositionsResponse",
    "CloseTrackedPositionResponse",
  ]) {
    const block = source.match(new RegExp(`export type ${responseName} =[\\s\\S]*?;\\n\\n`));
    assert.ok(block, `${responseName} should be declared`);
    assert.match(block[0], /position_event_persistence\?: PositionEventPersistence/);
  }

  for (const responseName of [
    "CreateSuggestedTradeResponse",
    "ReviewSuggestedTradesResponse",
    "CloseSuggestedTradeResponse",
  ]) {
    const block = source.match(new RegExp(`export type ${responseName} =[\\s\\S]*?;\\n\\n`));
    assert.ok(block, `${responseName} should be declared`);
    assert.match(block[0], /position_event_persistence\?: never/);
  }
});

test("Trading Desk backend helpers expose named contracts instead of opaque records", () => {
  const source = readRepoFile("src/lib/backend/positions.ts");
  const expectedReturnTypes = [
    "TrackedPositionsListResponse",
    "GroupedTrackedPositionsResponse",
    "CreateTrackedPositionResponse",
    "ReviewTrackedPositionsResponse",
    "CloseTrackedPositionResponse",
    "SuggestedTradesListResponse",
    "GroupedSuggestedTradesResponse",
    "CreateSuggestedTradeResponse",
    "ReviewSuggestedTradesResponse",
    "CloseSuggestedTradeResponse",
  ];

  assert.match(source, /from "@\/lib\/trading-desk\/apiContracts"/);
  assert.doesNotMatch(source, /Promise<Record<string, unknown>>/);
  assert.doesNotMatch(source, /payload: Record<string, unknown>/);
  for (const returnType of expectedReturnTypes) {
    assert.match(source, new RegExp(`Promise<${returnType}>`));
  }
});

test("Trading Desk route handlers parse request bodies through named contracts", () => {
  const routes = [
    ["src/app/api/positions/route.ts", "CreateTrackedPositionRequest"],
    ["src/app/api/positions/review/route.ts", "ReviewTrackedPositionsRequest"],
    ["src/app/api/positions/[id]/close/route.ts", "CloseTrackedPositionRequest"],
    ["src/app/api/suggested-trades/route.ts", "CreateSuggestedTradeRequest"],
    ["src/app/api/suggested-trades/review/route.ts", "ReviewSuggestedTradesRequest"],
    ["src/app/api/suggested-trades/[id]/close/route.ts", "CloseSuggestedTradeRequest"],
  ];

  for (const [relativePath, contractName] of routes) {
    const source = readRepoFile(relativePath);
    assert.match(source, new RegExp(`type \\{ ${contractName} \\}`));
    assert.match(source, new RegExp(`readJsonObject<${contractName}>`));
    assert.match(source, /jsonWithValidatedTradingDeskStore/);
  }
});

test("Trading Desk components use named response contracts for position and suggestion envelopes", () => {
  const source = [
    readRepoFile("src/components/predictions/PredictionsView.tsx"),
    readRepoFile("src/components/predictions/useTradingDeskCloseDialogs.ts"),
    readRepoFile("src/components/predictions/useTradingDeskRecords.ts"),
  ].join("\n");

  assert.doesNotMatch(source, /readJsonResponseOrThrow<\{\s*duplicate\?: boolean;\s*position\?:/);
  assert.doesNotMatch(source, /readJsonResponseOrThrow<\{\s*duplicate\?: boolean;\s*trade\?:/);
  assert.doesNotMatch(source, /readJsonResponseOrThrow<\{\s*positions\?:/);
  assert.doesNotMatch(source, /readJsonResponseOrThrow<\{\s*trades\?:/);
  for (const contractName of [
    "CreateTrackedPositionResponse",
    "CreateSuggestedTradeResponse",
    "CloseTrackedPositionResponse",
    "CloseSuggestedTradeResponse",
    "TrackedPositionsListResponse",
    "SuggestedTradesListResponse",
    "ReviewTrackedPositionsResponse",
    "ReviewSuggestedTradesResponse",
  ]) {
    assert.match(source, new RegExp(`\\b${contractName}\\b`));
  }
});

test("Living docs point to manual TypeScript contracts and the non-runtime schema bridge", () => {
  const docs = [
    "docs/index.md",
    "docs/api-and-storage.md",
    "docs/architecture-overview.md",
    "docs/PROJECT_CONTEXT.md",
    "docs/typescript-api-contracts.md",
    "docs/trading-desk-api-models.md",
    "docs/trading-desk-schema-bridge.md",
  ].map(readRepoFile).join("\n");

  assert.match(docs, /docs\/typescript-api-contracts\.md/);
  assert.match(docs, /src\/lib\/trading-desk\/apiContracts\.ts/);
  assert.match(docs, /src\/lib\/trading-desk\/apiResponseValidation\.ts/);
  assert.match(docs, /docs\/trading-desk-schema-bridge\.md/);
  assert.match(docs, /data\/contracts\/trading-desk-api-schema-bridge\.json/);
  assert.match(docs, /runtime_use/);
  assert.match(docs, /OpenAPI/);
  assert.match(docs, /generated TypeScript/);
});
