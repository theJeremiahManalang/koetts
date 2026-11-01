const test = require("node:test");
const assert = require("node:assert/strict");
const ts = require("typescript");
const fs = require("node:fs");
const source = fs.readFileSync(require.resolve("../features/studio/operation-events.ts"), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
const operationEvents = {};
new Function("exports", "require", compiled)(operationEvents, () => ({}));

test("operation SSE parser keeps partial frames and accepts CRLF and multiline data", () => {
  const frame = "event: operation\r\ndata: {\"id\":\"a\",\r\ndata: \"project\":\"b\",\r\ndata: \"status\":\"running\",\r\ndata: \"message\":\"busy\"}\r\n\r\n";
  const first = operationEvents.takeOperationEvents(frame.slice(0, 39));
  assert.deepEqual(first.events, []);
  const second = operationEvents.takeOperationEvents(first.remainder + frame.slice(39));
  assert.deepEqual(second.events.map(value => value.status), ["running"]);
  assert.equal(second.remainder, "");
});

test("operation SSE parser ignores keepalives and unknown event types", () => {
  const parsed = operationEvents.takeOperationEvents(": keepalive\n\n" + "event: auth-expired\ndata: {}\n\n");
  assert.deepEqual(parsed.events, []);
  assert.deepEqual(parsed.controls, ["auth-expired"]);
  assert.equal(parsed.remainder, "");
});
