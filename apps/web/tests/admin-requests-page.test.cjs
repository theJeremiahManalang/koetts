const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const compiled = ts.transpileModule(fs.readFileSync(require.resolve('../app/admin/requests/page.tsx'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
}).outputText;
function page(status, cloud = false) {
  const api = {}, calls = [], component = () => {};
  new Function('exports', 'require', compiled)(api, name => {
    if (name === 'next/headers') return { headers: async () => new Headers({ cookie: 'koetts-session=test' }) };
    if (name === 'next/navigation') return { redirect: location => { throw new Error(`redirect:${location}`); } };
    if (name.endsWith('/require-admin')) return { requireAdmin: async request => { calls.push(request.headers.get('cookie')); return status ? new Response(null, { status }) : null; } };
    if (name.endsWith('/admin-requests-page')) return component;
    if (name.endsWith('/private-api')) return { isCloudExecution: () => cloud };
    return require(name);
  });
  return { render: api.default, component, calls };
}
test('admin request page verifies session and preserves frontend-only guard', async t => {
  const previous = process.env.MANGA_FRONTEND_ONLY;
  const previousMode = process.env.MANGA_EXECUTION_MODE;
  t.after(() => {
    if (previous === undefined) delete process.env.MANGA_FRONTEND_ONLY; else process.env.MANGA_FRONTEND_ONLY = previous;
    if (previousMode === undefined) delete process.env.MANGA_EXECUTION_MODE; else process.env.MANGA_EXECUTION_MODE = previousMode;
  });
  delete process.env.MANGA_FRONTEND_ONLY;
  await assert.rejects(page(401).render(), /redirect:\/login\?next=%2Fadmin%2Frequests/);
  await assert.rejects(page(403).render(), /redirect:\/browse/);
  const admin = page(); assert.equal((await admin.render()).type, admin.component); assert.deepEqual(admin.calls, ['koetts-session=test']);
  const cloudAdmin = page(null, true); assert.equal((await cloudAdmin.render()).props.productionControlsEnabled, true);
  process.env.MANGA_FRONTEND_ONLY = '1';
  const hosted = page(); await assert.rejects(hosted.render(), /redirect:\/browse/); assert.deepEqual(hosted.calls, []);
});
