const equitiesLegacyEngine = require("./engine");
const cryptoEngine = require("./crypto-engine");

function normalizeDayTradingMarket(value) {
  const normalized = String(value || "crypto").trim().toLowerCase();
  return normalized === "equities_legacy" ? "equities_legacy" : "crypto";
}

function resolveEngine(market) {
  return normalizeDayTradingMarket(market) === "equities_legacy"
    ? equitiesLegacyEngine
    : cryptoEngine;
}

function withMarketMetadata(payload, market) {
  const resolvedMarket = normalizeDayTradingMarket(market);
  return {
    ...payload,
    market: payload?.market || resolvedMarket,
    marketLabel: payload?.marketLabel || (resolvedMarket === "equities_legacy" ? "Equities Legacy" : "Crypto Profitability Pilot"),
  };
}

function getDayTradingSnapshot(options = {}) {
  const market = normalizeDayTradingMarket(options.market);
  return withMarketMetadata(resolveEngine(market).getDayTradingSnapshot({
    ...options,
    readOnly: true,
  }), market);
}

async function runDayTradingValidation(options = {}) {
  const market = normalizeDayTradingMarket(options.market);
  return withMarketMetadata(await resolveEngine(market).runDayTradingValidation(options), market);
}

async function buildMorningWatchlist(options = {}) {
  const market = normalizeDayTradingMarket(options.market);
  return withMarketMetadata(await resolveEngine(market).buildMorningWatchlist({
    ...options,
    readOnly: true,
    persistArtifacts: false,
  }), market);
}

async function runDayTradingExperiments(options = {}) {
  const market = normalizeDayTradingMarket(options.market);
  return withMarketMetadata(await resolveEngine(market).runDayTradingExperiments(options), market);
}

async function importCryptoDayTradingHistory(options = {}) {
  return cryptoEngine.importCryptoDayTradingHistory(options);
}

async function appendCryptoProfitabilityJournalEntry(entry) {
  return cryptoEngine.appendProfitabilityJournalEntry(entry);
}

module.exports = {
  DEFAULT_DAY_TRADING_CONFIG: {
    crypto: cryptoEngine.DEFAULT_DAY_TRADING_CONFIG,
    equities_legacy: equitiesLegacyEngine.DEFAULT_DAY_TRADING_CONFIG,
  },
  normalizeDayTradingMarket,
  getDayTradingSnapshot,
  runDayTradingValidation,
  buildMorningWatchlist,
  runDayTradingExperiments,
  importCryptoDayTradingHistory,
  appendCryptoProfitabilityJournalEntry,
  __markets: {
    crypto: cryptoEngine,
    equities_legacy: equitiesLegacyEngine,
  },
};
