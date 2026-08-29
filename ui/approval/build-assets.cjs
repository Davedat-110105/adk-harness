const fs = require("node:fs");
const path = require("node:path");

const packageRoot = path.resolve(__dirname, "../../src/adk_harness/ui/approval");
fs.mkdirSync(path.join(packageRoot, "dist"), { recursive: true });
for (const relativePath of ["index.html", "dist/main.js"]) {
  fs.copyFileSync(path.join(__dirname, relativePath), path.join(packageRoot, relativePath));
}
