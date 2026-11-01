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

async function renderContext(t, { status, ok = true, hosted = true, showEmptyState = false, url } = {}) {
  const workId = 'a'.repeat(32);
  const dom = new JSDOM('<div id="root"></div>', { url: url || `http://localhost/?work=${workId}` });
  const originals = Object.fromEntries(['window', 'document', 'fetch', 'IS_REACT_ACT_ENVIRONMENT'].map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  globalThis.fetch = async () => ({ ok, json: async () => ({ work: ok ? [{ id: workId, title: 'Requested story', chapter: 3, status, requests: [{ requester_name: 'Reader', notes: 'Narrate clearly' }] }] : [] }) });
  const user = { uid: 'admin' };
  const verifiedFetch = (...args) => globalThis.fetch(...args);
  const mocks = {
    '../identity/auth-provider': { useAuth: () => ({ user, authorizationReady: true }) },
    '../identity/use-verified-fetch': { useVerifiedFetch: () => verifiedFetch },
    'next/navigation': { useSearchParams: () => new URLSearchParams(window.location.search) },
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
  await act(async () => root.render(React.createElement(StudioRequestContext, { hosted, showEmptyState, onWorkState: state => states.push(state) })));
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 0)); });
  return { dom, states, workId };
}

test('request context reports pending work as ineligible', async t => {
  const pending = await renderContext(t, { status: 'pending' });
  assert.match(pending.dom.window.document.body.textContent, /Approval status: pending/);
  assert.equal(pending.states.at(-1), null);
});

test('request context reports approved work as verified', async t => {
  const approved = await renderContext(t, { status: 'approved' });
  assert.match(approved.dom.window.document.body.textContent, /Selected chapter work: Requested story · Chapter 3/);
  assert.match(approved.dom.window.document.body.textContent, /Approval status: approved/);
  assert.deepEqual(approved.states.at(-1), { id: approved.workId, status: 'approved' });
});

test('request context reports published work as verified', async t => {
  const published = await renderContext(t, { status: 'published' });
  assert.deepEqual(published.states.at(-1), { id: published.workId, status: 'published' });
});

test('direct hosted entry explains that eligible work is required', async t => {
  const direct = await renderContext(t, { hosted: true, showEmptyState: true, url: 'http://localhost/' });
  assert.match(direct.dom.window.document.body.textContent, /No chapter work selected/);
  assert.match(direct.dom.window.document.body.textContent, /Choose an approved request/);
  assert.deepEqual(direct.states.at(-1), null);
});

test('direct local entry identifies standalone project creation', async t => {
  const direct = await renderContext(t, { hosted: false, showEmptyState: true, url: 'http://localhost/' });
  assert.match(direct.dom.window.document.body.textContent, /Standalone local project/);
  assert.match(direct.dom.window.document.body.textContent, /is optional/);
});

test('request verification failure clears eligibility and hosted create UI stays gated', async t => {
  const failed = await renderContext(t, { status: 'approved', ok: false });
  assert.equal(failed.states.at(-1), null);
  assert.ok(failed.dom.window.document.querySelector('[role="alert"]'));

  const studio = fs.readFileSync(path.resolve(__dirname, '../features/studio/studio-workspace.tsx'), 'utf8');
  assert.match(studio, /<StudioRequestContext hosted=\{hosted\} showEmptyState=\{!snapshot\} onWorkState=\{setHostedWorkState\}/);
  assert.match(studio, /disabled=\{\(hosted && !selectedHostedWork\)/);
  assert.doesNotMatch(studio, /approved:\s*true|is_approved/);
  const context = fs.readFileSync(path.resolve(__dirname, '../features/studio/studio-request-context.tsx'), 'utf8');
  assert.match(context, /\[workId, user\?\.uid/);
  assert.doesNotMatch(context, /window\.location\.search/);
  assert.match(studio, /currentHostedWork\(hostedWorkState, selectedWorkId\)/);
});
