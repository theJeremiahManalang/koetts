const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
function load(path, { signedIn = true, admin = false, validToken = true } = {}) {
  const calls = [];
  const api = {};
  const code = ts.transpileModule(fs.readFileSync(require.resolve(path), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  new Function('exports', 'require', code)(api, name => {
    if (name.includes('require-user')) return { requireUser: async () => signedIn ? { uid: 'reader', project_id: 'project' } : Response.json({}, { status: 401 }) };
    if (name.includes('require-admin')) return { requireAdmin: async () => admin ? null : Response.json({}, { status: 403 }) };
    if (name.includes('/server/shared')) return { localSharedOnly: () => null, validSharedId: value => /^[a-f0-9]{32}$/.test(value), sharedCall: async input => { calls.push(input); return { publication_id: 'b'.repeat(32), path: '/private/artifact' }; } };
    if (name.includes('audio-key')) return { audioKey: async () => Buffer.alloc(32) };
    if (name.includes('audio-token')) return { issueAudioToken: () => 'signed', verifyAudioToken: () => { if (!validToken) throw new Error(); return { work: 'a'.repeat(32), publication: 'b'.repeat(32) }; } };
    if (name.includes('audio-file')) return { serveAudioFile: async (_root, _path, request) => new Response(request.headers.get('range') || 'full', { status: 206 }) };
    if (name.includes('lib/python')) return { dataRoot: '/private' };
    return {};
  });
  return { ...api, calls };
}
test('playback URL requires signed-in reader and binds current publication', async () => {
  const unauthenticated = load('../app/api/shared/playback/route.ts', { signedIn: false });
  assert.equal((await unauthenticated.GET(new Request('http://localhost/api/shared/playback?work=' + 'a'.repeat(32)))).status, 401);
  assert.equal(unauthenticated.calls.length, 0);
  const api = load('../app/api/shared/playback/route.ts');
  const response = await api.GET(new Request('http://localhost/api/shared/playback?work=' + 'a'.repeat(32)));
  assert.equal(response.status, 200); assert.match((await response.json()).url, /token=signed/);
  assert.deepEqual(api.calls, [{ action: 'published', work_id: 'a'.repeat(32) }]);
});
test('audio requires session and valid token before resolving the pinned publication', async () => {
  const expired = load('../app/api/shared/audio/route.ts', { validToken: false });
  assert.equal((await expired.GET(new Request('http://localhost/api/shared/audio?token=bad'))).status, 403);
  assert.equal(expired.calls.length, 0);
  const api = load('../app/api/shared/audio/route.ts');
  const response = await api.GET(new Request('http://localhost/api/shared/audio?token=signed', { headers: { range: 'bytes=1-3' } }));
  assert.equal(response.status, 206); assert.equal(await response.text(), 'bytes=1-3');
  assert.deepEqual(api.calls, [{ action: 'published', work_id: 'a'.repeat(32), publication_id: 'b'.repeat(32) }]);
});
test('candidate audio is admin-only', async () => {
  const api = load('../app/api/shared/candidate/route.ts');
  assert.equal((await api.GET(new Request('http://localhost/api/shared/candidate?id=' + 'c'.repeat(32)))).status, 403);
  assert.equal(api.calls.length, 0);
});
