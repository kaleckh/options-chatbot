#!/usr/bin/env node

const { spawn } = require("node:child_process");

const child = spawn(
  "uv",
  ["run", "--directory", "python-backend", "uvicorn", "main:app", ...process.argv.slice(2)],
  {
    env: {
      ...process.env,
      OPTIONS_BACKEND_ALLOW_UNAUTHENTICATED: "1",
    },
    stdio: "inherit",
    windowsHide: true,
  }
);

child.on("error", (error) => {
  console.error(error.message);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 1);
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    child.kill(signal);
  });
}
