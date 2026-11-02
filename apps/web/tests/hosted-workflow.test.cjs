const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');

function load(file, { denied = null, hosted = true, failure } = {}) {
  const calls = [];
  const api = {};
  class PrivateApiError extends Error {
    constructor(status, code, message) { super(message); this.status = status; this.code = code; }
  }
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
      hostedMode: () => hosted,
      PrivateApiError,
      privateJson: async (request, endpoint, init) => { calls.push({ request, endpoint, init }); return { id: 'operation', status: 'queued' }; },
      privateApi: async (request, endpoint, init) => { calls.push({ request, endpoint, init }); if (failure) throw new PrivateApiError(failure.status, failure.code, failure.message); return new Response('event: operation\ndata: {}\n\n', { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'private, no-store' } }); },
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

test('hosted operation stream is admin-only and proxies the private event stream', async () => {
  const api = load('../app/api/workflow/events/route.ts');
  const id = 'a'.repeat(32);
  const request = new Request(`https://studio.example/api/workflow/events?job=${id}`);
  const result = await api.GET(request);
  assert.equal(result.status, 200);
  assert.equal(result.headers.get('content-type'), 'text/event-stream');
  assert.equal(await result.text(), 'event: operation\ndata: {}\n\n');
  assert.equal(api.calls[0].request, request);
  assert.equal(api.calls[0].endpoint, `/operations/${id}/events`);
  assert.equal(new Headers(api.calls[0].init.headers).get('accept'), 'text/event-stream');
  const denied = load('../app/api/workflow/events/route.ts', { denied: 403 });
  assert.equal((await denied.GET(request)).status, 403);
  assert.equal(denied.calls.length, 0);
  assert.equal((await api.GET(new Request('https://studio.example/api/workflow/events?job=bad'))).status, 400);
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

for (const status of [401, 403]) test(`processing endpoints reject HTTP ${status} before parsing or backend work`, async () => {
  for (const [file, method] of [
    ['workflow', 'GET'], ['workflow', 'POST'], ['asset', 'GET'],
    ['workflow/events', 'GET'], ['workflow/upload', 'PUT'],
  ]) {
    const api = load(`../app/api/${file}/route.ts`, { denied: status });
    const response = await api[method](new Request(`https://studio.example/api/${file}`, { method }));
    assert.equal(response.status, status, `${method} ${file}`);
    assert.equal(api.calls.length, 0, `${method} ${file} must not contact the backend`);
  }
});

test('operation stream rejects absent or malformed identifiers without contacting backend', async () => {
  for (const query of ['', '?job=bad', '?job=' + 'A'.repeat(32), '?job=' + 'a'.repeat(33)]) {
    const api = load('../app/api/workflow/events/route.ts');
    const response = await api.GET(new Request('https://studio.example/api/workflow/events' + query));
    assert.equal(response.status, 400);
    assert.equal(api.calls.length, 0);
  }
  const local = load('../app/api/workflow/events/route.ts', { hosted: false });
  assert.equal((await local.GET(new Request('https://studio.example/api/workflow/events?job=' + 'a'.repeat(32)))).status, 503);
  assert.equal(local.calls.length, 0);
});

test('operation stream preserves typed backend errors and forwards cancellation', async () => {
  const request = new Request('https://studio.example/api/workflow/events?job=' + 'a'.repeat(32));
  const failure = { status: 429, code: 'production_paused', message: 'Hosted production is paused' };
  const failed = load('../app/api/workflow/events/route.ts', { failure });
  const response = await failed.GET(request);
  assert.equal(response.status, failure.status);
  assert.deepEqual(await response.json(), { error: failure.message, code: failure.code });
  const controller = new AbortController();
  const incoming = new Request(request, { signal: controller.signal });
  const api = load('../app/api/workflow/events/route.ts');
  await api.GET(incoming);
  controller.abort();
  assert.equal(api.calls[0].init.signal.aborted, true, 'browser disconnect reaches the private request');
});
