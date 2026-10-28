const test = require("node:test");
const assert = require("node:assert/strict");
const ts = require("typescript");
const api = {};
const compiled = ts.transpileModule(require("node:fs").readFileSync(require.resolve("../features/studio/script-review.ts"), "utf8"), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
new Function("exports", compiled)(api);
const scene = id => ({ scene_id: id, title: id, context: "", turns: [{ turn_id: id + "_turn", kind: "dialogue", source_ids: ["source"], include: true, text: "Hello", speaker_id: "A", delivery: "speech", emotion: "neutral", style: "", pacing: "", silence_sec: 0 }] });
test("review flags excluded sources and punctuation before approval without changing the draft", () => {
  const turn = scene("a").turns[0];
  const project = { cast: { A: {} }, sources: [{ source_id: "source", include: false }] };
  assert.match(api.turnReviewIssue(turn, project), /excluded source/);
  project.sources[0].include = true;
  for (const text of ["!?", "!", "…"]) {
    turn.text = text;
    assert.match(api.turnReviewIssue(turn, project), /Punctuation/);
    assert.equal(turn.text, text);
  }
  turn.text = "<gasp>";
  assert.equal(api.turnReviewIssue(turn, project), null);
  turn.text = "<slide>";
  assert.match(api.turnReviewIssue(turn, project), /Unsupported vocal tag/);
  turn.text = "Hello <laugh>";
  assert.equal(api.turnReviewIssue(turn, project), null);
  turn.text = "";
  assert.match(api.turnReviewIssue(turn, project), /spoken wording/);
  turn.silence_sec = 1;
  assert.equal(api.turnReviewIssue(turn, project), null);
  turn.text = "!?";
  turn.include = false;
  assert.equal(api.turnReviewIssue(turn, project), null);
});
test("batch save excludes unchanged scenes and approves only explicitly reviewed versions", () => {
  const saved = { scenes: [scene("a"), scene("b"), scene("c")] };
  const draft = structuredClone(saved);
  draft.scenes[0].turns[0].text = "Edited without approval";
  const reviews = api.sceneReviews(draft, saved, { b: api.sceneDraftKey(draft.scenes[1]) });
  assert.deepEqual(reviews.map(s => [s.scene_id, s.approve]), [["a", false], ["b", true]]);
  assert.equal(reviews[0].turns[0].kind, undefined);
});
test("editing after marking reviewed invalidates that pending approval", () => {
  const saved = { scenes: [scene("a")] }, draft = structuredClone(saved);
  const reviewed = { a: api.sceneDraftKey(draft.scenes[0]) };
  draft.scenes[0].turns[0].text = "Changed again";
  assert.equal(api.sceneReviews(draft, saved, reviewed)[0].approve, false);
});
test("unchanged unreviewed script produces no save transaction", () => {
  const saved = { scenes: [scene("a")] };
  assert.deepEqual(api.sceneReviews(structuredClone(saved), saved, {}), []);
});
