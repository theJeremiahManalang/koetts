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
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  new Function('exports', 'require', code)(exports, name => {
    if (name in mocks) return mocks[name];
    if (name.startsWith('.')) {
      const base = path.resolve(path.dirname(filename), name);
      const file = ['.tsx', '.ts'].map(ext => base + ext).find(fs.existsSync);
      if (file) return load(path.relative(__dirname, file), mocks, cache);
    }
    return require(name);
  });
  return exports;
}

test('pause failure keeps reason and last confirmed production state', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/admin/requests' });
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch'];
  const originals = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) {
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  }
  const status = {
    budget: { configured: true, paused: false, provider_allowance_micro: 25000000, provider_reserved_micro: 1000000, provider_used_micro: 2000000, infrastructure_reported_micro: 300000, infrastructure_reserved_micro: 50000 },
    chapter_quota: { utc_month: '2026-10', used: 2, limit: 5, remaining: 3, pages_per_chapter: 40 },
    reader_limits: { pending: 5, new_per_utc_day: 10 },
    artifact_collection: { active: false, epoch: 4 },
  };
  let currentStatus = status;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    return options.method === 'POST'
      ? { ok: false, status: 503, json: async () => ({ error: 'Pause could not be saved.' }) }
      : { ok: true, status: 200, json: async () => currentStatus };
  };
  const mocks = {
    '../identity/auth-provider': { useAuth: () => ({ user: { uid: 'admin' }, authorizationReady: true }) },
    '../identity/firebase-client': { getFirebaseAuth: () => ({ currentUser: { uid: 'admin', getIdToken: async () => 'verified-admin-token' } }) },
  };
  const Controls = load('../features/requests/production-controls.tsx', mocks).ProductionControls;
  const { createRoot } = require('react-dom/client');
  const root = createRoot(document.getElementById('root'));
  t.after(async () => {
    await act(async () => root.unmount());
    dom.window.close();
    for (const [key, descriptor] of Object.entries(originals)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor);
      else delete globalThis[key];
    }
  });

  await act(async () => root.render(React.createElement(Controls)));
  assert.match(document.body.textContent, /2\/5 chapters used/);
  assert.match(document.body.textContent, /Billing can be delayed/);
  const reason = document.querySelector('#production-pause-reason');
  const setter = Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, 'value').set;
  await act(async () => {
    setter.call(reason, 'Scheduled maintenance');
    reason.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
    reason.dispatchEvent(new dom.window.Event('change', { bubbles: true }));
  });
  await act(async () => [...document.querySelectorAll('button')].find(button => button.textContent === 'Pause production').click());
  const mutation = calls.find(([, options]) => options.method === 'POST');
  assert.deepEqual(JSON.parse(mutation[1].body), { paused: true, reason: 'Scheduled maintenance' });
  assert.equal(reason.value, 'Scheduled maintenance');
  assert.match(document.body.textContent, /Production: Active/);
  assert.match(document.body.textContent, /Pause could not be saved/);

  currentStatus = { ...status, budget: { configured: false, paused: true }, artifact_collection: { active: true, epoch: 5 } };
  await act(async () => document.querySelector('button').click());
  assert.match(document.body.textContent, /Production: Unconfigured/);
  assert.match(document.body.textContent, /Unavailable until the provider budget is configured/);
  assert.match(document.body.textContent, /Artifact cleanup is running \(epoch 5\)/);
  assert.equal([...document.querySelectorAll('button')].find(button => button.textContent === 'Resume production').disabled, true);
});
