import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('..', import.meta.url));

test('native/loaded_data.h is exactly what gen-native.mjs produces from the JS modules', () => {
  const r = spawnSync(process.execPath, ['gen-native.mjs', '--check'], { cwd: ROOT, encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr + r.stdout);
});

test('loaded.c is freestanding: no libc headers, no floating point, no allocation, no writable globals', () => {
  const src = readFileSync(ROOT + 'native/loaded.c', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');
  const includes = [...src.matchAll(/#include\s+(\S+)/g)].map(m => m[1]);
  assert.deepEqual(includes, ['"loaded.h"', '"loaded_data.h"']);
  assert.doesNotMatch(src, /\b(float|double|malloc|calloc|free|memset|memcpy|printf|sqrt|sin|cos)\b/);
  assert.doesNotMatch(src, /\b\d+\.\d+f?\b/, 'no floating point literal');
  // file-scope variables must all be const; a non-const static or global would land in .data/.bss
  for (const line of src.split('\n')) {
    if (/^(static\s+)?(?!const)[A-Za-z_][\w\s\*]*\s+\w+(\[[^\]]*\])*\s*(=\s*[^;(]*)?;\s*$/.test(line) && !/^\s/.test(line) && !/^(typedef|enum|struct|extern)/.test(line))
      assert.fail('writable global: ' + line);
  }
});

test('the generated header carries the view plan the renderer uses', () => {
  const h = readFileSync(ROOT + 'native/loaded_data.h', 'utf8');
  assert.match(h, /#define LD_VIEW_RECTS \{ \{ 0, 0, 720, 480 \}, \{ 0, 0, 720, 44 \}, \{ 0, 436, 720, 44 \}, \{ 612, 380, 108, 48 \}, \{ 0, 376, 128, 56 \} \}/);
  assert.match(h, /#define LD_FILMS 21/);
});
