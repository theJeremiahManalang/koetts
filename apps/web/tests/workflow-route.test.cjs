const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const ts = require("typescript");

const compiled = ts.transpileModule(
  fs.readFileSync(require.resolve("../app/api/workflow/route.ts"), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } },
).outputText;

function route(root, enqueueOperation, requireAdmin = async () => null) {
  let sequence = 0;
  const api = {};
  const workflow = {
    dataRoot: root,
    id: () => String(++sequence).padStart(32, "0"),
    sameOrigin: () => {},
    validIdempotencyKey: key => key,
    validId: value => value,
    dispatchQueued: async () => {},
    enqueueOperation,
  };
  new Function("exports", "require", compiled)(api, name => {
    if (name.endsWith("/workflow")) return workflow;
    if (name.endsWith("/python")) return {};
    if (name.endsWith("/private-api")) return { hostedMode: () => false, PrivateApiError: class extends Error {} };
    if (name.endsWith("/require-admin")) return { requireAdmin, adminPrincipal: () => ({ kind: "firebase", uid: "admin-fixture", project_id: "test-project" }) };
    return require(name);
  });
  return api;
}

test("workflow denies unauthenticated and non-admin requests before processing", async () => {
  for (const status of [401, 403]) {
    const api = route("unused", () => assert.fail("Denied requests must not enqueue"), async () =>
      Response.json({ error: "Access denied" }, { status }));
    assert.equal((await api.GET(new Request("http://localhost/api/workflow"))).status, status);
    assert.equal((await api.POST(upload())).status, status);
  }
});

function upload() {
  const form = new FormData();
  form.set("mode", "chapter");
  form.set("chapter", new File(["uploaded bundle"], "chapter.zip"));
  return new Request("http://localhost/api/workflow", {
    method: "POST", headers: { "x-manga-workflow": "1", "idempotency-key": "lost-response" }, body: form,
  });
}

test("committed upload survives a lost enqueue response and remains available on key retry", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "workflow-upload-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  let stored;
  let submissions = 0;
  const api = route(root, async payload => {
    submissions++;
    if (!stored) {
      stored = payload;
      throw new Error("enqueue response lost after commit");
    }
    return { operation: { id: "operation", status: "queued" }, stored_upload_token: stored.upload_token };
  });
  assert.equal((await api.POST(upload())).status, 400);
  const original = path.join(root, "uploads", stored.upload_token, "chapter.zip");
  assert.equal(fs.readFileSync(original, "utf8"), "uploaded bundle");
  assert.equal((await api.POST(upload())).status, 202);
  assert.equal(submissions, 2);
  assert.equal(fs.readFileSync(original, "utf8"), "uploaded bundle");
  assert.deepEqual(fs.readdirSync(path.join(root, "uploads")), [stored.upload_token]);
});

test("definite idempotency rejection removes the unused upload", async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "workflow-rejected-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const api = route(root, async () => {
    throw Object.assign(new Error("different request"), { code: "idempotency_conflict" });
  });
  assert.equal((await api.POST(upload())).status, 409);
  assert.deepEqual(fs.readdirSync(path.join(root, "uploads")), []);
});

test("approval enqueue replaces caller actor with the verified administrator", async () => {
  let submitted;
  const api = route("unused", async payload => {
    submitted = payload;
    return { operation: { id: "saved", status: "queued" } };
  });
  const response = await api.POST(new Request("http://localhost/api/workflow", {
    method: "POST", headers: { "content-type": "application/json", "x-manga-workflow": "1", "idempotency-key": "review" },
    body: JSON.stringify({ action: "cast", project: "a".repeat(32), actor: { uid: "forged" } }),
  }));
  assert.equal(response.status, 202);
  assert.deepEqual(submitted.actor, { kind: "firebase", uid: "admin-fixture", project_id: "test-project" });
});
