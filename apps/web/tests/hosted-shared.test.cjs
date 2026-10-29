const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');

function compile(path) {
  return ts.transpileModule(fs.readFileSync(require.resolve(path), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  }).outputText;
}

function loadPrivateApi() {
  const api = {};
  let credentialReads = 0;
  new Function('exports', 'require', compile('../lib/private-api.ts'))(api, name => {
    if (name === 'server-only') return {};
    if (name === 'google-auth-library') return { GoogleAuth: class {
      async getIdTokenClient(audience) {
        assert.equal(audience, 'https://private.example');
        return { idTokenProvider: { fetchIdToken: async () => 'service-token' } };
      }
    } };
    if (name.endsWith('/require-admin')) return { userCredential: request => {
      credentialReads++;
      assert.equal(request.headers.get('authorization'), 'Bearer browser-token');
      return { header: 'X-KoeTTS-User-Token', value: 'verified-user-token' };
    } };
    return require(name);
  });
  return { ...api, credentialReads: () => credentialReads };
}

function restoreEnv(t, key) {
  const prior = process.env[key];
  t.after(() => prior === undefined ? delete process.env[key] : process.env[key] = prior);
}

test('private transport separates service and verified user auth and rechecks each request', async t => {
  restoreEnv(t, 'S3_API_URL'); restoreEnv(t, 'MANGA_EXECUTION_MODE');
  process.env.S3_API_URL = 'https://private.example'; process.env.MANGA_EXECUTION_MODE = 'cloud';
  const originalFetch = global.fetch;
  t.after(() => { global.fetch = originalFetch; });
  const api = loadPrivateApi();
  let seen;
  global.fetch = async (url, init) => {
    seen = { url: String(url), init };
    return Response.json({ ok: true });
  };
  const request = new Request('https://app.example/api', { headers: {
    authorization: 'Bearer browser-token', cookie: 'session=secret',
    'x-serverless-authorization': 'browser-service-token', 'x-koetts-user-token': 'forged',
  } });
  await api.privateApi(request, '/shared', { method: 'POST', headers: {
    'content-type': 'application/json', authorization: 'forged', cookie: 'forged',
    'x-serverless-authorization': 'forged', 'x-koetts-session-cookie': 'forged', 'idempotency-key': 'operation-123',
  }, body: '{}' });
  assert.equal(seen.url, 'https://private.example/shared');
  assert.equal(seen.init.headers.get('authorization'), 'Bearer service-token');
  assert.equal(seen.init.headers.get('x-serverless-authorization'), 'Bearer service-token');
  assert.equal(seen.init.headers.get('x-koetts-user-token'), 'verified-user-token');
  assert.equal(seen.init.headers.get('x-koetts-session-cookie'), null);
  assert.equal(seen.init.headers.get('cookie'), null);
  assert.equal(seen.init.headers.get('idempotency-key'), 'operation-123');
  await api.privateApi(request, '/shared');
  assert.equal(api.credentialReads(), 2);
});

test('invalid execution mode, private origin, and absolute paths fail before fetch', async t => {
  restoreEnv(t, 'S3_API_URL'); restoreEnv(t, 'MANGA_EXECUTION_MODE');
  const originalFetch = global.fetch; let calls = 0;
  t.after(() => { global.fetch = originalFetch; });
  global.fetch = async () => { calls++; throw new Error('unexpected'); };
  const api = loadPrivateApi();
  const request = new Request('https://app.example', { headers: { authorization: 'Bearer browser-token' } });
  process.env.MANGA_EXECUTION_MODE = 'invalid'; process.env.S3_API_URL = 'https://private.example';
  assert.throws(() => api.hostedMode(), error => error.code === 'invalid_execution_mode');
  process.env.MANGA_EXECUTION_MODE = '';
  assert.throws(() => api.hostedMode(), error => error.code === 'invalid_execution_mode');
  process.env.MANGA_EXECUTION_MODE = 'cloud';
  for (const url of ['http://private.example', 'https://user@private.example', 'https://private.example/base']) {
    process.env.S3_API_URL = url;
    await assert.rejects(api.privateApi(request, '/shared'), error => error.code.startsWith('private_api_'));
  }
  process.env.S3_API_URL = 'https://private.example';
  await assert.rejects(api.privateApi(request, 'https://evil.example/shared'), error => error.code === 'invalid_private_path');
  assert.equal(calls, 0);
});

