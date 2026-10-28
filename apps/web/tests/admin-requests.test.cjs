const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

function load(relative, mocks, cache = new Map()) {
  const filename = path.resolve(__dirname, relative);
  if (cache.has(filename)) return cache.get(filename);
  const exports = {};
  cache.set(filename, exports);
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function('exports', 'require', compiled)(exports, name => {
    if (name in mocks) return mocks[name];
    if (name.endsWith('/firebase-admin')) return mocks.firebaseAdmin;
    if (name.startsWith('.')) {
      const base = path.resolve(path.dirname(filename), name);
      const file = ['.tsx', '.ts'].map(ext => base + ext).find(fs.existsSync);
      if (file) return load(file, mocks, cache);
    }
    return require(name);
  });
  return exports;
}

function fixture() {
  const writes = [];
  const profileQueries = [];
  const profiles = new Map([['alice', 'Alice Reader'], ['bob', 'Bob Reader']]);
  let reads = 0;
  class Timestamp { constructor(date) { this.date = date; } toDate() { return new Date(this.date); } }
  const records = new Map([
    ['first', { userId: 'alice', mangaTitle: 'First story', chapter: 1, notes: '', status: 'submitted', createdAt: new Timestamp('2026-10-27') }],
    ['second', { userId: 'bob', mangaTitle: 'Second story', chapter: 2, notes: 'Please narrate', status: 'approved', createdAt: new Timestamp('2026-10-28') }],
  ]);
  const doc = id => ({ id, exists: records.has(id), data: () => records.get(id) });
  const timestamp = Symbol('server timestamp');
  const db = {
    collection: name => {
      assert.equal(name, 'manga_requests');
      return { get: async () => { reads++; return { docs: [...records.keys()].map(doc) }; }, doc: id => ({ id, get: async () => { reads++; return doc(id); } }) };
    },
    runTransaction: async callback => callback({ get: async ref => { reads++; return doc(ref.id); }, update: (ref, data) => { writes.push({ id: ref.id, ...data }); records.set(ref.id, { ...records.get(ref.id), ...data }); } }),
  };
  const mocks = {
    'server-only': {},
    'firebase-admin/firestore': { Timestamp, FieldValue: { serverTimestamp: () => timestamp } },
    firebaseAdmin: { getAdminFirestore: () => db, getAdminAuth: () => {
      const verify = async (value, revoked) => {
        assert.equal(revoked, true);
        if (!['admin', 'reader'].includes(value)) throw new Error('Invalid identity');
        return { uid: value + '-uid', aud: 'fixture', admin: value === 'admin' };
      };
      return { verifyIdToken: verify, verifySessionCookie: verify, getUsers: async identifiers => {
        assert.ok(identifiers.length <= 100);
        profileQueries.push(identifiers);
        return { users: identifiers.filter(item => profiles.has(item.uid)).map(item => ({ uid: item.uid, displayName: profiles.get(item.uid) })), notFound: identifiers.filter(item => !profiles.has(item.uid)) };
      } };
    } },
  };
  const api = load('../app/api/admin/requests/route.ts', mocks);
  return { api, records, writes, timestamp, mocks, profiles, profileQueries, reads: () => reads };
}
function request(method, body, token = 'admin', query = '') {
  return new Request('http://localhost/api/admin/requests' + query, { method, headers: token ? { Authorization: `Bearer ${token}` } : {}, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
}

test('sign-in returns admins to the dashboard but readers and external destinations to Browse', () => {
  const React = require('react');
  const original = Object.getOwnPropertyDescriptor(globalThis, 'window');
  try {
    for (const [isAdmin, next, expected] of [[true, '/admin/requests', '/admin/requests'], [false, '/admin/requests', '/browse'], [true, 'https://example.test', '/browse']]) {
      const effects = [];
      const destinations = [];
      Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { search: '?next=' + encodeURIComponent(next) } } });
      const { AuthForm } = load('../features/identity/auth-form.tsx', {
        react: { ...React, useEffect: effect => effects.push(effect) },
        './auth-provider': { useAuth: () => ({ user: { uid: 'fixture' }, isAdmin, authorizationReady: true, loading: false }) },
        './firebase-client': { authErrorMessage: error => error.message },
        'next/navigation': { useRouter: () => ({ replace: destination => destinations.push(destination) }) },
        'next/link': props => React.createElement('a', props),
      });
      require('react-dom/server').renderToStaticMarkup(React.createElement(AuthForm, { mode: 'login' }));
      effects.forEach(effect => effect());
      assert.deepEqual(destinations, [expected]);
    }
  } finally { if (original) Object.defineProperty(globalThis, 'window', original); else delete globalThis.window; }
});

