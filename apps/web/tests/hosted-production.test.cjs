const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');

const fixture = {
  budget: { configured: true, paused: false, provider_allowance_micro: 25000000, provider_reserved_micro: 1000000, provider_used_micro: 2000000, infrastructure_reported_micro: 300000, infrastructure_reserved_micro: 50000 },
  chapter_quota: { utc_month: '2026-10', used: 2, limit: 5, remaining: 3, pages_per_chapter: 40 },
  reader_limits: { pending: 5, new_per_utc_day: 10 },
  artifact_collection: { active: false, epoch: 4 },
};

function load({ denied = null, cloud = true, privateFailure = null } = {}) {
  const calls = [];
  const api = {};
  class PrivateApiError extends Error {
    constructor(status, code, message) { super(message); this.status = status; this.code = code; }
  }
  const compiled = ts.transpileModule(fs.readFileSync(require.resolve('../app/api/production/route.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  new Function('exports', 'require', compiled)(api, name => {
    if (name.endsWith('/require-admin')) return {
      requireAdmin: async () => denied ? new Response(JSON.stringify({ error: 'denied' }), { status: denied }) : null,
      trustedSessionRequest: request => request.headers.get('origin') === 'https://studio.example',
    };
    if (name.endsWith('/private-api')) return {
      isCloudExecution: () => cloud,
      PrivateApiError,
      privateJson: async (request, endpoint, init) => {
        calls.push({ request, endpoint, init });
        if (privateFailure) throw privateFailure instanceof Error ? privateFailure : new PrivateApiError(privateFailure.status, privateFailure.code, privateFailure.message);
        return endpoint.endsWith('/pause') ? { ...fixture, budget: { ...fixture.budget, paused: true, pause_reason: 'maintenance' } } : fixture;
      },
    };
    return require(name);
  });
  return { ...api, calls, PrivateApiError };
}

function request(method = 'GET', body, headers = {}) {
  return new Request('https://studio.example/api/production', {
    method,
    headers: { ...(body === undefined ? {} : { 'content-type': 'application/json' }), ...headers },
    ...(body === undefined ? {} : { body: typeof body === 'string' ? body : JSON.stringify(body) }),
  });
}

test('production status requires verified admin and cloud execution, then uses private no-store API', async () => {
  const denied = load({ denied: 403 });
  const deniedResponse = await denied.GET(request());
  assert.equal(deniedResponse.status, 403);
  assert.match(deniedResponse.headers.get('cache-control'), /no-store/);
  assert.equal(denied.calls.length, 0);

  const local = load({ cloud: false });
  assert.equal((await local.GET(request())).status, 503);
  assert.equal(local.calls.length, 0);

  const api = load();
  const response = await api.GET(request());
  assert.equal(response.status, 200);
  assert.match(response.headers.get('cache-control'), /no-store/);
  assert.deepEqual(await response.json(), fixture);
  assert.equal(api.calls[0].endpoint, '/production/status');
});

test('pause route requires same-origin exact bounded reason payload and forwards only the requested fields', async () => {
  const api = load();
  assert.equal((await api.POST(request('POST', { paused: true, reason: 'maintenance' }))).status, 403);
  assert.equal((await api.POST(request('POST', { paused: true, reason: 'maintenance' }, { origin: 'https://studio.example' }))).status, 200);
  assert.equal(api.calls.length, 1);
  assert.equal(api.calls[0].endpoint, '/production/pause');
  assert.deepEqual(JSON.parse(api.calls[0].init.body), { paused: true, reason: 'maintenance' });
  assert.match((await api.POST(request('POST', { paused: true, reason: 'maintenance', actor: 'forged' }, { origin: 'https://studio.example' }))).status.toString(), /^400$/);
  assert.equal((await api.POST(request('POST', { paused: true, reason: '  ' }, { origin: 'https://studio.example' }))).status, 400);
  assert.equal((await api.POST(request('POST', { paused: true, reason: 'x'.repeat(501) }, { origin: 'https://studio.example' }))).status, 400);
  assert.equal((await api.POST(request('POST', '{', { origin: 'https://studio.example' }))).status, 400);
  assert.equal(api.calls.length, 1);
});

test('private API errors retain safe status and messages but redirects become gateway errors', async () => {
  const unavailable = load({ privateFailure: { status: 409, code: 'production_paused', message: 'Already paused.' } });
  const conflict = await unavailable.POST(request('POST', { paused: true, reason: 'maintenance' }, { origin: 'https://studio.example' }));
  assert.equal(conflict.status, 409);
  assert.deepEqual(await conflict.json(), { error: 'Already paused.', code: 'production_paused' });
  assert.match(conflict.headers.get('cache-control'), /no-store/);

  const redirected = load({ privateFailure: { status: 302, code: 'redirect', message: 'Follow this.' } });
  const response = await redirected.GET(request());
  assert.equal(response.status, 502);
  assert.deepEqual(await response.json(), { error: 'Private service request failed.', code: 'private_api_error' });
});
