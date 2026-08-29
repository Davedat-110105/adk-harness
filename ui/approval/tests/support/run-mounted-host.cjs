const { spawnSync } = require("node:child_process");
const path = require("node:path");

const repo = path.resolve(__dirname, "../../../..");
const script = path.join(__dirname, "probe-mounted-host.py");
const candidates = process.env.PYTHON ? [process.env.PYTHON] : [
    path.join(repo, ".venv", "Scripts", "python.exe"),
    path.join(repo, ".venv", "bin", "python"),
    "python",
    "python3",
];
for (const executable of candidates) {
    const result = spawnSync(executable, [script, ...process.argv.slice(2)], { cwd: repo, stdio: "inherit" });
    if (!result.error)
        process.exit(result.status ?? 1);
}
console.error("No usable Python runtime found; set PYTHON to the repository test runtime.");
process.exit(1);
