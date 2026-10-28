const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const ts = require('typescript');

// Exercise the component's request lifecycle using a minimal hook renderer.
function renderPage(createVideoSession) {
  const source = readFileSync(path.join(__dirname, '../src/pages/fileRecognition/FileRecognitionPage.tsx'), 'utf8');
  const slots = [];
  let cursor = 0;
  const stopped = [];
  const react = {
    useState(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = initial;
      return [slots[index], value => { slots[index] = typeof value === 'function' ? value(slots[index]) : value; }];
    },
    useRef(initial) {
      const index = cursor++;
      if (!(index in slots)) slots[index] = { current: initial };
      return slots[index];
    },
    useEffect() {},
    useMemo(fn) { return fn(); },
  };
  const jsx = (type, props) => ({ type, props });
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX },
  }).outputText, {
    exports,
    require(name) {
      if (name === 'react') return react;
      if (name === 'react/jsx-runtime') return { jsx, jsxs: jsx };
      if (name.endsWith('/api/inference')) return {
        createVideoSession,
        stopVideoSession: async id => { stopped.push(id); },
        getVideoSessionStreamUrl: id => id,
      };
      return { FileUploader: 'Uploader', MediaPreview: 'Preview', ResultList: 'Results' };
    },
  });
  function find(node, predicate) {
    if (!node || typeof node !== 'object') return null;
    if (predicate(node)) return node;
    const children = node.props?.children;
    for (const child of Array.isArray(children) ? children : [children]) {
      const result = find(child, predicate);
      if (result) return result;
    }
    return null;
  }
  return {
    stopped,
    render() {
      cursor = 0;
      const tree = exports.FileRecognitionPage();
      return {
        uploader: find(tree, node => node.type === 'Uploader').props,
        clear: find(tree, node => node.type === 'button' && node.props.className === 'file-panel__clear')?.props.onClick,
      };
    },
  };
}

test('clear releases loading state and deletes a late-created video session', async () => {
  let resolveUpload;
  const page = renderPage(() => new Promise(resolve => { resolveUpload = resolve; }));
  page.render().uploader.onFileChange({ type: 'video/mp4', name: 'video.mp4' });
  const pending = page.render().uploader.onRecognize();
  assert.equal(page.render().uploader.disabled, true);
  page.render().clear();
  assert.equal(page.render().uploader.disabled, false);
  resolveUpload({ sessionId: 'late-session' });
  await pending;
  assert.deepEqual(page.stopped, ['late-session']);
  assert.equal(page.render().uploader.selectedFile, null);
});
