const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");
const api = {};
const source = fs.readFileSync(require.resolve("../lib/idempotency.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
new Function("exports", compiled)(api);

function memoryStorage() {
  const values = new Map();
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
}

test("same intent reuses its key while a different pending intent keeps its recovery key", () => {
  const storage = memoryStorage();
  const first = api.idempotencyKeyForIntent("first payload", storage);
  assert.equal(api.idempotencyKeyForIntent("first payload", storage), first);
  const second = api.idempotencyKeyForIntent("second payload", storage);
  assert.notEqual(second, first);
  assert.deepEqual(api.pendingOperationIntents(storage).map(intent => intent.key), [first, second]);

  api.removePendingOperationKey(first, storage);
  assert.deepEqual(api.pendingOperationIntents(storage).map(intent => intent.key), [second]);
});

test("a typed idempotency conflict rotates the request key and preserves the old lookup key", () => {
  const storage = memoryStorage();
  const key = api.idempotencyKeyForIntent("payload", storage);
  api.clearConflictedOperationKey("revision_conflict", key, storage);
  assert.equal(api.idempotencyKeyForIntent("payload", storage), key);

  api.clearConflictedOperationKey("idempotency_conflict", key, storage);
  const retryKey = api.idempotencyKeyForIntent("payload", storage);
  assert.notEqual(retryKey, key);
  assert.deepEqual(
    api.pendingOperationIntents(storage).map(intent => [intent.key, intent.conflicted]),
    [[key, true], [retryKey, undefined]],
  );
});
