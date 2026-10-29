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

async function renderContext(t, { status, ok = true }) {
  const workId = 'a'.repeat(32);
  const dom = new JSDOM('<div id="root"></div>', { url: `http://localhost/?work=${workId}` });
  const originals = Object.fromEntries(['window', 'document', 'fetch', 'IS_REACT_ACT_ENVIRONMENT'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  globalThis.fetch = async () => ({ ok, json: async () => ({ work: ok ? [{ id: workId, title: 'Requested story', chapter: 3, status, requests: [{ requester_name: 'Reader', notes: 'Narrate clearly' }] }] : [] }) });
  const user = { uid: 'admin' };
  const verifiedFetch = (...args) => globalThis.fetch(...args);
  const mocks = {
    '../identity/auth-provider': { useAuth: () => ({ user, authorizationReady: true }) },
    '../identity/use-verified-fetch': { useVerifiedFetch: () => verifiedFetch },
  };
  const { StudioRequestContext } = load('../features/studio/studio-request-context.tsx', mocks);
  const states = [];
  const { createRoot } = require('react-dom/client');
  const root = createRoot(document.getElementById('root'));
  t.after(async () => {
    await act(async () => root.unmount());
    dom.window.close();
    for (const [key, descriptor] of Object.entries(originals)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
  });
  await act(async () => root.render(React.createElement(StudioRequestContext, { onWorkState: state => states.push(state) })));
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
  return { dom, states, workId };
}

test('request context reports pending work as ineligible', async t => {
  const pending = await renderContext(t, { status: 'pending' });
  assert.match(pending.dom.window.document.body.textContent, /Status: pending/);
  assert.equal(pending.states.at(-1), null);
});

test('request context reports approved work as verified', async t => {
  const approved = await renderContext(t, { status: 'approved' });
  assert.match(approved.dom.window.document.body.textContent, /Status: approved/);
  assert.deepEqual(approved.states.at(-1), { id: approved.workId, status: 'approved' });
});

test('request context reports published work as verified', async t => {
  const published = await renderContext(t, { status: 'published' });
  assert.deepEqual(published.states.at(-1), { id: published.workId, status: 'published' });
});

test('request verification failure clears eligibility and hosted create UI stays gated', async t => {
  const failed = await renderContext(t, { status: 'approved', ok: false });
  assert.equal(failed.states.at(-1), null);
  assert.ok(failed.dom.window.document.querySelector('[role="alert"]'));

  const studio = fs.readFileSync(path.resolve(__dirname, '../features/studio/studio-workspace.tsx'), 'utf8');
  assert.match(studio, /<StudioRequestContext onWorkState=\{setHostedWorkState\}/);
  assert.match(studio, /disabled=\{\(hosted && !hostedWorkState\)/);
  assert.doesNotMatch(studio, /approved:\s*true|is_approved/);
});
