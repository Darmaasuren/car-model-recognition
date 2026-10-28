const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

test('login sends UTF-8 Basic credentials only on the login request', async () => {
  const calls = [];
  const exports = {};
  const source = readFileSync(path.join(__dirname, '../src/api/auth.ts'), 'utf8');
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText, {
    exports, TextEncoder, btoa,
    require: () => ({
      buildApiUrl: value => value,
      apiFetch: async (...args) => {
        calls.push(args);
        return { ok: true, status: 200, json: async () => ({ username: 'admin' }) };
      },
    }),
  });
  await exports.login('admin', 'нууц:үг');
  assert.equal(calls[0][0], '/auth/login');
  const options = calls[0][1];
  assert.equal(options.method, 'POST');
  assert.equal(options.body, undefined);
  assert.equal(options.headers.Authorization, `Basic ${Buffer.from('admin:нууц:үг').toString('base64')}`);
  await exports.getMe();
  await exports.logout();
  assert.equal(calls[1][1], undefined);
  assert.equal(calls[2][1].headers, undefined);
});
