const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const ts = require("typescript");

const compiled = ts.transpileModule(
  fs.readFileSync(require.resolve("../app/page.tsx"), "utf8"),
  { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } },
).outputText;

function page(status) {
  const api = {};
  const workspace = () => {};
  const calls = [];
  new Function("exports", "require", compiled)(api, name => {
    if (name === "next/headers") return { headers: async () => new Headers({ cookie: "koetts-session=test" }) };
    if (name === "next/navigation") return { redirect: location => { throw new Error(`redirect:${location}`); } };
    if (name.endsWith("/require-admin")) return { requireAdmin: async request => {
      calls.push(request.headers.get("cookie"));
      return status ? new Response(null, { status }) : null;
    } };
    if (name === "../features/studio/studio-workspace") return workspace;
    if (name.endsWith("/private-api")) return { hostedMode: () => process.env.MANGA_EXECUTION_MODE === "cloud" };
    return require(name);
  });
  return { render: api.default, workspace, calls };
}

test("studio page gates sessions and preserves frontend-only redirect", async t => {
  const previous = process.env.MANGA_FRONTEND_ONLY;
  t.after(() => {
    if (previous === undefined) delete process.env.MANGA_FRONTEND_ONLY;
    else process.env.MANGA_FRONTEND_ONLY = previous;
  });
  delete process.env.MANGA_FRONTEND_ONLY;
  await assert.rejects(page(401).render(), /redirect:\/login\?next=%2F/);
  await assert.rejects(page(403).render(), /redirect:\/browse/);
  const admin = page();
  assert.equal((await admin.render()).type, admin.workspace);
  assert.deepEqual(admin.calls, ["koetts-session=test"]);
  process.env.MANGA_FRONTEND_ONLY = "1";
  const hosted = page();
  await assert.rejects(hosted.render(), /redirect:\/browse/);
  assert.deepEqual(hosted.calls, []);
});