test('admin request reads and writes reject anonymous, reader and invalid identities before database access', async () => {
  const f = fixture();
  for (const method of ['GET', 'PATCH']) {
    for (const [token, status] of [[null, 401], ['reader', 403], ['invalid', 401]]) {
      assert.equal((await f.api[method](request(method, undefined, token))).status, status);
    }
  }
  assert.equal(f.reads(), 0);
  assert.deepEqual(f.profileQueries, []);
  assert.deepEqual(f.writes, []);
});
test('admin listing includes different owners, newest first, and single-request context', async () => {
  const f = fixture();
  const response = await f.api.GET(request('GET'));
  assert.equal(response.headers.get('Cache-Control'), 'private, no-store');
  const { requests } = await response.json();
  assert.deepEqual(requests.map(item => item.userId), ['bob', 'alice']);
  assert.deepEqual(requests.map(item => item.requesterName), ['Bob Reader', 'Alice Reader']);
  assert.deepEqual(requests.map(item => item.status), ['approved', 'submitted']);
  const single = await f.api.GET(request('GET', undefined, 'admin', '?id=first'));
  assert.equal((await single.json()).requests.length, 1);
  assert.equal((await f.api.GET(request('GET', undefined, 'admin', '?id=missing'))).status, 404);
  assert.equal((await f.api.GET(request('GET', undefined, 'admin', '?id=..%2Fother'))).status, 400);
});
test('status updates use verified actor, preserve request content, and reject stale transitions', async () => {
  const f = fixture();
  const body = { id: 'first', expectedStatus: 'submitted', status: 'approved', updatedBy: 'forged' };
  assert.equal((await f.api.PATCH(request('PATCH', body))).status, 200);
  assert.deepEqual(f.writes, [{ id: 'first', status: 'approved', updatedBy: 'admin-uid', updatedAt: f.timestamp }]);
  assert.equal(f.records.get('first').userId, 'alice');
  assert.equal((await f.api.PATCH(request('PATCH', { ...body, status: 'rejected' }))).status, 409);
  assert.equal(f.writes.length, 1);
});

test('submitted requests load as submitted and can be reviewed without a data migration', async () => {
  const f = fixture();
  f.records.get('first').status = 'submitted';
  f.records.get('second').status = ' SUBMITTED ';
  f.records.get('second').userId = '';
  const response = await f.api.GET(request('GET'));
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.deepEqual(result.requests.map(item => item.status), ['submitted', 'submitted']);
  assert.equal(result.requests[0].requesterName, 'Name unavailable');
  assert.deepEqual(f.profileQueries, [[{ uid: 'alice' }]]);
  assert.equal(f.records.get('first').status, 'submitted', 'GET must not rewrite stored requests');
  assert.equal((await f.api.PATCH(request('PATCH', { id: 'first', expectedStatus: 'submitted', status: 'approved' }))).status, 200);
  assert.equal((await f.api.PATCH(request('PATCH', { id: 'second', expectedStatus: 'submitted', status: 'rejected' }))).status, 200);
});