test('private JSON keeps status and sanitized typed backend error', async t => {
  restoreEnv(t, 'S3_API_URL'); restoreEnv(t, 'MANGA_EXECUTION_MODE');
  process.env.S3_API_URL = 'https://private.example'; process.env.MANGA_EXECUTION_MODE = 'cloud';
  const originalFetch = global.fetch; t.after(() => { global.fetch = originalFetch; });
  global.fetch = async () => Response.json({ error: { code: 'daily_limit', message: 'Daily limit\n reached' } }, { status: 429 });
  const api = loadPrivateApi();
  const request = new Request('https://app.example', { headers: { authorization: 'Bearer browser-token' } });
  await assert.rejects(api.privateJson(request, '/shared'), error => error.status === 429 && error.code === 'daily_limit' && error.message === 'Daily limit  reached');
});

test('private proxy streams range response with only safe private headers', async t => {
  restoreEnv(t, 'S3_API_URL'); restoreEnv(t, 'MANGA_EXECUTION_MODE');
  process.env.S3_API_URL = 'https://private.example'; process.env.MANGA_EXECUTION_MODE = 'cloud';
  const originalFetch = global.fetch; t.after(() => { global.fetch = originalFetch; });
  let seen;
  global.fetch = async (_url, init) => {
    seen = init;
    return new Response(new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode('range-data')); controller.close(); } }), {
      status: 206,
      headers: { 'content-type': 'audio/wav', 'content-length': '10', 'content-range': 'bytes 2-11/20', 'accept-ranges': 'bytes', 'etag': '"abc"', 'set-cookie': 'private=1', 'location': 'https://evil.example' },
    });
  };
  const api = loadPrivateApi();
  const request = new Request('https://app.example/audio', { headers: { authorization: 'Bearer browser-token', range: 'bytes=2-11' } });
  const response = await api.proxyPrivate(request, '/shared/published/id');
  assert.equal(seen.headers.get('range'), 'bytes=2-11');
  assert.equal(response.status, 206); assert.equal(await response.text(), 'range-data');
  assert.equal(response.headers.get('cache-control'), 'private, no-store');
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(response.headers.get('content-range'), 'bytes 2-11/20');
  assert.equal(response.headers.get('etag'), '"abc"');
  assert.equal(response.headers.get('set-cookie'), null); assert.equal(response.headers.get('location'), null);
});

test('private proxy preserves approved image MIME for admin assets', async t => {
  restoreEnv(t, 'S3_API_URL'); restoreEnv(t, 'MANGA_EXECUTION_MODE');
  process.env.S3_API_URL = 'https://private.example'; process.env.MANGA_EXECUTION_MODE = 'cloud';
  const originalFetch = global.fetch; t.after(() => { global.fetch = originalFetch; });
  global.fetch = async () => new Response(new Uint8Array([137, 80, 78, 71]), { status: 200, headers: { 'content-type': 'image/png', 'content-length': '4' } });
  const api = loadPrivateApi();
  const request = new Request('https://app.example/api/assets/image', { headers: { authorization: 'Bearer browser-token' } });
  const response = await api.proxyPrivate(request, '/assets/image');
  assert.equal(response.headers.get('content-type'), 'image/png');
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
  assert.deepEqual(Array.from(new Uint8Array(await response.arrayBuffer())), [137, 80, 78, 71]);
});

test('cloud shared calls use private JSON and never invoke local Python', async t => {
  const exports = {}; const calls = [];
  new Function('exports', 'require', compile('../features/requests/server/shared.ts'))(exports, name => {
    if (name === 'server-only') return {};
    if (name.endsWith('/python')) return { pythonJSON: async () => { throw new Error('local Python must not run'); } };
    if (name.endsWith('/private-api')) return { hostedMode: () => true, privateJson: async (...args) => { calls.push(args); return { served: true }; } };
    return require(name);
  });
  const request = new Request('https://app.example', { headers: { authorization: 'Bearer verified' } });
  assert.deepEqual(await exports.sharedCall({ action: 'catalog' }, request), { served: true });
  assert.equal(calls[0][0], request); assert.equal(calls[0][1], '/shared');
  assert.deepEqual(JSON.parse(calls[0][2].body), { action: 'catalog' });
});

