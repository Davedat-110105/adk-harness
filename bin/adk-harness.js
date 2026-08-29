#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const project = path.resolve(__dirname, "..");
const uv = process.env.ADK_HARNESS_UV || (process.platform === "win32" ? "uv.exe" : "uv");
const result = spawnSync(
  uv,
  [
    "tool",
    "run",
    "--python",
    "3.12",
    "--from",
    project,
    "adk-harness",
    ...process.argv.slice(2),
  ],
  { cwd: process.cwd(), stdio: "inherit", shell: false },
);

if (result.error?.code === "ENOENT") {
  console.error(
    "adk-harness needs uv. Install it from https://docs.astral.sh/uv/getting-started/installation/ " +
      "then run this command again.",
  );
  process.exit(1);
}

if (result.error) {
  console.error(`adk-harness could not start uv: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
