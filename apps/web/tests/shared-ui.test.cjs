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
  };
  const Page = load('../features/requests/request-page.tsx', mocks).default;
  const { createRoot } = require('react-dom/client');
  const root = createRoot(document.getElementById('root'));
  t.after(async () => { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; } });
  await act(async () => root.render(React.createElement(Page)));
  await act(async () => document.querySelector('form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })));
  assert.equal(calls[0][0], '/api/shared/requests');
  assert.deepEqual(JSON.parse(calls[0][1].body), { title: 'Manga', chapter: '1', notes: '' });
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
    return { ok: true, json: async () => options.method === 'DELETE' ? { deleted: true } : { requests: [{ id: 'a'.repeat(32), work_id: 'b'.repeat(32), title: 'Shared Manga', chapter: 3, notes: '', status: 'published', created_at: '2026-10-20 00:00:00' }] } };
  };
  const mocks = {
    'next/link': props => React.createElement('a', props),
    '../library/library-ui': { LibraryHeader: () => null },
    '../identity/require-sign-in': { RequireSignIn: ({ children }) => children },
    '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'reader' }, authorizationReady: true }) },
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
  assert.match(document.body.textContent, /No requests yet/);
});
