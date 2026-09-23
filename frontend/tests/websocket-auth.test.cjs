const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

for (const [file, connect, options] of [
  ['live.ts', 'connectLiveEvents', {
    cameraId: 'camera-1', onConnected() {}, onDisconnected() {},
    onError() {}, onRecognition() {},
  }],
  ['inference.ts', 'connectVideoSessionEvents', {
    sessionId: 'missing-video', onRecognition() {}, onStatus() {}, onError() {},
  }],
]) {
  test(`${file}: resource errors keep login, expired sessions clear login`, () => {
    let socket;
    const events = [];
    const exports = {};
    const source = readFileSync(path.join(__dirname, '../src/api', file), 'utf8');
    const compiled = ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS },
    }).outputText;
    vm.runInNewContext(compiled, {
      exports, Event, console,
      require: () => ({ buildApiUrl: value => value, buildWebSocketUrl: value => value }),
      window: { dispatchEvent: event => events.push(event.type) },
      WebSocket: class { constructor() { socket = this; } close() {} },
    });
    exports[connect](options);
    for (const code of [1000, 1006, 1008, 1013]) socket.onclose({ code });
    assert.deepEqual(events, []);
    socket.onclose({ code: 4401 });
    assert.deepEqual(events, ['auth-expired']);
  });
}
