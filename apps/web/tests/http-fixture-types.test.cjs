const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

test('HTTP identity fixture typechecks against the actual admin request route', () => {
  const web = path.resolve(__dirname, '..');
  const harness = fs.readFileSync(path.resolve(web, '../../tests/verify_local_http.py'), 'utf8');
  const fixture = harness.match(/\(runtime \/ "apps\/web\/features\/identity\/firebase-admin\.ts"\)\.write_text\('''([\s\S]*?)'''\)/)?.[1];
  assert.ok(fixture, 'disposable HTTP identity fixture must be found');
  const config = ts.readConfigFile(path.join(web, 'tsconfig.json'), ts.sys.readFile);
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, web);
  const options = { ...parsed.options, noEmit: true, incremental: false };
  const host = ts.createCompilerHost(options);
  const originalRead = host.readFile.bind(host);
  const target = path.join(web, 'features/identity/firebase-admin.ts');
  host.readFile = file => path.resolve(file) === target ? fixture : originalRead(file);
  const program = ts.createProgram([path.join(web, 'app/api/admin/requests/route.ts')], options, host);
  const errors = ts.getPreEmitDiagnostics(program).filter(item => item.category === ts.DiagnosticCategory.Error);
  assert.equal(errors.length, 0, ts.formatDiagnosticsWithColorAndContext(errors, {
    getCanonicalFileName: file => file, getCurrentDirectory: () => web, getNewLine: () => '\n',
  }));
  const compiled = ts.transpileModule(fixture, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  new Function('exports', compiled)(exports);
  return assert.rejects(exports.getAdminAuth().getUsers([{ uid: 'fixture' }]), /profile lookup is disabled/);
});
