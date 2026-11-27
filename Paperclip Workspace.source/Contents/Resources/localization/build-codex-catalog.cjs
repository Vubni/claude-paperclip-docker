// Read only public metadata packaged in the Linux CLI installed in this image.
const { execFileSync } = require("node:child_process");
const { writeFileSync } = require("node:fs");

const { models } = JSON.parse(execFileSync("codex", ["debug", "models", "--bundled"], {
  encoding: "utf8", maxBuffer: 16 * 1024 * 1024,
}));
const catalog = models
  .filter(model => model.visibility === "list")
  .sort((a, b) => a.priority - b.priority)
  .map(model => ({
    id: model.slug,
    label: model.display_name.replace(/^(GPT-[\d.]+)-/, "$1 "),
    efforts: model.supported_reasoning_levels.map(level => level.effort),
    fast: model.additional_speed_tiers.includes("fast"),
  }));
if (!catalog.length || new Set(catalog.map(model => model.id)).size !== catalog.length) {
  throw new Error("Expected a non-empty Codex model catalog with unique IDs.");
}
writeFileSync(process.argv[2], "export const cliCatalog = " + JSON.stringify(catalog, null, 2) + " as const;\n");
