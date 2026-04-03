const { requestCryptoProfitabilityPreflightTicket } = require("../src/lib/day-trading");

function parseArgs(argv) {
  const parsed = {};
  for (const raw of argv) {
    if (!raw.startsWith("--")) continue;
    const [flag, ...rest] = raw.slice(2).split("=");
    parsed[flag] = rest.join("=");
  }
  return parsed;
}

function parseBoolean(value, label) {
  const normalized = String(value || "").trim().toLowerCase();
  if (["true", "1", "yes", "y"].includes(normalized)) return true;
  if (["false", "0", "no", "n"].includes(normalized)) return false;
  throw new Error(`${label} must be true or false`);
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const payload = {
    strategyId: String(args.setup || "").trim() || undefined,
    bars: args.bars === "all"
      ? "all"
      : (Number.isFinite(Number(args.bars)) ? Number(args.bars) : undefined),
    now: String(args.now || "").trim() || undefined,
    setup_match_confirmed: parseBoolean(args["setup-match-confirmed"], "setup-match-confirmed"),
    headline_lockout_checked: parseBoolean(args["headline-lockout-checked"], "headline-lockout-checked"),
    maker_limit_plan_confirmed: parseBoolean(args["maker-limit-plan-confirmed"], "maker-limit-plan-confirmed"),
  };

  const result = await requestCryptoProfitabilityPreflightTicket(payload);
  console.log(JSON.stringify({
    approved: result.approved,
    blocked: result.blocked,
    reasons: result.reasons,
    checklistFlags: result.checklistFlags,
    ticket: result.ticket,
    todayGate: result.systemGate?.todayGate || null,
    systemGate: result.systemGate || null,
  }, null, 2));
}

main().catch((error) => {
  console.error(`daytrading:preflight failed: ${error instanceof Error ? error.message : "unknown error"}`);
  process.exit(1);
});
