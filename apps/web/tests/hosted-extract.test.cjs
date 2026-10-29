const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");

function compile() {
  return ts.transpileModule(fs.readFileSync(require.resolve("../app/api/extract/route.ts"), "utf8"), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  }).outputText;
}

function loadRoute({ key = "caller-intent", apiFailure } = {}) {
  const route = {};
  const calls = [];
  class PrivateApiError extends Error {
    constructor(status, code, message) { super(message); this.status = status; this.code = code; }
  }
  new Function("exports", "require", compile())(route, name => {
    if (name.endsWith("/require-admin")) return { requireAdmin: async () => null, trustedSessionRequest: () => true };
    if (name.endsWith("/workflow")) return {
      id: () => assert.fail("Projectless OCR must not allocate a random identity on retry"),
      validId: value => { if (!/^[a-f0-9]{32}$/.test(value)) throw new Error("Invalid identifier"); return value; },
      validIdempotencyKey: value => { if (!value || value.length > 200) throw new Error("A valid Idempotency-Key header is required."); return value; },
    };
    if (name.endsWith("/private-api")) return {
      hostedMode: () => true,
      PrivateApiError,
      privateJson: async (request, path, init) => {
        calls.push({ path, init });
        if (apiFailure) throw new PrivateApiError(apiFailure.status, apiFailure.code, apiFailure.message);
        return path === "/operations" ? { id: "a".repeat(32), project: "d".repeat(32), status: "queued" } : { name: "panel.png" };
      },
    };
    if (name.endsWith("/python")) return { python: async () => { throw new Error("local extractor must not run"); } };
    return require(name);
  });
  return { route, calls, key };
}

function request({ fields = {}, key = "caller-intent", imageSize = 3 } = {}) {
  const form = new FormData();
  form.set("model", fields.model || "magi");
  if (fields.project !== undefined) form.set("project", fields.project);
  form.append("image", new File([new Uint8Array(imageSize)], "panel.png", { type: fields.type || "image/png" }));
  return new Request("https://app.example/api/extract", {
    method: "POST",
    headers: { origin: "https://app.example", "idempotency-key": key },
    body: form,
  });
}

test("hosted extraction uploads one bounded panel and enqueues idempotent MAGI operation", async () => {
  const { route, calls } = loadRoute();
  const response = await route.POST(request({ fields: { project: "b".repeat(32) } }));

  assert.equal(response.status, 202);
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  assert.deepEqual(await response.json(), { id: "a".repeat(32), project: "d".repeat(32), status: "queued" });
  assert.equal(calls.length, 2);
  assert.equal(calls[0].path, `/uploads/${require("node:crypto").createHash("sha256").update("caller-intent").digest("hex").slice(0, 32)}/panel.png`);
  assert.equal(calls[0].init.method, "PUT");
  assert.equal(calls[0].init.headers["Content-Type"], "application/octet-stream");
  assert.deepEqual(calls[0].init.body, Buffer.from([0, 0, 0]));
  assert.equal(calls[1].path, "/operations");
  assert.equal(calls[1].init.method, "POST");
  assert.equal(calls[1].init.headers["Idempotency-Key"], "caller-intent");
  assert.deepEqual(JSON.parse(calls[1].init.body), {
    action: "ocr", project: "b".repeat(32),
    upload_token: calls[0].path.match(/uploads\/([a-f0-9]{32})/)[1],
  });
});

test("hosted extraction creates ephemeral project identity and rejects non-MAGI inputs", async () => {
  const { route, calls } = loadRoute();
  const noProject = await route.POST(request({ fields: { project: "untrusted" } }));
  assert.equal(noProject.status, 202);
  assert.equal(JSON.parse(calls[1].init.body).project, JSON.parse(calls[1].init.body).upload_token);

  const badModel = await route.POST(request({ fields: { model: "other" } }));
  assert.equal(badModel.status, 400);
  const badType = await route.POST(request({ fields: { type: "image/gif" } }));
  assert.equal(badType.status, 400);
});

test("projectless OCR keeps the same operation intent across lost-response retries", async () => {
  const { route, calls } = loadRoute();
  assert.equal((await route.POST(request())).status, 202);
  assert.equal((await route.POST(request())).status, 202);
  const operations = calls.filter(call => call.path === "/operations");
  assert.equal(operations.length, 2);
  assert.deepEqual(JSON.parse(operations[0].init.body), JSON.parse(operations[1].init.body));
  assert.equal(operations[0].init.headers["Idempotency-Key"], operations[1].init.headers["Idempotency-Key"]);
});

test("hosted extraction bounds actual multipart bytes and forwards only sanitized private errors", async () => {
  const { route } = loadRoute();
  const oversized = await route.POST(request({ imageSize: 11 * 1024 * 1024 }));
  assert.equal(oversized.status, 413);

  const failure = { status: 503, code: "private_api_unavailable", message: "Private service unavailable." };
  const failing = loadRoute({ apiFailure: failure });
  const response = await failing.route.POST(request());
  assert.equal(response.status, 503);
  assert.deepEqual(await response.json(), { error: "Private service unavailable.", code: "private_api_unavailable" });
});
