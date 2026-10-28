const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');
const React = require('react');
const { act } = React;
const { JSDOM } = require('jsdom');
function load(relative, mocks, cache = new Map()) {
  const filename = path.resolve(__dirname, relative);
  if (cache.has(filename)) return cache.get(filename);
  const exports = {}; cache.set(filename, exports);
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function('exports', 'require', code)(exports, name => {
    if (name in mocks) return mocks[name];
    if (name === './auth-provider' && mocks['../identity/auth-provider']) return mocks['../identity/auth-provider'];
    if (name.startsWith('.')) {
      const base = path.resolve(path.dirname(filename), name);
      const file = ['.tsx', '.ts'].map(ext => base + ext).find(fs.existsSync);
      if (file) return load(file, mocks, cache);
    }
    return require(name);
  });
  return exports;
}
test('reader submits shared request and sees duplicate feedback', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/request?manga=Manga&chapter=1' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const calls = [];
  globalThis.fetch = async (url, options) => { calls.push([url, options]); return { ok: true, json: async () => ({ request: { duplicate: true } }) }; };
  const mocks = {
    'next/link': props => React.createElement('a', props),
    'next/navigation': { useSearchParams: () => new URLSearchParams('manga=Manga&chapter=1') },
    '../library/library-ui': { LibraryHeader: () => null },
    '../identity/require-sign-in': { RequireSignIn: ({ children }) => children },
    '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'reader' }, authorizationReady: true }) },
    './auth-provider': { useAuth: () => ({ user: { uid: 'reader' }, authorizationReady: true }) },
    './firebase-client': { getFirebaseAuth: () => ({ currentUser: { uid: 'reader', getIdToken: async () => 'reader-token' } }) },
  };
  const Page = load('../features/requests/request-page.tsx', mocks).default;
  const { createRoot } = require('react-dom/client');
  const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  await act(async () => root.render(React.createElement(Page)));
  await act(async () => document.querySelector('form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })));
  assert.equal(calls[0][0], '/api/shared/requests');
  assert.deepEqual(JSON.parse(calls[0][1].body), { title: 'Manga', chapter: '1', notes: '' });
  assert.equal(new Headers(calls[0][1].headers).get('authorization'), 'Bearer reader-token');
  assert.match(document.body.textContent, /already requested/i);
});

test('reader sees persisted requests and can remove only their own entry', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/requests' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  dom.window.HTMLDialogElement.prototype.close = function () { this.open = false; };
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    return { ok: true, json: async () => options.method === 'DELETE' ? { deleted: true } : { requests: [{ id: 'a'.repeat(32), work_id: 'b'.repeat(32), manga_id: 'c'.repeat(32), title: 'Shared Manga', chapter: 3, notes: '', status: 'published', created_at: '2026-10-20 00:00:00' }] } };
  };
  const mocks = {
    'next/link': props => React.createElement('a', props),
    '../library/library-ui': { LibraryHeader: () => null },
    '../identity/require-sign-in': { RequireSignIn: ({ children }) => children },
    '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'reader' }, authorizationReady: true }) },
    './auth-provider': { useAuth: () => ({ user: { uid: 'reader' }, authorizationReady: true }) },
    './firebase-client': { getFirebaseAuth: () => ({ currentUser: { uid: 'reader', getIdToken: async () => 'reader-token' } }) },
  };
  const Page = load('../features/requests/requests-page.tsx', mocks).default;
  const { createRoot } = require('react-dom/client'); const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  await act(async () => root.render(React.createElement(Page)));
  assert.match(document.body.textContent, /Shared Manga/);
  assert.match(document.body.textContent, /published/i);
  await act(async () => [...document.querySelectorAll('button')].find(button => button.getAttribute('aria-label')?.startsWith('Delete request')).click());
  await act(async () => [...document.querySelectorAll('button')].find(button => button.textContent === 'Delete request').click());
  assert.equal(calls.at(-1)[1].method, 'DELETE');
  assert.deepEqual(JSON.parse(calls.at(-1)[1].body), { id: 'a'.repeat(32) });
  assert.equal(new Headers(calls.at(-1)[1].headers).get('authorization'), 'Bearer reader-token');
  assert.match(document.body.textContent, /No requests yet/);
});

