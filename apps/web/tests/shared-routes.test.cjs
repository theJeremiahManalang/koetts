const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
function compile(path) {
  return ts.transpileModule(fs.readFileSync(require.resolve(path), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
}
function load(path, { reader = true, admin = false } = {}) {
  const calls = [];
  const exports = {};
  const principal = { kind: 'firebase', uid: 'real-uid', project_id: 'real-project' };
  new Function('exports', 'require', compile(path))(exports, name => {
    if (name.includes('require-user')) return { requireUser: async () => reader ? principal : Response.json({ error: 'Sign in required.' }, { status: 401 }) };
    if (name.includes('require-admin')) return {
      requireAdmin: async () => admin ? null : Response.json({ error: 'Administrator access required.' }, { status: 403 }),
      adminPrincipal: () => principal,
      trustedSessionRequest: request => request.headers.get('origin') === 'http://localhost:3000',
    };
    if (name.includes('/server/requester-names')) return { withRequesterNames: async work => work };
    if (name.includes('/server/shared')) return {
      sharedCall: async payload => { calls.push(payload); return payload.action === 'requests' || payload.action === 'work' ? [] : { id: 'result' }; },
      validSharedId: value => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value),
      validRevision: value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value),
      principalKey: value => JSON.stringify([value.project_id, value.uid]),
      readSharedJson: async request => request.json(),
      localSharedOnly: () => null,
    };
    return {};
  });
  return { ...exports, calls };
}
const jsonRequest = (body, origin = 'http://localhost:3000') => new Request('http://localhost:3000/api/shared/requests', {
  method: 'POST', headers: { 'content-type': 'application/json', origin }, body: JSON.stringify(body),
});
test('reader mutations bind identity from verified credentials and enforce origin', async () => {
  const api = load('../app/api/shared/requests/route.ts');
  const response = await api.POST(jsonRequest({ title: 'Manga', chapter: '1', notes: 'note', reader: 'forged' }));
  assert.equal(response.status, 200);
  assert.deepEqual(api.calls[0], { action: 'submit', reader: JSON.stringify(['real-project', 'real-uid']), title: 'Manga', chapter: '1', notes: 'note' });
  assert.equal((await api.POST(jsonRequest({ title: 'Manga', chapter: '1', notes: '' }, 'https://evil.example'))).status, 403);
  assert.equal(api.calls.length, 1);
});
test('anonymous readers and non-admins cannot reach shared operations', async () => {
  const anonymous = load('../app/api/shared/requests/route.ts', { reader: false });
  assert.equal((await anonymous.GET(new Request('http://localhost:3000/api/shared/requests'))).status, 401);
  assert.equal(anonymous.calls.length, 0);
  const ordinary = load('../app/api/shared/admin/route.ts');
  assert.equal((await ordinary.GET(new Request('http://localhost:3000/api/shared/admin'))).status, 403);
  assert.equal(ordinary.calls.length, 0);
});
test('admin approval pins the verified actor and ignores caller actor fields', async () => {
  const api = load('../app/api/shared/admin/route.ts', { admin: true });
  const response = await api.POST(jsonRequest({ action: 'approve', work_id: 'a'.repeat(32), actor: 'forged' }));
  assert.equal(response.status, 200);
  assert.deepEqual(api.calls[0], { action: 'approve', work_id: 'a'.repeat(32), actor: JSON.stringify(['real-project', 'real-uid']) });
});
