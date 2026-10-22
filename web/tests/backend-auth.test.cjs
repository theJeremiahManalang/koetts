const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");
const compiled = ts.transpileModule(fs.readFileSync(require.resolve("../app/api/auth/backend/route.ts"), "utf8"), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

function route(denial) {
  const api = {};
  new Function("exports", "require", compiled)(api, name => {
    if (name === "google-auth-library") return { GoogleAuth: class {
      async getIdTokenClient(audience) {
        assert.equal(audience, "https://private-api.run.app");
        return { idTokenProvider: { fetchIdToken: async () => "service-fixture" } };
      }
    } };
    if (name.endsWith("/require-admin")) return {
      requireAdmin: async () => denial ? new Response(null, { status: denial }) : null,
      userCredential: () => ({ header: "X-KoeTTS-User-Token", value: "user-fixture" }),
    };
    return require(name);
  });
  return api;
}

test("backend diagnostic denies users before contacting the private service", async () => {
  for (const status of [401, 403]) {
    assert.equal((await route(status).GET(new Request("https://app/api/auth/backend"))).status, status);
  }
});

test("backend diagnostic separates service and user credentials and omits identity from response", async t => {
  const previous = process.env.S3_API_URL;
  const originalFetch = global.fetch;
  t.after(() => { global.fetch = originalFetch; if (previous === undefined) delete process.env.S3_API_URL; else process.env.S3_API_URL = previous; });
  process.env.S3_API_URL = "https://private-api.run.app";
  global.fetch = async (url, options) => {
    assert.equal(String(url), "https://private-api.run.app/identity");
    assert.equal(options.headers.Authorization, "Bearer service-fixture");
    assert.equal(options.headers["X-Serverless-Authorization"], "Bearer service-fixture");
    assert.equal(options.headers["X-KoeTTS-User-Token"], "user-fixture");
    return Response.json({ principal: { uid: "private-user" }, mode: "verification" });
  };
  const response = await route().GET(new Request("https://app/api/auth/backend"));
  assert.deepEqual(await response.json(), { verified: true, mode: "verification" });
});