test('admin publishes the saved review rather than a newer audition candidate', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/admin/requests' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const workId = 'a'.repeat(32), projectId = 'b'.repeat(32), reviewId = 'c'.repeat(32);
  const reviewedCandidate = 'd'.repeat(32), latestCandidate = 'e'.repeat(32), revision = 'f'.repeat(64);
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    if (options.method === 'POST') return { ok: true, json: async () => ({ result: { id: '1'.repeat(32) } }) };
    if (url === '/api/workflow') return { ok: true, json: async () => ({ projects: [{ id: projectId, name: 'Studio project' }] }) };
    return { ok: true, json: async () => ({ work: [{ id: workId, title: 'Manga', chapter: 1, status: 'approved', requests: [{ id: '2'.repeat(32), notes: 'Reader note', requester_name: 'Fixture Reader' }], link: { project_id: projectId }, publication_id: null, candidate: { id: latestCandidate, revision, export_id: '3'.repeat(32) }, review: { id: reviewId, candidate_id: reviewedCandidate, revision, export_id: '3'.repeat(32) } }] }) };
  };
  const mocks = {
    'next/link': props => React.createElement('a', props),
    '../identity/require-sign-in': { RequireSignIn: ({ children }) => children },
    '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'admin' }, isAdmin: true, authorizationReady: true }) },
    '../identity/firebase-client': { getFirebaseAuth: () => ({ currentUser: { uid: 'admin', getIdToken: async () => 'admin-token' } }) },
  };
  const Page = load('../features/requests/admin-requests-page.tsx', mocks).default;
  const { createRoot } = require('react-dom/client'); const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  await act(async () => root.render(React.createElement(Page)));
  assert.match(document.body.textContent, /Reader note/);
  assert.match(document.body.textContent, /Fixture Reader/);
  assert.ok(document.querySelector('nav[aria-label="Admin navigation"] a[aria-current="page"]'));
  const publish = [...document.querySelectorAll('button')].find(button => button.textContent === 'Publish reviewed audio');
  assert.ok(publish);
  await act(async () => publish.click());
  const sent = calls.find(([, options]) => options.method === 'POST');
  assert.deepEqual(JSON.parse(sent[1].body), { action: 'publish', work_id: workId, review_id: reviewId, revision, expected_publication: null });
  assert.equal(new Headers(sent[1].headers).get('authorization'), 'Bearer admin-token');
});

test('browse displays only published catalog entries', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/browse' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const mangaId = 'b'.repeat(32), workId = 'a'.repeat(32);
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ chapters: [{ work_id: workId, manga_id: mangaId, title: 'Published Manga', chapter: 1, publication_id: 'c'.repeat(32) }] }) });
  const mocks = {
    'next/link': props => React.createElement('a', props),
    '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'reader' }, authorizationReady: true }) },
    './library-ui': { LibraryHeader: () => null, MangaCover: ({ title }) => React.createElement('div', null, title) },
  };
  const Page = load('../features/library/browse-page.tsx', mocks).default;
  const { createRoot } = require('react-dom/client'); const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  await act(async () => root.render(React.createElement(Page)));
  assert.match(document.body.textContent, /Published Manga/);
  assert.doesNotMatch(document.body.textContent, /Echoes of Tomorrow/);
  assert.ok(document.querySelector(`a[href="/manga/${mangaId}"]`));
});

test('manga details links published chapters to playback', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/manga/' + 'b'.repeat(32) });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const mangaId = 'b'.repeat(32), workId = 'a'.repeat(32);
  globalThis.fetch = async () => ({ ok: true, json: async () => ({ chapters: [{ work_id: workId, manga_id: mangaId, title: 'Published Manga', chapter: 3, publication_id: 'c'.repeat(32) }] }) });
  const mocks = {
    'next/link': props => React.createElement('a', props),
    'next/navigation': { useParams: () => ({ id: mangaId }) },
    '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'reader' }, authorizationReady: true }) },
    '../identity/require-sign-in': { RequireSignIn: ({ children }) => children },
    './library-ui': { LibraryHeader: () => null, MangaCover: () => null },
  };
  const Page = load('../features/library/manga-page.tsx', mocks).default;
  const { createRoot } = require('react-dom/client'); const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  await act(async () => root.render(React.createElement(Page)));
  assert.match(document.body.textContent, /Chapter 3/);
  const listen = document.querySelector(`a[href="/read/${mangaId}/${workId}"]`);
  assert.ok(listen); assert.match(listen.textContent, /Listen/);
});

