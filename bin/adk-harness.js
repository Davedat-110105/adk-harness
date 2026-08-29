#!/usr/bin/env node

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const project = path.resolve(__dirname, "..");

// Node 18 has no recursive withFileTypes listing.
function listFiles(root, prefix = "") {
  const found = [];
  for (const entry of fs.readdirSync(path.join(root, prefix), { withFileTypes: true })) {
    const relative = path.join(prefix, entry.name);
    if (entry.isDirectory()) {
      found.push(...listFiles(root, relative));
    } else {
      found.push(relative);
    }
  }
  return found;
}

// The plugin is a file copy, so it runs here rather than paying for a Python
// environment the caller may not need yet.
function installPlugin(argv) {
  const flag = argv.indexOf("--plugin-dir");
  if (flag !== -1 && !argv[flag + 1]) {
    console.error("--plugin-dir needs a path");
    return 2;
  }
  const destination =
    flag === -1
      ? path.join(os.homedir(), ".gemini", "config", "plugins", "adk-harness")
      : path.resolve(argv[flag + 1]);
  const source = path.join(project, "plugins", "antigravity");
  if (!fs.existsSync(source)) {
    console.error("the packaged Antigravity plugin is missing");
    return 2;
  }
  try {
    fs.rmSync(destination, { recursive: true, force: true });
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.cpSync(source, destination, { recursive: true });
  } catch (error) {
    console.error(`the plugin could not be installed: ${error.message}`);
    return 2;
  }
  console.log(`installed: ${destination}`);
  for (const entry of listFiles(destination).sort()) {
    console.log(`  ${entry}`);
  }
  return 0;
}

if (process.argv[2] === "install-plugin") {
  process.exit(installPlugin(process.argv.slice(3)));
}
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
