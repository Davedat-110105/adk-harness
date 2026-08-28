#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const project = path.resolve(__dirname, "..");
const result = spawnSync(
  process.platform === "win32" ? "uv.exe" : "uv",
  [
    "tool",
    "run",
    "--python",
    "3.12",
    "--from",
    `${project}[google-workspace]`,
    "adk-harness",
    ...process.argv.slice(2),
  ],
  { stdio: "inherit" },
);

if (result.error?.code === "ENOENT") {
  console.error(
    "adk-harness needs uv. Install it from https://docs.astral.sh/uv/getting-started/installation/ " +
      "then run this command again.",
  );
  process.exit(1);
}

process.exit(result.status ?? 1);
