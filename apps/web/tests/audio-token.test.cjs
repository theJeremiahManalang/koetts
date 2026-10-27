const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync(require.resolve('../features/requests/server/audio-token.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
}).outputText;
const api = {};
new Function('exports', 'require', code)(api, name => name === 'server-only' ? {} : require(name));
const key = Buffer.alloc(32, 42);
const principal = { project_id: 'project', uid: 'alice' };
const work = 'a'.repeat(32), publication = 'b'.repeat(32), now = 1700000000000;
test('audio token binds work, publication, reader and expiry', () => {
  const token = api.issueAudioToken(key, principal, work, publication, now);
  assert.deepEqual(api.verifyAudioToken(key, token, principal, now + 1000), { work, publication });
  assert.throws(() => api.verifyAudioToken(key, token, { ...principal, uid: 'bob' }, now + 1000));
  assert.throws(() => api.verifyAudioToken(key, token, principal, now + 300001));
  const parts = token.split('.');
  const changed = (parts[0][0] === 'A' ? 'B' : 'A') + parts[0].slice(1) + '.' + parts[1];
  assert.throws(() => api.verifyAudioToken(key, changed, principal, now + 1000));
});
