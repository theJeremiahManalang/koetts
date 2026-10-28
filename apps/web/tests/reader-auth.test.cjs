const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const compiled = ts.transpileModule(fs.readFileSync(require.resolve('../features/identity/require-user.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
function load({ fail = false } = {}) {
  const calls = [];
  const auth = Object.fromEntries(['verifyIdToken', 'verifySessionCookie'].map(method => [method, async (...args) => {
    calls.push([method, ...args]);
    if (fail) throw new Error('invalid');
    return { uid: 'verified-reader', aud: 'verified-project' };
  }]));
  const api = {};
  new Function('exports', 'require', compiled)(api, name => name === './firebase-admin' ? { getAdminAuth: () => auth } : name === './require-admin' ? { sessionCookie: 'koetts-session' } : {});
  return { ...api, calls };
}
const request = headers => new Request('http://localhost:3000/api/shared', { headers });
test('reader identity requires verified credentials and ignores forged identity headers', async () => {
  const api = load();
  assert.equal((await api.requireUser(request({ 'x-user-id': 'forged' }))).status, 401);
  assert.deepEqual(await api.requireUser(request({ authorization: 'Bearer token', 'x-user-id': 'forged' })), {
    kind: 'firebase', uid: 'verified-reader', project_id: 'verified-project',
  });
  assert.deepEqual(api.calls, [['verifyIdToken', 'token', true]]);
});
test('reader session verifies revocation and rejects invalid authorization', async () => {
  const api = load();
  assert.equal((await api.requireUser(request({ cookie: 'koetts-session=value' }))).uid, 'verified-reader');
  assert.deepEqual(api.calls, [['verifySessionCookie', 'value', true]]);
  assert.equal((await api.requireUser(request({ authorization: 'Basic bad', cookie: 'koetts-session=value' }))).status, 401);
  assert.equal((await load({ fail: true }).requireUser(request({ authorization: 'Bearer revoked' }))).status, 401);
});
