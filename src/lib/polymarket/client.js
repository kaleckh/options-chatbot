/**
 * Polymarket API Client
 *
 * Wraps @polymarket/clob-client with config management, public data access,
 * and helper methods for the scanner, market-maker, and arb engine.
 */

const { ClobClient, Side, OrderType } = require("@polymarket/clob-client");
const { ethers } = require("ethers");
const https = require("https");
const fs = require("fs");
const path = require("path");

const CLOB_HOST = "https://clob.polymarket.com";
const GAMMA_HOST = "https://gamma-api.polymarket.com";
const CHAIN_ID = 137; // Polygon

// Neg-risk exchange contracts (for USDC approval)
const EXCHANGE_CONTRACTS = {
  ctfExchange: "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E",
  negRiskCtfExchange: "0xC5d563A36AE78145C45a50134d48A1215220f80a",
  negRiskAdapter: "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296",
};

const CONFIG_DIR = path.resolve(process.env.POLYMARKET_CONFIG_DIR || path.join(process.cwd(), "data", "polymarket"));
const CREDENTIALS_PATH = path.join(CONFIG_DIR, "credentials.json");
const STATE_PATH = path.join(CONFIG_DIR, "state.json");

function ensureDir(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function loadJson(filePath, fallback = null) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

function saveJson(filePath, data) {
  ensureDir(path.dirname(filePath));
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
}

// ---- Public API (no auth needed) ----

function httpGet(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers: { "User-Agent": "PolymarketBot/1.0" } }, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        try { resolve(JSON.parse(data)); }
        catch { reject(new Error("JSON parse failed: " + data.slice(0, 200))); }
      });
    }).on("error", reject);
  });
}

async function fetchAllEvents(options = {}) {
  const limit = options.limit || 2000;
  const all = [];
  for (let offset = 0; offset < limit; offset += 100) {
    const batch = await httpGet(
      GAMMA_HOST + "/events?limit=100&offset=" + offset + "&active=true&closed=false"
    );
    if (!Array.isArray(batch) || batch.length === 0) break;
    all.push(...batch);
    if (batch.length < 100) break;
  }
  return all;
}

async function fetchMarketOrderBook(tokenId) {
  return httpGet(CLOB_HOST + "/book?token_id=" + tokenId);
}

async function fetchMarketMidpoint(tokenId) {
  return httpGet(CLOB_HOST + "/midpoint?token_id=" + tokenId);
}

async function fetchTickSize(tokenId) {
  return httpGet(CLOB_HOST + "/tick-size?token_id=" + tokenId);
}

async function fetchNegRisk(tokenId) {
  return httpGet(CLOB_HOST + "/neg-risk?token_id=" + tokenId);
}

// ---- Authenticated Client ----

function loadCredentials() {
  const creds = loadJson(CREDENTIALS_PATH);
  if (!creds || !creds.privateKey) {
    return null;
  }
  return creds;
}

function saveCredentials(creds) {
  saveJson(CREDENTIALS_PATH, creds);
}

async function createAuthenticatedClient(options = {}) {
  const config = options.credentials || loadCredentials();
  if (!config || !config.privateKey) {
    throw new Error(
      "No credentials found. Create " + CREDENTIALS_PATH + " with:\n" +
      '{\n  "privateKey": "0xYOUR_POLYGON_WALLET_PRIVATE_KEY",\n  "funderAddress": "0xYOUR_WALLET_ADDRESS"\n}'
    );
  }

  const wallet = new ethers.Wallet(config.privateKey);
  const funderAddress = config.funderAddress || wallet.address;

  // Create the CLOB client
  const client = new ClobClient(
    CLOB_HOST,
    CHAIN_ID,
    wallet,
    undefined, // creds — will derive below
    config.signatureType || 0, // 0 = EOA
    funderAddress,
  );

  // Derive or load API keys
  let apiCreds = config.apiKey ? {
    key: config.apiKey,
    secret: config.apiSecret,
    passphrase: config.apiPassphrase,
  } : null;

  if (!apiCreds) {
    console.log("Deriving API keys from wallet...");
    apiCreds = await client.createOrDeriveApiKey();
    // Save for future use
    saveCredentials({
      ...config,
      apiKey: apiCreds.key,
      apiSecret: apiCreds.secret,
      apiPassphrase: apiCreds.passphrase,
    });
    console.log("API keys derived and saved.");
  }

  // Recreate client with API credentials
  const authedClient = new ClobClient(
    CLOB_HOST,
    CHAIN_ID,
    wallet,
    apiCreds,
    config.signatureType || 0,
    funderAddress,
  );

  return {
    client: authedClient,
    wallet,
    address: wallet.address,
    funderAddress,
  };
}

// ---- State Management ----

function loadState() {
  return loadJson(STATE_PATH, {
    positions: {},
    openOrders: {},
    pnl: { realized: 0, unrealized: 0 },
    tradeHistory: [],
    startedAt: null,
  });
}

function saveState(state) {
  saveJson(STATE_PATH, state);
}

// ---- Order Helpers ----

async function placeLimitOrder(client, options) {
  const { tokenId, side, price, size, negRisk, tickSize } = options;

  const orderOptions = {
    tokenID: tokenId,
    price,
    size,
    side: side === "buy" ? Side.BUY : Side.SELL,
  };

  const createOptions = {
    tickSize: tickSize || "0.01",
    negRisk: negRisk || false,
  };

  const signedOrder = await client.createOrder(orderOptions, createOptions);
  const response = await client.postOrder(signedOrder, OrderType.GTC);
  return response;
}

async function placeMarketOrder(client, options) {
  const { tokenId, side, amount, negRisk, tickSize } = options;

  const orderOptions = {
    tokenID: tokenId,
    amount,
    side: side === "buy" ? Side.BUY : Side.SELL,
    price: side === "buy" ? 0.99 : 0.01, // worst case price for market orders
  };

  const createOptions = {
    tickSize: tickSize || "0.01",
    negRisk: negRisk || false,
  };

  const signedOrder = await client.createMarketOrder(orderOptions, createOptions);
  const response = await client.postOrder(signedOrder, OrderType.FOK);
  return response;
}

async function cancelOrder(client, orderId) {
  return client.cancelOrder({ orderID: orderId });
}

async function cancelAllOrders(client) {
  return client.cancelAll();
}

async function getOpenOrders(client) {
  return client.getOpenOrders();
}

async function getBalanceAllowance(client, assetType = "USDC", tokenId) {
  const params = { asset_type: assetType };
  if (tokenId) params.token_id = tokenId;
  return client.getBalanceAllowance(params);
}

module.exports = {
  // Config
  CLOB_HOST,
  GAMMA_HOST,
  CHAIN_ID,
  EXCHANGE_CONTRACTS,
  CONFIG_DIR,
  CREDENTIALS_PATH,

  // Public API
  fetchAllEvents,
  fetchMarketOrderBook,
  fetchMarketMidpoint,
  fetchTickSize,
  fetchNegRisk,
  httpGet,

  // Auth
  loadCredentials,
  saveCredentials,
  createAuthenticatedClient,

  // State
  loadState,
  saveState,

  // Orders
  placeLimitOrder,
  placeMarketOrder,
  cancelOrder,
  cancelAllOrders,
  getOpenOrders,
  getBalanceAllowance,

  // SDK re-exports
  Side,
  OrderType,
};
