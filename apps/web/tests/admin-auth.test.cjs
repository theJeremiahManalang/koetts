const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const compiled = ts.transpileModule(fs.readFileSync(require.resolve('../features/identity/require-admin.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
function load({ claims = {}, fail = false } = {}) {
  const calls = [];
  const auth = Object.fromEntries(['verifyIdToken', 'verifySessionCookie'].map(method => [method, async (...args) => { calls.push([method, ...args]); if (fail) throw new Error('invalid'); return { uid: 'verified-admin', aud: 'verified-project', ...claims }; }]));
  const api = {};
  new Function('exports', 'require', compiled)(api, name => name === './firebase-admin' ? { getAdminAuth: () => auth } : {});
  return { ...api, calls };
}
const request = headers => new Request('http://localhost:3000/api/workflow', { headers });
test('anonymous requests are rejected without accessing Firebase', async () => {
  const api = load(); assert.equal((await api.requireAdmin(request({}))).status, 401); assert.equal(api.calls.length, 0);
});
test('regular users and legacy roles are forbidden', async () => {
  for (const claims of [{}, { admin: 'true' }, { role: 'admin' }, { role: 'Admin' }]) {
    assert.equal((await load({ claims }).requireAdmin(request({ authorization: 'Bearer token' }))).status, 403);
  }
});
test('valid admin bearer tokens pass with revocation checks enabled', async () => {
  const api = load({ claims: { admin: true } }); assert.equal(await api.requireAdmin(request({ authorization: 'Bearer token' })), null);
  assert.deepEqual(api.calls, [['verifyIdToken', 'token', true]]);
});
test('protected media accepts verified admin sessions', async () => {
  const api = load({ claims: { admin: true } }); assert.equal(await api.requireAdmin(request({ cookie: 'other=x; koetts-session=session-value' })), null);
  assert.deepEqual(api.calls, [['verifySessionCookie', 'session-value', true]]);
});
test('invalid, expired or revoked credentials fail closed', async () => {
  for (const headers of [{ authorization: 'Bearer token' }, { cookie: 'koetts-session=expired' }]) assert.equal((await load({ fail: true }).requireAdmin(request(headers))).status, 401);
});
test('invalid authorization cannot fall back to a session', async () => {
  const api = load({ claims: { admin: true } }); assert.equal((await api.requireAdmin(request({ authorization: 'Basic invalid', cookie: 'koetts-session=valid' }))).status, 401); assert.equal(api.calls.length, 0);
});
test('session mutations require an explicit same origin', () => {
  const api = load();
  assert.equal(api.trustedSessionRequest(request({ origin: 'http://localhost:3000' })), true);
  assert.equal(api.trustedSessionRequest(request({ host: '127.0.0.1:3000', origin: 'http://127.0.0.1:3000' })), true);
  assert.equal(api.trustedSessionRequest(request({ host: '127.0.0.1:3000', origin: 'http://localhost:3000' })), false);
  for (const headers of [{}, { origin: 'https://attacker.example' }, { origin: 'http://localhost:3000', 'sec-fetch-site': 'cross-site' }]) assert.equal(api.trustedSessionRequest(request(headers)), false);
});
test('configured public origin survives hosting proxy without trusting forwarded hosts', t => {
  const previous = process.env.MANGA_APP_ORIGIN;
  t.after(() => { if (previous === undefined) delete process.env.MANGA_APP_ORIGIN; else process.env.MANGA_APP_ORIGIN = previous; });
  process.env.MANGA_APP_ORIGIN = 'https://koetts.example';
  const api = load();
  const proxied = headers => new Request('http://0.0.0.0:8080/api/auth/session', { headers });
  assert.equal(api.trustedSessionRequest(proxied({ origin: 'https://koetts.example' })), true);
  for (const headers of [{}, { origin: 'https://attacker.example', 'x-forwarded-host': 'attacker.example' },
    { origin: 'https://koetts.example', 'sec-fetch-site': 'cross-site' }, { origin: 'http://0.0.0.0:8080' }]) {
    assert.equal(api.trustedSessionRequest(proxied(headers)), false);
  }
  process.env.MANGA_APP_ORIGIN = 'not-an-origin';
  assert.equal(api.trustedSessionRequest(proxied({ origin: 'https://koetts.example' })), false);
});
test('verified principal ignores forged actor headers and cannot be reused for another request', async () => {
  const api = load({ claims: { admin: true } });
  const incoming = request({ authorization: 'Bearer token', 'x-user-id': 'forged', 'x-admin': 'true' });
  assert.throws(() => api.adminPrincipal(incoming));
  assert.equal(await api.requireAdmin(incoming), null);
  assert.deepEqual(api.adminPrincipal(incoming), { kind: 'firebase', uid: 'verified-admin', project_id: 'verified-project' });
  assert.throws(() => api.adminPrincipal(request({ authorization: 'Bearer token' })));
});
test('all processing routes enforce authorization before their existing work', () => {
  for (const file of ['workflow', 'extract', 'asset']) {
    const source = fs.readFileSync(require.resolve(`../app/api/${file}/route.ts`), 'utf8');
    const handlers = [...source.matchAll(/export async function (GET|POST)\(request: Request\) \{\s*const denied = await requireAdmin\(request\); if \(denied\) return denied;/g)];
    assert.equal(handlers.length, file === 'workflow' ? 2 : 1);
  }
});