test('requester names handle deleted/unnamed accounts and deduplicate profile lookup batches', async () => {
  const f = fixture();
  f.profiles.delete('alice');
  f.profiles.set('bob', ' ');
  for (let i = 0; i < 101; i++) f.records.set(`extra-${i}`, { ...f.records.get('first'), userId: `reader-${i}` });
  f.records.set('duplicate', { ...f.records.get('first') });
  const result = await (await f.api.GET(request('GET'))).json();
  assert.equal(result.requests.find(item => item.id === 'first').requesterName, 'Deleted account');
  assert.equal(result.requests.find(item => item.id === 'second').requesterName, 'Unnamed reader');
  assert.deepEqual(f.profileQueries.map(batch => batch.length), [100, 3]);
});
test('profile lookup failure keeps request data available without presenting IDs as names', async () => {
  const f = fixture();
  const originalAuth = f.mocks.firebaseAdmin.getAdminAuth;
  f.mocks.firebaseAdmin.getAdminAuth = () => ({ ...originalAuth(), getUsers: async () => { throw new Error('Profile service unavailable'); } });
  const response = await f.api.GET(request('GET'));
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.deepEqual(result.requests.map(item => item.requesterName), ['Name unavailable', 'Name unavailable']);
});
test('invalid transitions, malformed JSON, cookie-only mutation and missing records cannot write', async () => {
  const f = fixture();
  for (const body of [null, [], { id: '../other', expectedStatus: 'submitted', status: 'approved' }, { id: 'first', expectedStatus: 'submitted', status: 'ready' }, { id: 'first', expectedStatus: 'ready', status: 'published' }]) {
    assert.equal((await f.api.PATCH(request('PATCH', body))).status, 400);
  }
  assert.equal((await f.api.PATCH(new Request('http://localhost/api/admin/requests', { method: 'PATCH', headers: { Authorization: 'Bearer admin' }, body: '{' }))).status, 400);
  assert.equal((await f.api.PATCH(new Request('http://localhost/api/admin/requests', { method: 'PATCH', headers: { cookie: 'koetts-session=admin' } }))).status, 401);
  assert.equal((await f.api.PATCH(request('PATCH', { id: 'missing', expectedStatus: 'submitted', status: 'approved' }))).status, 404);
  assert.deepEqual(f.writes, []);
});
test('approved requests can be tracked through processing and ready; rejected requests reopen as submitted', async () => {
  const f = fixture();
  for (const [id, expectedStatus, status] of [['second', 'approved', 'processing'], ['second', 'processing', 'ready'], ['first', 'submitted', 'rejected'], ['first', 'rejected', 'submitted']]) {
    assert.equal((await f.api.PATCH(request('PATCH', { id, expectedStatus, status }))).status, 200);
  }
  assert.equal(f.records.get('second').status, 'ready');
});
test('dashboard page checks server session and remains usable without hosted Studio', async t => {
  const previous = process.env.MANGA_FRONTEND_ONLY;
  t.after(() => { if (previous === undefined) delete process.env.MANGA_FRONTEND_ONLY; else process.env.MANGA_FRONTEND_ONLY = previous; });
  const component = () => null;
  for (const [identity, destination] of [['invalid', '/login?next=%2Fadmin%2Frequests'], ['reader', '/browse'], ['admin', null]]) {
    const f = fixture();
    const page = load('../app/admin/requests/page.tsx', { ...f.mocks,
      'next/headers': { headers: async () => new Headers({ cookie: `koetts-session=${identity}` }) },
      'next/navigation': { redirect: location => { throw new Error(location); } },
      '../../../features/requests/admin-requests-page': { default: component, __esModule: true },
    });
    process.env.MANGA_FRONTEND_ONLY = '1';
    if (destination) await assert.rejects(page.default(), { message: destination });
    else { const result = await page.default(); assert.equal(result.type, component); assert.equal(result.props.studioAvailable, false); }
  }
});

