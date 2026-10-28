const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');

const compiled = ts.transpileModule(fs.readFileSync(require.resolve('../app/api/requests/route.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;

function loadRoute() {
  const writes = [];
  const queries = [];
  const timestamp = Symbol('server timestamp');
  class Timestamp { toDate() { return new Date('2026-10-28T00:00:00Z'); } }
  const api = {};
  new Function('exports', 'require', compiled)(api, name => {
    if (name === 'firebase-admin/firestore') return { Timestamp, FieldValue: { serverTimestamp: () => timestamp } };
    if (name === '../../../features/identity/firebase-admin') return {
      getAdminAuth: () => ({ verifyIdToken: async (token, revoked) => {
        assert.equal(revoked, true);
        if (token !== 'valid') throw new Error('Invalid token');
        return { uid: 'alice' };
      } }),
      getAdminFirestore: () => ({ collection: name => {
        assert.equal(name, 'manga_requests');
        return {
          add: async data => { writes.push(data); return { id: 'saved' }; },
          where: (...args) => {
            queries.push(args);
            return { get: async () => ({ docs: [{ id: 'saved', data: () => ({
              mangaTitle: 'Example', chapter: 2, notes: '', status: 'pending', createdAt: new Timestamp(),
            }) }] }) };
          },
        };
      } }),
    };
    throw new Error(`Unexpected dependency: ${name}`);
  });
  return { api, writes, queries, timestamp };
}

function request(method, body, token = 'valid') {
  return new Request('http://localhost/api/requests', {
    method, headers: token ? { Authorization: `Bearer ${token}` } : {},
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}

test('requests deny missing or invalid identity before accessing Firestore', async () => {
  const { api, writes, queries } = loadRoute();
  for (const method of ['GET', 'POST']) {
    for (const token of [null, 'invalid']) {
      assert.equal((await api[method](request(method, undefined, token))).status, 401);
    }
  }
  assert.deepEqual(writes, []);
  assert.deepEqual(queries, []);
});

test('request creation uses verified owner, numeric chapter, and server timestamp', async () => {
  const { api, writes, timestamp } = loadRoute();
  const response = await api.POST(request('POST', {
    userId: 'someone-else', mangaTitle: ' Example ', chapter: '002', notes: 'n'.repeat(2000),
  }));
  assert.equal(response.status, 201);
  assert.deepEqual(await response.json(), { id: 'saved' });
  assert.deepEqual(writes, [{ userId: 'alice', mangaTitle: 'Example', chapter: 2,
    notes: 'n'.repeat(2000), status: 'pending', createdAt: timestamp }]);
});

test('invalid chapters and oversized notes are rejected without writes', async () => {
  const { api, writes } = loadRoute();
  for (const body of [
    { mangaTitle: 'Example', chapter: '1.5', notes: '' },
    { mangaTitle: 'Example', chapter: '2', notes: 'n'.repeat(2001) },
  ]) assert.equal((await api.POST(request('POST', body))).status, 400);
  assert.deepEqual(writes, []);
});

test('request listing scopes the query to the signed-in user and disables caching', async () => {
  const { api, queries } = loadRoute();
  const response = await api.GET(request('GET'));
  assert.equal(response.status, 200);
  assert.deepEqual(queries, [['userId', '==', 'alice']]);
  assert.equal(response.headers.get('Cache-Control'), 'private, no-store');
  assert.deepEqual(await response.json(), { requests: [{ id: 'saved', mangaTitle: 'Example', chapter: 2,
    notes: '', status: 'PENDING', createdAt: '2026-10-28T00:00:00.000Z' }] });
});
