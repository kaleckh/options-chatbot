#!/usr/bin/env node
/**
 * Polymarket Wallet Setup
 *
 * Checks balances, approves USDC for Polymarket exchange contracts,
 * and verifies everything is ready to trade.
 */

const { ethers } = require("ethers");
const fs = require("fs");
const path = require("path");

const CONFIG_DIR = path.resolve(process.env.POLYMARKET_CONFIG_DIR || path.join(process.cwd(), "data", "polymarket"));
const CREDENTIALS_PATH = path.join(CONFIG_DIR, "credentials.json");
const POLYGON_RPC = "https://polygon-bor-rpc.publicnode.com";

// Polymarket exchange contracts that need USDC approval
const CONTRACTS_TO_APPROVE = [
  { name: "CTF Exchange", address: "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E" },
  { name: "NegRisk CTF Exchange", address: "0xC5d563A36AE78145C45a50134d48A1215220f80a" },
  { name: "NegRisk Adapter", address: "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296" },
];

// USDC on Polygon — check both native and bridged
const USDC_NATIVE_ADDRESS = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359";
const USDC_BRIDGED_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174";
// Polymarket uses USDC.e (bridged) — but let's detect which has balance
let USDC_ADDRESS = USDC_BRIDGED_ADDRESS;
const USDC_ABI = [
  "function balanceOf(address) view returns (uint256)",
  "function allowance(address owner, address spender) view returns (uint256)",
  "function approve(address spender, uint256 amount) returns (bool)",
  "function decimals() view returns (uint8)",
];

// Conditional Tokens (also needs approval)
const CT_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045";
const CT_ABI = [
  "function isApprovedForAll(address owner, address operator) view returns (bool)",
  "function setApprovalForAll(address operator, bool approved) returns (bool)",
];

function parseArgs(argv) {
  const options = {
    executeApprovals: false,
    allowanceUsd: null,
  };
  for (const arg of argv) {
    if (arg === "--live") {
      options.live = true;
    } else if (arg === "--confirm-allowance") {
      options.confirmAllowance = true;
    } else if (arg.startsWith("--allowance-usdc=")) {
      const value = Number(arg.slice("--allowance-usdc=".length));
      if (Number.isFinite(value) && value > 0) {
        options.allowanceUsd = value;
      }
    }
  }
  options.executeApprovals = Boolean(options.live && options.confirmAllowance);
  return options;
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const creds = JSON.parse(fs.readFileSync(CREDENTIALS_PATH, "utf8"));
  const provider = new ethers.providers.JsonRpcProvider(POLYGON_RPC);
  const wallet = new ethers.Wallet(creds.privateKey, provider);
  const address = wallet.address;

  console.log("Polymarket Wallet Setup");
  console.log("Address: " + address);
  console.log("Mode: " + (options.executeApprovals ? "live approvals" : "dry-run checks only"));
  if (!options.executeApprovals) {
    console.log("Approval transactions require --live --confirm-allowance.");
  }
  console.log("");
  const readinessBlockers = [];

  // Check balances
  console.log("--- Balances ---");
  const polBalance = await provider.getBalance(address);
  console.log("POL/MATIC: " + ethers.utils.formatEther(polBalance) + " ($" + (Number(ethers.utils.formatEther(polBalance)) * 0.4).toFixed(2) + " approx)");

  const usdc = new ethers.Contract(USDC_ADDRESS, USDC_ABI, wallet);
  const usdcBalance = await usdc.balanceOf(address);
  const usdcDecimals = await usdc.decimals();
  const usdcFormatted = Number(usdcBalance) / (10 ** usdcDecimals);
  console.log("USDC.e: $" + usdcFormatted.toFixed(2));
  console.log("");

  if (usdcFormatted < 1) {
    console.log("WARNING: No USDC.e balance. Fund the wallet before trading.");
    console.log("Send USDC to " + address + " on Polygon network.");
    process.exitCode = 1;
    return;
  }

  if (Number(ethers.utils.formatEther(polBalance)) < 0.01) {
    console.log("WARNING: Very low POL balance. Need gas for approvals and trades.");
    process.exitCode = 1;
    return;
  }

  // Check and set USDC approvals
  console.log("--- USDC Approvals ---");
  for (const contract of CONTRACTS_TO_APPROVE) {
    const allowance = await usdc.allowance(address, contract.address);
    const allowanceFormatted = Number(allowance) / (10 ** usdcDecimals);

    if (allowanceFormatted >= usdcFormatted) {
      console.log(contract.name + ": OK (allowance: $" + allowanceFormatted.toFixed(2) + ")");
    } else {
      const approvalAmount = options.allowanceUsd == null
        ? usdcBalance
        : ethers.utils.parseUnits(String(options.allowanceUsd), usdcDecimals);
      const approvalFormatted = Number(approvalAmount) / (10 ** usdcDecimals);
      if (!options.executeApprovals) {
        console.log(contract.name + ": DRY-RUN would approve $" + approvalFormatted.toFixed(2) + " USDC.e");
        readinessBlockers.push(contract.name + " USDC approval not confirmed");
        continue;
      }
      console.log(contract.name + ": Approving $" + approvalFormatted.toFixed(2) + " USDC.e...");
      try {
        const tx = await usdc.approve(contract.address, approvalAmount);
        console.log("  TX sent: " + tx.hash);
        await tx.wait();
        console.log("  Confirmed.");
      } catch (err) {
        console.log("  FAILED: " + err.message.slice(0, 100));
        readinessBlockers.push(contract.name + " USDC approval failed");
      }
    }
  }

  // Check and set Conditional Token approvals
  console.log("\n--- Conditional Token Approvals ---");
  const ct = new ethers.Contract(CT_ADDRESS, CT_ABI, wallet);
  for (const contract of CONTRACTS_TO_APPROVE) {
    const approved = await ct.isApprovedForAll(address, contract.address);
    if (approved) {
      console.log(contract.name + ": OK");
    } else {
      if (!options.executeApprovals) {
        console.log(contract.name + ": DRY-RUN would set approval-for-all");
        readinessBlockers.push(contract.name + " conditional-token approval not confirmed");
        continue;
      }
      console.log(contract.name + ": Approving...");
      try {
        const tx = await ct.setApprovalForAll(contract.address, true);
        console.log("  TX sent: " + tx.hash);
        await tx.wait();
        console.log("  Confirmed.");
      } catch (err) {
        console.log("  FAILED: " + err.message.slice(0, 100));
        readinessBlockers.push(contract.name + " conditional-token approval failed");
      }
    }
  }

  if (readinessBlockers.length) {
    console.log("\n--- Not Ready ---");
    for (const blocker of readinessBlockers) {
      console.log("- " + blocker);
    }
    process.exitCode = 1;
    return;
  }

  console.log("\n--- Ready to Trade ---");
  console.log("Balance: $" + usdcFormatted.toFixed(2) + " USDC.e");
  console.log("Gas: " + ethers.utils.formatEther(polBalance) + " POL");
  console.log("\nRun: node scripts/polymarket-run.js --mode=live --loop");
}

main().catch((err) => {
  console.error("Setup failed:", err.message);
  process.exitCode = 1;
});
