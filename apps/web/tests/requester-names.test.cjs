const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
function load(getUsers) {
  const exports = {};
  const source = ts.transpileModule(fs.readFileSync(require.resolve('../features/requests/server/requester-names.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  }).outputText;
  new Function('exports', 'require', source)(exports, name => name === 'server-only' ? {} : { getAdminAuth: () => ({ getUsers }) });
  return exports.withRequesterNames;
}
test('admin names are batched, project-scoped, and never expose profile emails', async () => {
  const calls = [];
  const work = [{ id: 'work', requests: Array.from({ length: 101 }, (_, index) => ({ reader: JSON.stringify(['project', `uid-${index}`]), notes: 'original' })) }];
  work[0].requests.push({ reader: JSON.stringify(['other-project', 'private']), notes: 'other' });
  const resolve = load(async batch => {
    calls.push(batch);
    return { users: batch.map(({ uid }) => ({ uid, displayName: `Name ${uid}`, email: 'private@example.test' })), notFound: [] };
  });
  const result = await resolve(work, 'project');
  assert.deepEqual(calls.map(batch => batch.length), [100, 1]);
  assert.equal(result[0].requests[0].requester_name, 'Name uid-0');
  assert.equal(result[0].requests.at(-1).requester_name, 'Name unavailable');
  assert.equal(result[0].requests[0].notes, 'original');
  assert.equal(JSON.stringify(result).includes('private@example.test'), false);
  assert.equal(work[0].requests[0].requester_name, undefined);
});
test('missing/deleted profiles and profile outages retain the complete request queue', async () => {
  const work = [{ requests: ['named', 'deleted', 'unnamed'].map(uid => ({ reader: JSON.stringify(['project', uid]), notes: uid })) }];
  const resolve = load(async () => ({ users: [{ uid: 'named', displayName: ' Reader ' }, { uid: 'unnamed' }], notFound: [{ uid: 'deleted' }] }));
  assert.deepEqual((await resolve(work, 'project'))[0].requests.map(item => item.requester_name), ['Reader', 'Deleted account', 'Unnamed reader']);
  const failed = await load(async () => { throw new Error('offline'); })(work, 'project');
  assert.equal(failed[0].requests.length, 3);
  assert.ok(failed[0].requests.every(item => item.requester_name === 'Name unavailable'));
});
