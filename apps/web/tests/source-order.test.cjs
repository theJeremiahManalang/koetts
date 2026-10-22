const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");
const api = {};
const compiled = ts.transpileModule(fs.readFileSync(require.resolve("../features/studio/source-order.ts"), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
new Function("exports", compiled)(api);
const source = (id, scene, group, order) => ({ source_id: id, scene_id: scene, turn_group: group, order, speaker_id: "A", delivery: "speech", emotion: "neutral", style: "", pacing: "", include: true });

test("filtered dialogue moves preserve all other source positions", () => {
  const project = { sources: [source("a", "s1", "a", 0), source("other", "s1", "other", 1), source("b", "s1", "b", 2)] };
  api.replaceSourceSlots(project, ["b", "a"]);
  assert.deepEqual(project.sources.map(s => s.source_id), ["b", "other", "a"]);
  assert.deepEqual(project.sources.map(s => s.order), [0, 1, 2]);
});
test("split repair preserves reading order and separates repeated scene runs", () => {
  const project = { sources: [source("a", "scene", "g", 0), source("b", "scene2", "g", 1), source("c", "scene", "g", 2)] };
  assert.equal(api.orderIssues(project).length, 2);
  api.splitOrderConflicts(project);
  assert.deepEqual(api.orderIssues(project), []);
  assert.deepEqual(project.sources.map(s => s.source_id), ["a", "b", "c"]);
  assert.equal(project.sources[2].scene_id, "scene_part_2");
});
test("conflicting speakers split groups without rewriting dialogue", () => {
  const project = { sources: [source("a", "s", "g", 0), { ...source("b", "s", "g", 1), speaker_id: "B", text: "Keep me" }] };
  assert.equal(api.orderIssues(project).length, 1);
  api.splitOrderConflicts(project);
  assert.deepEqual(api.orderIssues(project), []);
  assert.equal(project.sources[1].text, "Keep me");
});
test("already valid grouping is unchanged by repair", () => {
  const project = { sources: [source("a", "s", "g", 0), source("b", "s", "g", 1)] };
  const original = JSON.stringify(project);
  api.splitOrderConflicts(project);
  assert.equal(JSON.stringify(project), original);
});
