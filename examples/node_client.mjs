/**
 * Analyse a text with the SlopTotal JSON API, using only Node 18+'s built-in fetch.
 *
 * Usage: node examples/node_client.mjs "some text..." [--base URL]
 */

const DEFAULT_BASE = "http://localhost:8000";

const args = process.argv.slice(2);
let base = DEFAULT_BASE;
const baseFlag = args.indexOf("--base");
if (baseFlag !== -1) {
  base = args[baseFlag + 1];
  args.splice(baseFlag, 2);
}
base = base.replace(/\/+$/, "");

const [text] = args;
if (!text) {
  console.error('Usage: node examples/node_client.mjs "some text..." [--base URL]');
  process.exit(1);
}

const response = await fetch(`${base}/api/analyze`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ text }),
});
if (!response.ok) {
  console.error(`SlopTotal returned ${response.status}: ${await response.text()}`);
  process.exit(1);
}
const analysis = await response.json();

console.log(
  `Overall score: ${analysis.overall_score.toFixed(1)}/100 (${analysis.overall_verdict})`,
);
console.log("Top five engines:");
const topEngines = [...analysis.engine_results]
  .sort((a, b) => b.score - a.score)
  .slice(0, 5);
for (const engine of topEngines) {
  console.log(`  ${engine.engine_name}: ${(engine.score * 100).toFixed(1)}%`);
}
