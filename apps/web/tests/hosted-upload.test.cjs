const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");

const source = fs.readFileSync(require.resolve("../features/studio/hosted-upload.ts"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const hostedUpload = {};
new Function("exports", compiled)(hostedUpload);

function form(fields) {
  const value = new FormData();
  for (const [key, item] of Object.entries(fields)) {
    if (Array.isArray(item)) item.forEach(file => value.append(key, file));
    else value.set(key, item);
  }
  return value;
}

test("hosted image upload sends bounded canonical files sequentially and returns compact payload", async () => {
  const files = Array.from({ length: 40 }, (_, i) => new File([`page-${i}`], `page-${i}.webp`, { type: "image/webp" }));
  const uploadToken = "a".repeat(32);
  const submitted = [];
  let inFlight = 0;
  let maxInFlight = 0;
  const payload = await hostedUpload.prepareHostedUpload(form({ action: "create", mode: "images", direction: "rtl", images: files }), async (name, file, token) => {
    inFlight++;
    maxInFlight = Math.max(maxInFlight, inFlight);
    submitted.push([name, file.name, token]);
    await Promise.resolve();
    inFlight--;
  }, uploadToken, "b".repeat(32));

  assert.equal(submitted.length, 40);
  assert.equal(maxInFlight, 1);
  assert.deepEqual(submitted[0], ["0.png", "page-0.webp", uploadToken]);
  assert.deepEqual(submitted.at(-1), ["39.png", "page-39.webp", uploadToken]);
  assert.deepEqual(payload, {
    action: "create", upload_token: uploadToken, mode: "images", direction: "rtl",
    images: Array.from({ length: 40 }, (_, i) => `${i}.png`), work_id: "b".repeat(32),
  });
});

test("hosted ZIP and cast import uploads use their canonical names and retain project revision", async () => {
  const token = "c".repeat(32);
  const zip = new File(["zip"], "source.zip", { type: "application/zip" });
  for (const [input, expectedName, expectedAction] of [
    [form({ action: "create", mode: "restore", chapter: zip }), "chapter.zip", "create"],
    [form({ action: "cast-import", project: "d".repeat(32), revision: "revision-2", cast: zip }), "cast.zip", "cast-import"],
  ]) {
    const sent = [];
    const payload = await hostedUpload.prepareHostedUpload(input, async name => sent.push(name), token);
    assert.deepEqual(sent, [expectedName]);
    assert.equal(payload.action, expectedAction);
    assert.equal(payload.upload_token, token);
    if (expectedAction === "cast-import") assert.deepEqual(payload, {
      action: expectedAction, upload_token: token, project: "d".repeat(32), revision: "revision-2",
    });
  }
});

test("oversized hosted file is rejected before any upload request", async () => {
  const tooLarge = new File([new Uint8Array(10 * 1024 * 1024 + 1)], "big.zip");
  let sends = 0;
  await assert.rejects(
    hostedUpload.prepareHostedUpload(form({ action: "create", mode: "chapter", chapter: tooLarge }), async () => { sends++; }, "e".repeat(32)),
    /no larger than 10 MiB/,
  );
  assert.equal(sends, 0);
});

test("invalid work query values are ignored", () => {
  assert.equal(hostedUpload.hostedWorkId(`?work=${"f".repeat(32)}`), "f".repeat(32));
  assert.equal(hostedUpload.hostedWorkId("?work=not-an-id"), undefined);
});

test("the same idempotency intent maps to the same UUID32 upload token", () => {
  const key = "12345678-1234-4234-9234-123456789abc";
  assert.equal(hostedUpload.uploadTokenForIntent(key), "12345678123442349234123456789abc");
  assert.equal(hostedUpload.uploadTokenForIntent(key), hostedUpload.uploadTokenForIntent(key));
});