test('hosted audio signing key fails closed without using local file storage', async t => {
  restoreEnv(t, 'MANGA_EXECUTION_MODE'); restoreEnv(t, 'MANGA_AUDIO_SIGNING_KEY');
  process.env.MANGA_EXECUTION_MODE = 'cloud'; delete process.env.MANGA_AUDIO_SIGNING_KEY;
  const api = {};
  new Function('exports', 'require', compile('../features/requests/server/audio-key.ts'))(api, name => {
    if (name === 'server-only') return {};
    if (name.endsWith('/private-api')) return { hostedMode: () => true };
    if (name.endsWith('/python')) return { dataRoot: '/must-not-be-read' };
    return require(name);
  });
  await assert.rejects(api.audioKey(), /signing key is unavailable/);
});

test('published cloud audio rechecks Next auth before private streaming on every request', async () => {
  const api = {}; let authChecks = 0; let privateStreams = 0;
  new Function('exports', 'require', compile('../app/api/shared/audio/route.ts'))(api, name => {
    if (name.endsWith('/require-user')) return { requireUser: async () => {
      authChecks++;
      return authChecks === 1 ? { uid: 'reader', project_id: 'project' } : Response.json({ error: 'revoked' }, { status: 401 });
    } };
    if (name.endsWith('/requests/server/shared')) return { localSharedOnly: () => null, sharedCall: async () => { throw new Error('local Python must not run'); } };
    if (name.endsWith('/requests/server/audio-key')) return { audioKey: async () => Buffer.alloc(32) };
    if (name.endsWith('/requests/server/audio-token')) return { verifyAudioToken: () => ({ work: 'a'.repeat(32), publication: 'b'.repeat(32) }) };
    if (name.endsWith('/requests/server/audio-file')) return { serveAudioFile: async () => { throw new Error('local files must not be read'); } };
    if (name.endsWith('/lib/python')) return { dataRoot: '/unused' };
    if (name.endsWith('/lib/private-api')) return {
      hostedMode: () => true,
      proxyPrivate: async (_request, path) => { privateStreams++; assert.equal(path, `/shared/published/${'a'.repeat(32)}?publication_id=${'b'.repeat(32)}`); return new Response('audio', { status: 206 }); },
    };
    return {};
  });
  const request = () => new Request('https://app.example/api/shared/audio?token=signed', { headers: { range: 'bytes=0-4' } });
  assert.equal((await api.GET(request())).status, 206);
  assert.equal((await api.GET(request())).status, 401);
  assert.equal(authChecks, 2); assert.equal(privateStreams, 1);
});

test('typed intake quota remains HTTP 429 at the shared request route', async () => {
  class PrivateApiError extends Error { constructor(status, code, message) { super(message); this.status = status; this.code = code; } }
  const api = {};
  new Function('exports', 'require', compile('../app/api/shared/requests/route.ts'))(api, name => {
    if (name.endsWith('/require-user')) return { requireUser: async () => ({ uid: 'reader', project_id: 'project' }) };
    if (name.endsWith('/require-admin')) return { trustedSessionRequest: () => true };
    if (name.endsWith('/requests/server/shared')) return {
      localSharedOnly: () => null, principalKey: () => '["project","reader"]', validSharedId: value => typeof value === 'string' && /^[a-f0-9]{32}$/.test(value),
      readSharedJson: async request => request.json(), sharedCall: async () => { throw new PrivateApiError(429, 'daily_limit', 'Daily reader request limit reached.'); },
    };
    if (name.endsWith('/lib/private-api')) return { PrivateApiError };
    return {};
  });
  const response = await api.POST(new Request('https://app.example/api/shared/requests', {
    method: 'POST', headers: { 'content-type': 'application/json', origin: 'https://app.example' },
    body: JSON.stringify({ title: 'Manga', chapter: '1', notes: '' }),
  }));
  assert.equal(response.status, 429);
  assert.deepEqual(await response.json(), { error: { code: 'daily_limit', message: 'Daily reader request limit reached.' } });
});