test('audio player refreshes its URL and restores the listening position', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/read' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch', 'setTimeout', 'clearTimeout'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  let calls = 0, played = 0, scheduled;
  const realSetTimeout = globalThis.setTimeout, realClearTimeout = globalThis.clearTimeout;
  globalThis.setTimeout = (callback, delay, ...args) => {
    if (delay === 270000) { scheduled = callback; return 2147483647; }
    return realSetTimeout(callback, delay, ...args);
  };
  globalThis.clearTimeout = timer => { if (timer !== 2147483647) realClearTimeout(timer); };
  globalThis.fetch = async () => { calls++; return { ok: true, json: async () => ({ url: `/api/shared/audio?token=${calls}`, expires_in: 300 }) }; };
  const Player = load('../features/library/published-audio-player.tsx', { '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'reader' }, authorizationReady: true }) } }).PublishedAudioPlayer;
  const { createRoot } = require('react-dom/client'); const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  await act(async () => root.render(React.createElement(Player, { workId: 'a'.repeat(32) })));
  const audio = document.querySelector('audio');
  assert.ok(audio); assert.match(audio.getAttribute('src'), /token=1/);
  audio.currentTime = 42;
  Object.defineProperty(audio, 'paused', { configurable: true, get: () => false });
  audio.play = async () => { played++; };
  assert.ok(scheduled, 'refresh should be scheduled before expiry');
  await act(async () => scheduled());
  assert.equal(calls, 2); assert.match(audio.getAttribute('src'), /token=2/);
  audio.currentTime = 0;
  await act(async () => audio.dispatchEvent(new dom.window.Event('loadedmetadata')));
  assert.equal(audio.currentTime, 42); assert.equal(played, 1);
  await act(async () => audio.dispatchEvent(new dom.window.Event('error')));
  assert.equal(calls, 3);
});

test('reader plays a published chapter without exposing studio images', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/read' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const mangaId = 'b'.repeat(32), workId = 'a'.repeat(32);
  globalThis.fetch = async url => url === '/api/shared/catalog'
    ? { ok: true, json: async () => ({ chapters: [{ work_id: workId, manga_id: mangaId, title: 'Published Manga', chapter: 3, publication_id: 'c'.repeat(32) }] }) }
    : { ok: true, json: async () => ({ url: '/api/shared/audio?token=signed', expires_in: 300 }) };
  const mocks = {
    'next/link': props => React.createElement('a', props),
    'next/navigation': { useParams: () => ({ mangaId, chapterId: workId }) },
    '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'reader' }, authorizationReady: true }) },
    '../identity/require-sign-in': { RequireSignIn: ({ children }) => children },
  };
  const Page = load('../features/library/reader-page.tsx', mocks).default;
  const { createRoot } = require('react-dom/client'); const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  await act(async () => root.render(React.createElement(Page)));
  assert.match(document.body.textContent, /Chapter 3/);
  assert.equal(document.querySelector('audio').getAttribute('src'), '/api/shared/audio?token=signed');
  assert.match(document.body.textContent, /pages are not available/i);
  assert.equal(document.querySelector('img'), null);
  const accessibility = [...document.querySelectorAll('button')].find(button => button.textContent === 'Accessibility');
  assert.ok(accessibility);
  await act(async () => accessibility.click());
  const settings = document.querySelectorAll('input[type="checkbox"]');
  await act(async () => { settings[0].click(); settings[1].click(); });
  assert.ok(document.querySelector('main').classList.contains('reader-high-contrast'));
  assert.ok(document.querySelector('main').classList.contains('reader-large-controls'));
});

test('audio refresh waits for session verification and resumes afterward', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/read' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  let ready = true, calls = 0;
  globalThis.fetch = async () => { calls++; return { ok: true, json: async () => ({ url: `/api/shared/audio?token=${calls}`, expires_in: 300 }) }; };
  const Player = load('../features/library/published-audio-player.tsx', { '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'reader' }, authorizationReady: ready }) } }).PublishedAudioPlayer;
  const { createRoot } = require('react-dom/client'); const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  const render = () => root.render(React.createElement(Player, { workId: 'a'.repeat(32) }));
  await act(async () => render());
  assert.equal(calls, 1);
  ready = false;
  await act(async () => render());
  await act(async () => document.querySelector('audio').dispatchEvent(new dom.window.Event('error')));
  assert.equal(calls, 1);
  ready = true;
  await act(async () => render());
  assert.equal(calls, 2);
});

test('admin action stops if session verification changes while preparing', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/admin/requests' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const workId = 'a'.repeat(32), projectId = 'b'.repeat(32);
  let ready = true, release;
  const wait = new Promise(resolve => { release = resolve; });
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    if (String(url).startsWith('/api/workflow?project=')) { await wait; return { ok: true, json: async () => ({ revision: 'f'.repeat(64) }) }; }
    if (url === '/api/workflow') return { ok: true, json: async () => ({ projects: [{ id: projectId, name: 'Project' }] }) };
    return { ok: true, json: async () => ({ work: [{ id: workId, title: 'Manga', chapter: 1, status: 'approved', requests: [], link: { project_id: projectId }, publication_id: null, candidate: null, review: null }] }) };
  };
  const mocks = {
    'next/link': props => React.createElement('a', props),
    '../identity/require-sign-in': { RequireSignIn: ({ children }) => children },
    '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'admin' }, isAdmin: true, authorizationReady: ready }) },
    '../identity/firebase-client': { getFirebaseAuth: () => ({ currentUser: { uid: 'admin', getIdToken: async () => 'admin-token' } }) },
  };
  const Page = load('../features/requests/admin-requests-page.tsx', mocks).default;
  const { createRoot } = require('react-dom/client'); const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  const render = () => root.render(React.createElement(Page));
  await act(async () => render());
  await act(async () => [...document.querySelectorAll('button')].find(button => button.textContent === 'Prepare export for audition').click());
  ready = false;
  await act(async () => render());
  await act(async () => { release(); await wait; });
  assert.equal(calls.filter(([, options]) => options.method === 'POST').length, 0);
});

