const { importCryptoDayTradingHistory } = require("../src/lib/day-trading");

function parseArgs(argv) {
  const args = {
    symbols: ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
    days: 90,
    input: undefined,
  };

  for (const raw of argv) {
    if (raw.startsWith("--symbols=")) {
      const values = String(raw.split("=")[1] || "")
        .split(",")
        .map((value) => value.trim().toUpperCase())
        .filter(Boolean);
      if (values.length > 0) args.symbols = values;
    }
    if (raw.startsWith("--days=")) {
      const value = Number(raw.split("=")[1]);
      if (Number.isFinite(value) && value > 0) args.days = Math.min(180, Math.round(value));
    }
    if (raw.startsWith("--minutes=")) {
      const value = Number(raw.split("=")[1]);
      if (Number.isFinite(value) && value > 0) args.minutes = value;
    }
    if (raw.startsWith("--input=")) {
      const value = String(raw.split("=")[1] || "").trim();
      if (value) args.input = value;
    }
  }

  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const report = await importCryptoDayTradingHistory(args);
  console.log(JSON.stringify(report, null, 2));
}

main().catch((err) => {
  console.error(`daytrading:import:crypto failed: ${err.message}`);
  process.exit(1);
});
