const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync(require.resolve('../features/requests/server/audio-file.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true },
}).outputText;
const api = {};
new Function('exports', 'require', code)(api, name => name === 'server-only' ? {} : require(name));
test('published audio serves full and byte-range responses from artifact storage', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'shared-audio-test-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const artifacts = path.join(root, 'shared-artifacts'); fs.mkdirSync(artifacts);
  const audio = path.join(artifacts, 'a'.repeat(64)); fs.writeFileSync(audio, 'abcdefghij');
  const request = range => new Request('http://localhost/audio', { headers: range ? { range } : {} });
  let response = await api.serveAudioFile(root, audio, request('bytes=2-5'));
  assert.equal(response.status, 206); assert.equal(response.headers.get('content-range'), 'bytes 2-5/10'); assert.equal(await response.text(), 'cdef');
  response = await api.serveAudioFile(root, audio, request('bytes=-3'));
  assert.equal(await response.text(), 'hij');
  response = await api.serveAudioFile(root, audio, request('bytes=99-'));
  assert.equal(response.status, 416); assert.equal(response.headers.get('content-range'), 'bytes */10');
  response = await api.serveAudioFile(root, audio, request());
  assert.equal(response.status, 200); assert.equal(await response.text(), 'abcdefghij');
  await assert.rejects(api.serveAudioFile(root, path.join(root, 'private.wav'), request()));
});
