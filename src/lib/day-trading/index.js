const cryptoEngine = require("./crypto-engine");

function withMarketMetadata(payload) {
  return {
    ...payload,
    market: payload?.market || "crypto",
    marketLabel: payload?.marketLabel || "Crypto Profitability Pilot",
  };
}

function getDayTradingSnapshot(options = {}) {
  return withMarketMetadata(cryptoEngine.getDayTradingSnapshot({
    ...options,
    readOnly: true,
  }));
}

async function runDayTradingValidation(options = {}) {
  return withMarketMetadata(await cryptoEngine.runDayTradingValidation(options));
}

async function buildMorningWatchlist(options = {}) {
  return withMarketMetadata(await cryptoEngine.buildMorningWatchlist({
    ...options,
    readOnly: true,
    persistArtifacts: false,
  }));
}

async function runDayTradingExperiments(options = {}) {
  return withMarketMetadata(await cryptoEngine.runDayTradingExperiments(options));
}

async function importCryptoDayTradingHistory(options = {}) {
  return cryptoEngine.importCryptoDayTradingHistory(options);
}

async function appendCryptoProfitabilityJournalEntry(entry) {
  return cryptoEngine.appendProfitabilityJournalEntry(entry);
}

async function requestCryptoProfitabilityPreflightTicket(options = {}) {
  return cryptoEngine.requestProfitabilityPreflightTicket(options);
}

module.exports = {
  DEFAULT_DAY_TRADING_CONFIG: cryptoEngine.DEFAULT_DAY_TRADING_CONFIG,
  getDayTradingSnapshot,
  runDayTradingValidation,
  buildMorningWatchlist,
  runDayTradingExperiments,
  importCryptoDayTradingHistory,
  appendCryptoProfitabilityJournalEntry,
  requestCryptoProfitabilityPreflightTicket,
};
