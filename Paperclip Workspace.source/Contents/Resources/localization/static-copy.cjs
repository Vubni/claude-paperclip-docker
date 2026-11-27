// Localize UI source at build time. Runtime values from tasks and accounts never enter this catalog.
const fs = require("node:fs");
const path = require("node:path");
const { parse } = require("/app/node_modules/.pnpm/@babel+parser@7.29.8/node_modules/@babel/parser");

const attributeNames = new Set(["aria-label", "placeholder", "title", "alt", "emptyMessage", "loadingLabel", "primaryLabel", "heading", "label"]);
const skip = new Set(["pre", "code", "kbd", "script", "style", "textarea", "svg", "Trans"]);
function eligible(text) {
  // Keep brands, shortcuts, paths, code examples and template fragments as supplied.
  return /^[A-Za-z][A-Za-z0-9 ,.!?;:’'()—–…-]*$/.test(text) && text.length <= 500 &&
    /[a-z]{2}/.test(text) && !/^(?:git|docker|npm|pnpm|curl|npx|sudo|export)\s|^(?:https?|data):/i.test(text);
}
function frontendFile(id) {
  return id.endsWith(".tsx") && !/\.(?:test|stories|spec)\.|\/(?:__tests__|artifact-directions|design-sandbox)\/|\/DesignGuide\.tsx$/.test(id);
}
function collect(source, id) {
  const ast = parse(source, { sourceType: "module", plugins: ["jsx", "typescript", "decorators-legacy"] });
  const found = [];
  function record(node, text, jsx, original = text) {
    if (eligible(text)) found.push({ start: node.start, end: node.end, text, jsx, original });
  }
  function expression(n) {
    if (!n) return;
    if (n.type === "StringLiteral") record(n, n.value, false);
    if (n.type === "ConditionalExpression") { expression(n.consequent); expression(n.alternate); }
    if (n.type === "LogicalExpression") expression(n.right);
  }
  function walk(node) {
    if (!node || typeof node !== "object") return;
    if (node.type === "JSXElement") {
      const tag = node.openingElement.name.name;
      const attrs = node.openingElement.attributes;
      if (skip.has(tag) || (tag === "option" && !attrs.some(a => a.name?.name === "value"))) return;
      for (const a of attrs) {
        if (attributeNames.has(a.name?.name) && a.value?.type === "StringLiteral") record(a.value, a.value.value, true);
        else if (attributeNames.has(a.name?.name) && a.value?.type === "JSXExpressionContainer") expression(a.value.expression);
        if (a.value?.type === "JSXExpressionContainer") walk(a.value.expression);
      }
      for (const child of node.children) {
        if (child.type === "JSXText" && node.children.length === 1) {
          const lines = child.value.split(/\r\n|\n|\r/);
          const original = lines.map((line, i) => {
            let value = line.replace(/\t/g, " ");
            if (i > 0) value = value.trimStart();
            if (i < lines.length - 1) value = value.trimEnd();
            return value;
          }).filter(Boolean).join(" ");
          record(child, original.trim(), true, original);
        }
        if (child.type === "JSXExpressionContainer") expression(child.expression);
        walk(child);
      }
      return;
    }
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) value.forEach(walk);
      else if (value && typeof value === "object") walk(value);
    }
  }
  walk(ast.program);
  return found;
}
function staticCopy() {
  const extra = JSON.parse(fs.readFileSync(path.join(__dirname, "ru-extra.json"), "utf8"));
  return { name: "paperclip-static-russian", enforce: "pre", transform(source, id) {
    if (!id.startsWith("/app/ui/src/") || !frontendFile(id)) return;
    let result = source;
    for (const span of collect(source, id).sort((a,b) => b.start - a.start)) {
      const ru = extra[span.text];
      if (!ru || ru === span.text) continue;
      const expr = `document.documentElement.lang==="ru"?${JSON.stringify(span.original.replace(span.text, () => ru))}:${JSON.stringify(span.original)}`;
      result = result.slice(0, span.start) + (span.jsx ? "{"+expr+"}" : "("+expr+")") + result.slice(span.end);
    }
    if (result !== source) return { code: result, map: null };
  }};
}
module.exports = staticCopy;
if (require.main === module) {
  const root = process.argv[2] || "/app/ui/src";
  const counts = new Map();
  let files = 0;
  for (const item of fs.readdirSync(root,{recursive:true,withFileTypes:true})) {
    const id = path.join(item.parentPath,item.name);
    if (!item.isFile() || !frontendFile(id)) continue;
    files++;
    for (const {text} of collect(fs.readFileSync(id,"utf8"),id)) counts.set(text,(counts.get(text)||0)+1);
  }
  console.log(JSON.stringify({files, labels:Object.fromEntries([...counts].sort())}));
}
