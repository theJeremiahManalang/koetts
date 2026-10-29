const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');

function load(file, { denied = null } = {}) {
  const calls = [];
  const api = {};
  class PrivateApiError extends Error {}
  const principal = { kind: 'firebase', uid: 'admin', project_id: 'demo-hosted' };
  const compiled = ts.transpileModule(fs.readFileSync(require.resolve(file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function('exports', 'require', compiled)(api, name => {
    if (name.endsWith('/require-admin')) return {
      requireAdmin: async () => denied ? new Response(null, { status: denied }) : null,
      adminPrincipal: () => principal,
      trustedSessionRequest: request => request.headers.get('origin') === 'https://studio.example',
    };
    if (name.endsWith('/private-api')) return {
      hostedMode: () => true,
      PrivateApiError,
      privateJson: async (request, endpoint, init) => { calls.push({ request, endpoint, init }); return { id: 'operation', status: 'queued' }; },
      proxyPrivate: async (request, endpoint) => { calls.push({ request, endpoint }); return new Response('image', { status: 206, headers: { 'Content-Type': 'image/png' } }); },
    };
    if (name.endsWith('/workflow')) return {
      id: () => 'a'.repeat(32),
      validId: value => { assert.match(value, /^[a-f0-9]{32}$/); return value; },
      validIdempotencyKey: value => { assert.ok(value); return value; },
      get dataRoot() { assert.fail('Hosted routes must not use local data roots'); },
      dispatchQueued: () => assert.fail('Hosted routes must not start local workers'),
    };
    if (name.endsWith('/python')) return { python: () => assert.fail('Hosted routes must not run Python') };
    if (name === 'node:fs/promises') return new Proxy({}, { get: () => () => assert.fail('Hosted routes must not touch local files') });
    return require(name);
  });
  return { ...api, calls, principal };
}

function mutation(body, extra = {}) {
  return new Request('https://studio.example/api/workflow', {
    method: 'POST', headers: { origin: 'https://studio.example', 'content-type': 'application/json',
      'x-manga-workflow': '1', 'idempotency-key': 'intent', ...extra }, body: JSON.stringify(body),
  });
}

test('hosted workflow pins the verified actor and enqueues without filesystem or local dispatch', async () => {
  const api = load('../app/api/workflow/route.ts');
  const request = mutation({ action: 'rename', project: 'b'.repeat(32), revision: 'c'.repeat(64), actor: { uid: 'forged' }, command: { title: 'New title' } });
  assert.equal((await api.POST(request)).status, 202);
  assert.equal(api.calls.length, 1);
  assert.equal(api.calls[0].request, request);
  assert.equal(api.calls[0].endpoint, '/operations');
  assert.equal(api.calls[0].init.headers['Idempotency-Key'], 'intent');
  assert.deepEqual(JSON.parse(api.calls[0].init.body).actor, api.principal);
  assert.equal((await api.POST(mutation({ action: 'rename' }, { origin: 'https://attacker.example' }))).status, 403);
  assert.equal(api.calls.length, 1);
});

test('hosted polling, key recovery, and snapshots use private APIs', async () => {
  const api = load('../app/api/workflow/route.ts');
  for (const [query, endpoint] of [
    ['job=' + 'a'.repeat(32), '/operations/' + 'a'.repeat(32)],
    ['key=intent%2Fone', '/operations/by-key?key=intent%2Fone'],
    ['project=' + 'b'.repeat(32), '/projects/' + 'b'.repeat(32)],
    ['', '/projects'],
  ]) {
    assert.equal((await api.GET(new Request('https://studio.example/api/workflow?' + query))).status, 200);
    assert.equal(api.calls.at(-1).endpoint, endpoint);
  }
});

test('hosted upload is one bounded binary object and never writes local staging', async () => {
  const api = load('../app/api/workflow/upload/route.ts');
  const url = 'https://studio.example/api/workflow/upload?token=' + 'a'.repeat(32) + '&name=0.png';
  const request = new Request(url, { method: 'PUT', headers: { origin: 'https://studio.example', 'x-manga-workflow': '1', 'content-type': 'application/octet-stream' }, body: 'image bytes' });
  assert.equal((await api.PUT(request)).status, 200);
  assert.equal(api.calls[0].endpoint, '/uploads/' + 'a'.repeat(32) + '/0.png');
  assert.equal(Buffer.from(api.calls[0].init.body).toString(), 'image bytes');
  const tooLarge = new Request(url, { method: 'PUT', headers: { origin: 'https://studio.example', 'x-manga-workflow': '1', 'content-type': 'application/octet-stream', 'content-length': String(11 * 1024 * 1024) }, body: 'small' });
  assert.equal((await api.PUT(tooLarge)).status, 413);
  assert.equal(api.calls.length, 1);
});

test('hosted assets stream through private service after admin authorization', async () => {
  const url = 'https://studio.example/api/asset?project=' + 'a'.repeat(32) + '&path=input%2Fpage.png';
  const api = load('../app/api/asset/route.ts');
  const result = await api.GET(new Request(url, { headers: { range: 'bytes=0-4' } }));
  assert.equal(result.status, 206);
  assert.equal(result.headers.get('content-type'), 'image/png');
  assert.equal(api.calls[0].endpoint, '/projects/' + 'a'.repeat(32) + '/assets/input/page.png');
  const denied = load('../app/api/asset/route.ts', { denied: 403 });
  assert.equal((await denied.GET(new Request(url))).status, 403);
  assert.equal(denied.calls.length, 0);
});
