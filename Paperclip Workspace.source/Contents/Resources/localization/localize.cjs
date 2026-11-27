// Apply reviewed translations only to literal UI copy in the pinned distribution.
const fs = require("node:fs");
const path = require("node:path");
const {parse} = require("/app/node_modules/.pnpm/acorn@8.18.0/node_modules/acorn");
const dictionary = new Map(fs.readFileSync(path.join(__dirname, "ru.tsv"), "utf8").trim().split("\n").map(s => s.split("\t")));
const fields = new Set(["children", "title", "description", "label", "placeholder", "aria-label", "alt", "heading", "primaryLabel", "loadingLabel", "fallbackTitle", "badgeLabel", "instruction", "emptyMessage", "body"]);
const used = new Set();
function translate(node, edits) {
  if (node.type === "Literal" && typeof node.value === "string") {
    const key = node.value.trim();
    if (dictionary.has(key)) {
      used.add(key);
      const russian = JSON.stringify(node.value.replace(key, dictionary.get(key)));
      edits.push([node.start, node.end, `(document.documentElement.lang==="ru"?${russian}:${JSON.stringify(node.value)})`]);
    }
  } else if (node.type === "ConditionalExpression") {
    translate(node.consequent, edits);
    translate(node.alternate, edits);
  } else if (node.type === "ArrayExpression") {
    for (const item of node.elements) if (item) translate(item, edits);
  } else if (node.type === "LogicalExpression") translate(node.right, edits);
}
function scan(node, edits) {
  if (!node || typeof node !== "object") return;
  if (node.type === "Property" && !node.computed && fields.has(node.key.name ?? node.key.value)) translate(node.value, edits);
  for (const value of Object.values(node)) {
    if (Array.isArray(value)) value.forEach(item => scan(item, edits));
    else if (value && typeof value === "object") scan(value, edits);
  }
}
module.exports = function workspaceLabels() {
  let count = 0;
  return {
    name: "workspace-ui-language",
    enforce: "post",
    transformIndexHtml(html) {
      return html.replace('<html lang="en"', '<html lang="ru"').replace("<head>", `<head>
      <script>
      if (navigator.userAgent.endsWith("PaperclipWorkspace/1")) {
        const policy = document.createElement("meta");
        policy.httpEquiv = "Content-Security-Policy";
        policy.content = "default-src 'self' blob: data:; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval' blob:; style-src 'self' 'unsafe-inline'; connect-src 'self' ws://localhost:43107; frame-src 'self' blob:; object-src 'none'; form-action 'self'; base-uri 'self'";
        document.head.append(policy);
      }
      try {
        if (localStorage.getItem("paperclip.workspace.language") === "en")
          document.documentElement.lang = "en";
      } catch {}</script>`);
    },
    renderChunk: {
      order: "post",
      handler(code) {
        const edits = [];
        scan(parse(code, { ecmaVersion: "latest", sourceType: "module" }), edits);
        if (!edits.length) return null;
        // Edits are independent literal ranges. Assemble once for large UI chunks.
        const parts = [];
        let cursor = 0;
        for (const [start, end, replacement] of edits.sort((a, b) => a[0] - b[0])) {
          parts.push(code.slice(cursor, start), replacement);
          cursor = end;
        }
        parts.push(code.slice(cursor));
        count += edits.length;
        return { code: parts.join(""), map: null };
      },
    },
    generateBundle() {
      for (const key of ["Finish setting up this Paperclip", "Sign in to Paperclip", "Dashboard", "New Task", "What is the name of your organization?", "e.g. Northwind Labs", "Continue"]) {
        if (!used.has(key)) throw Error("Missing UI string: " + key);
      }
      console.log(count + " labels localized; " + used.size + " distinct translations");
    },
  };
};