test('dashboard updates, preserves rows on failure, and clears private data after role loss', async t => {
  const React = require('react');
  const { act } = React;
  const { JSDOM } = require('jsdom');
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/admin/requests' });
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  dom.window.HTMLDialogElement.prototype.close = function () { this.open = false; };
  const originals = Object.fromEntries(['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const f = fixture();
  const auth = { user: { uid: 'admin', getIdToken: async () => 'admin' }, isAdmin: true, authorizationReady: true };
  let fail = false;
  globalThis.fetch = async (url, options) => {
    if (fail) return Response.json({ error: 'Refresh before retrying.' }, { status: 409 });
    return f.api[options.method || 'GET'](new Request('http://localhost' + url, options));
  };
  const Page = load('../features/requests/admin-requests-page.tsx', {
    '../identity/auth-provider': { useAuth: () => auth },
    '../identity/require-sign-in': { RequireSignIn: ({ children }) => children },
    '../identity/account-nav': { AccountNav: () => null },
  }).default;
  const root = require('react-dom/client').createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  const render = () => act(async () => root.render(React.createElement(Page)));
  const click = text => act(async () => { const button = [...document.querySelectorAll('button')].find(item => (item.getAttribute('aria-label') || item.textContent).startsWith(text)); assert.ok(button, text); button.click(); });
  await render();
  assert.equal(document.querySelectorAll('tbody tr').length, 2);
  assert.match(document.querySelector('tbody').textContent, /Bob Reader/);
  assert.equal(document.querySelector('tbody details'), null);
  assert.equal(document.querySelector('tbody .request-status'), null);
  assert.equal(document.querySelector('tbody td:nth-child(3)').textContent, 'Please narrate');
  const generate = document.querySelector('a[aria-label="Generate"]');
  assert.equal(generate.textContent, '');
  assert.equal(document.getElementById(generate.getAttribute('aria-describedby')).textContent, 'Generate');
  await click('Approve');
  assert.equal(document.querySelectorAll('tbody .admin-status-text')[1].textContent, 'approved');
  assert.equal(document.querySelectorAll('tbody tr').length, 2);
  assert.equal(document.querySelector('tbody a').getAttribute('href'), '/?request=second&create=1');
  fail = true;
  await click('Mark processing');
  assert.match(document.querySelector('[role="alert"]').textContent, /Refresh/);
  assert.equal(document.querySelectorAll('tbody tr').length, 2);
  fail = false;
  const writesBeforeRejection = f.writes.length;
  const rejectButton = document.querySelector('button[aria-label="Reject"]');
  rejectButton.focus();
  await click('Reject');
  assert.equal(document.querySelector('dialog').open, true);
  assert.match(document.querySelector('dialog').textContent, /Second story/);
  assert.equal(document.activeElement.textContent, 'Keep request');
  assert.equal(f.writes.length, writesBeforeRejection, 'opening confirmation must not reject');
  await click('Keep request');
  assert.equal(document.querySelector('dialog').open, false);
  assert.equal(document.activeElement, rejectButton);
  assert.equal(f.writes.length, writesBeforeRejection, 'cancel does not write');
  await click('Reject');
  await act(async () => document.querySelector('dialog').dispatchEvent(new dom.window.Event('cancel', { cancelable: true })));
  assert.equal(document.querySelector('dialog').open, false, 'Escape cancels confirmation');
  await click('Reject');
  fail = true;
  await click('Reject request');
  assert.equal(document.querySelector('dialog').open, true, 'failed rejection keeps confirmation visible');
  assert.match(document.querySelector('dialog [role="alert"]').textContent, /Refresh/);
  assert.equal(f.writes.length, writesBeforeRejection);
  fail = false;
  await click('Reject request');
  assert.equal(f.writes.length, writesBeforeRejection + 1);
  assert.equal(f.records.get('second').status, 'rejected');
  assert.equal(document.querySelector('dialog').open, false);
  f.records.clear();
  await click('Refresh requests');
  assert.match(document.querySelector('tbody').textContent, /No requests yet/);
  assert.equal(document.querySelectorAll('thead th').length, 6, 'empty database retains table headings');
  assert.ok(document.querySelector('nav[aria-label="Admin navigation"]'));
  auth.authorizationReady = false;
  await render();
  assert.ok([...document.querySelectorAll('tbody button')].every(button => button.disabled));
  auth.isAdmin = false;
  await render();
  assert.equal(document.querySelector('tbody'), null);
  assert.match(document.body.textContent, /Administrator access required/);
});
