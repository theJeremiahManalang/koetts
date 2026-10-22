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
  const exports = {};
  cache.set(filename, exports);
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true } }).outputText;
  new Function('exports', 'require', compiled)(exports, name => {
    if (name in mocks) return mocks[name];
    if (name.startsWith('.')) {
      const base = path.resolve(path.dirname(filename), name);
      const file = ['.tsx', '.ts'].map(ext => base + ext).find(fs.existsSync);
      if (file) return load(file, mocks, cache);
    }
    return require(name);
  });
  return exports;
}

for (const surface of ['request', 'studio', 'polling']) test(surface === 'polling' ? 'active studio polling resumes after session renewal and failed verification' : `${surface} draft survives token renewal and failed verification; account changes clear it`, async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/request' });
  const originals = Object.fromEntries(['window', 'document', 'navigator', 'localStorage', 'URL', 'File', 'ResizeObserver', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, localStorage: dom.window.localStorage, File: dom.window.File, URL: dom.window.URL, ResizeObserver: class { observe() {} disconnect() {} }, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  dom.window.HTMLElement.prototype.scrollTo = () => {};
  URL.createObjectURL = () => 'blob:test-upload';
  URL.revokeObjectURL = () => {};
  const firebaseAuth = { currentUser: null };
  let observer;
  let pending;
  let loginCalls = 0;
  let fail = false;
  let polls = 0;
  let jobStatus = 'running';
  let observedReconciliation = false;
  globalThis.fetch = async url => {
    if (String(url).includes('?job=')) {
      polls++;
      return { ok: true, json: async () => { if (jobStatus === 'reconciliation_required') observedReconciliation = true; return { status: jobStatus, message: 'Rendering fixture' }; } };
    }
    if (pending && url === '/api/auth/session') await pending;
    return { ok: !fail, json: async () => ({ projects: [], has_api_key: false }) };
  };
  const mocks = {
    'firebase/auth': { onIdTokenChanged: (_, next) => { observer = next; return () => {}; }, GoogleAuthProvider: class { setCustomParameters() {} }, signInWithPopup: async () => { loginCalls++; }, signOut: async () => {} },
    '../lib/firebase-client': { getFirebaseAuth: () => firebaseAuth, authErrorMessage: error => error.message },
    '../../components/library-ui': { LibraryHeader: () => null },
    'sonner': { Toaster: () => null, toast: { error() {}, loading() {}, success() {} } },
    '../components/image-order': { ImageOrder: () => null },
    '../components/cast-workspace': { CastWorkspace: () => null },
    '../components/source-workspace': { SourceWorkspace: () => null },
    '../components/script-workspace': { ScriptWorkspace: () => null },
    '../components/loading-state': { LoadingState: () => null },
    'next/link': props => React.createElement('a', props),
    'next/navigation': { useRouter: () => ({ replace() {} }), useSearchParams: () => new URLSearchParams() },
  };
  const cache = new Map();
  const { AuthProvider } = load('../components/auth-provider.tsx', mocks, cache);
  const Page = load(surface === 'request' ? '../app/request/page.tsx' : '../app/studio-workspace.tsx', mocks, cache).default;
  const { createRoot } = require('react-dom/client');
  const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); if (surface === 'polling') await act(async () => { await new Promise(resolve => setTimeout(resolve, 1100)); }); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  await act(async () => root.render(React.createElement(AuthProvider, null, React.createElement(Page))));
  const emit = user => { firebaseAuth.currentUser = user; return observer(user); };
  const user = uid => ({ uid, getIdToken: async () => 'token', getIdTokenResult: async () => ({ token: 'token', claims: { admin: true } }) });
  if (surface === 'polling') {
    localStorage.setItem('manga-tts-job', JSON.stringify({ id: 'a'.repeat(32), project: 'b'.repeat(32), idempotencyKey: 'retained-intent' }));
    localStorage.setItem('manga-tts-pending-operation', JSON.stringify([{ key: 'retained-intent', fingerprint: 'operation' }]));
  }
  await act(async () => emit(user('alice')));
  if (surface === 'polling') {
    assert.ok(polls > 0, 'saved operation must start polling');
    let release;
    pending = new Promise(resolve => { release = resolve; });
    let refresh;
    await act(async () => { refresh = emit(user('alice')); });
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 1100)); });
    fail = true;
    await act(async () => { release(); await refresh; });
    const pausedPolls = polls;
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 1100)); });
    assert.equal(polls, pausedPolls, 'verification failure must pause protected requests');
    pending = null;
    fail = false;
    await act(async () => emit(user('alice')));
    await act(async () => { await new Promise(resolve => setTimeout(resolve, 1100)); });
    assert.ok(polls > pausedPolls, 'reauthentication must resume the existing operation without reload');
    assert.ok(localStorage.getItem('manga-tts-job'), 'running operation recovery record must remain');
    jobStatus = 'reconciliation_required';
    await act(async () => { for (let elapsed = 0; elapsed < 2000 && !observedReconciliation; elapsed += 50) await new Promise(resolve => setTimeout(resolve, 50)); });
    assert.ok(observedReconciliation, 'worker reconciliation state must be observed before checking retained intent');
    assert.ok(localStorage.getItem('manga-tts-pending-operation')?.includes('retained-intent'), 'uncertain outcome must retain its idempotency lookup key');
    return;
  }
  const selector = surface === 'request' ? 'textarea' : 'input[aria-label="Upload manga images"]';
  const textarea = document.querySelector(selector);
  assert.ok(textarea);
  if (surface === 'request') await act(async () => { Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, 'value').set.call(textarea, 'Keep my review notes'); textarea.dispatchEvent(new dom.window.Event('input', { bubbles: true })); });
  if (surface === 'studio') await act(async () => {
    Object.defineProperty(textarea, 'files', { configurable: true, value: [new dom.window.File(['page'], 'retained-manga.png', { type: 'image/png' })] });
    textarea.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  let release;
  pending = new Promise(resolve => { release = resolve; });
  let refresh;
  await act(async () => { refresh = emit(user('alice')); });
  assert.equal(document.querySelector(selector), textarea, 'renewal must keep the existing form mounted');
  assert.ok(textarea.closest('[inert]'), 'protected form is inactive while verification is pending');
  fail = true;
  await act(async () => { release(); await refresh; });
  assert.equal(document.querySelector(selector), textarea);
  if (surface === 'request') assert.equal(textarea.value, 'Keep my review notes');
  else assert.ok(document.body.textContent.includes('retained-manga.png'), 'selected manga upload remains in the draft');
  assert.ok(textarea.closest('[inert]'));
  const retry = [...document.querySelectorAll('button')].find(button => button.textContent.includes('Sign in again'));
  assert.ok(retry, 'failed verification offers reauthentication without navigation');
  await act(async () => retry.click());
  assert.equal(loginCalls, 1);
  pending = null;
  fail = false;
  await act(async () => emit(user('alice')));
  assert.equal(document.querySelector(selector), textarea);
  assert.equal(textarea.closest('[inert]'), null);
  await act(async () => emit(user('bob')));
  assert.notEqual(document.querySelector(selector), textarea, 'another account gets a new form');
  assert.equal(document.querySelector(selector).value, '');
  await act(async () => emit(null));
  assert.equal(document.querySelector(selector), null);
});
