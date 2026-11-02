const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');

const compiled = ts.transpileModule(fs.readFileSync(require.resolve('../proxy.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function load() {
  const api = {};
  new Function('exports', 'require', compiled)(api, name => {
    if (name === 'next/server') return {
      NextResponse: {
        next: () => ({ kind: 'next' }),
        rewrite: url => ({ kind: 'rewrite', pathname: new URL(url).pathname }),
      },
    };
    return require(name);
  });
  return api;
}

test('maintenance rewrite is explicit and bypasses APIs, assets, and its destination', t => {
  const previous = process.env.MANGA_MAINTENANCE_MODE;
  t.after(() => {
    if (previous === undefined) delete process.env.MANGA_MAINTENANCE_MODE;
    else process.env.MANGA_MAINTENANCE_MODE = previous;
  });
  const proxy = load().proxy;
  const request = pathname => ({ nextUrl: { pathname }, url: `https://studio.example${pathname}` });

  delete process.env.MANGA_MAINTENANCE_MODE;
  assert.deepEqual(proxy(request('/studio')), { kind: 'next' });
  process.env.MANGA_MAINTENANCE_MODE = '1';
  assert.deepEqual(proxy(request('/studio')), { kind: 'rewrite', pathname: '/maintenance' });
  for (const path of ['/api/production', '/_next/static/app.js', '/favicon.ico', '/brand.svg', '/maintenance']) {
    assert.deepEqual(proxy(request(path)), { kind: 'next' }, path);
  }
});