test('reader keeps its player and position through same-user session renewal', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/read' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const mangaId = 'b'.repeat(32), workId = 'a'.repeat(32);
  let ready = true, requests = 0;
  const auth = { useAuth: () => ({ user: { uid: 'reader' }, loading: false, authorizationReady: ready, error: ready ? '' : 'Session verification failed', login: async () => {} }) };
  globalThis.fetch = async url => {
    requests++;
    return url === '/api/shared/catalog'
      ? { ok: true, json: async () => ({ chapters: [{ work_id: workId, manga_id: mangaId, title: 'Published Manga', chapter: 3, publication_id: 'c'.repeat(32) }] }) }
      : { ok: true, json: async () => ({ url: '/api/shared/audio?token=' + requests, expires_in: 300 }) };
  };
  const mocks = {
    'next/link': props => React.createElement('a', props),
    'next/navigation': { useParams: () => ({ mangaId, chapterId: workId }), useRouter: () => ({ replace() {} }) },
    '../identity/auth-provider': auth, './auth-provider': auth,
  };
  const Page = load('../features/library/reader-page.tsx', mocks).default;
  const { createRoot } = require('react-dom/client'); const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  const render = () => root.render(React.createElement(Page));
  await act(async () => render());
  const audio = document.querySelector('audio'); audio.currentTime = 42;
  const before = requests;
  ready = false;
  await act(async () => render());
  assert.equal(document.querySelector('audio'), audio);
  assert.equal(audio.currentTime, 42);
  assert.ok(audio.closest('[inert]'));
  assert.equal(requests, before);
  ready = true;
  await act(async () => render());
  assert.equal(document.querySelector('audio'), audio);
  assert.equal(audio.currentTime, 42);
  assert.equal(audio.closest('[inert]'), null);
});

test('admin keeps audition audio mounted during same-user session renewal', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/admin/requests' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  let ready = true;
  const auth = { useAuth: () => ({ user: { uid: 'admin' }, isAdmin: true, loading: false, authorizationReady: ready, error: '', login: async () => {} }) };
  const releases = [];
  let background = false;
  globalThis.fetch = async url => {
    if (background) await new Promise(resolve => { releases.push(resolve); });
    return { ok: true, json: async () => url === '/api/workflow' ? { projects: [] } : { work: [{ id: 'a'.repeat(32), title: 'Manga', chapter: 1, status: 'approved', requests: [], link: { project_id: 'b'.repeat(32) }, publication_id: null, candidate: { id: 'c'.repeat(32), revision: 'd'.repeat(64), export_id: 'e'.repeat(32) }, review: null }] } };
  };
  const mocks = {
    'next/link': props => React.createElement('a', props),
    'next/navigation': { useRouter: () => ({ replace() {} }) },
    '../identity/auth-provider': auth, './auth-provider': auth,
    '../identity/firebase-client': { getFirebaseAuth: () => ({ currentUser: { uid: 'admin', getIdToken: async () => 'admin-token' } }) },
  };
  const Page = load('../features/requests/admin-requests-page.tsx', mocks).default;
  const { createRoot } = require('react-dom/client'); const root = createRoot(document.getElementById('root'));
  t.after(async () => { releases.forEach(release => release()); await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  const render = () => root.render(React.createElement(Page));
  await act(async () => render());
  const audio = document.querySelector('audio'); audio.currentTime = 42;
  ready = false;
  await act(async () => render());
  assert.equal(document.querySelector('audio'), audio);
  assert.ok(audio.closest('[inert]'));
  background = true;
  ready = true;
  await act(async () => render());
  assert.equal(document.querySelector('audio'), audio);
  assert.equal(audio.currentTime, 42);
  await act(async () => releases.forEach(release => release()));
  assert.equal(document.querySelector('audio'), audio);
  assert.equal(audio.currentTime, 42);
});
