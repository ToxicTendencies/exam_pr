/**
 * Runs every *.test.mjs file in this folder and reports one combined verdict.
 *
 *     cd tools/ui_tests
 *     npm install      # once, pulls jsdom
 *     npm test
 *
 * Each test file boots the real app shell (index.html + app.js) inside jsdom with
 * a synthetic question bank, so it needs no emulator and no browser download.
 * Exit code is non-zero when any file fails, which makes it usable from CI.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';

const here = path.dirname(url.fileURLToPath(import.meta.url));

const run = (file) =>
  new Promise((resolve) => {
    const child = spawn(process.execPath, [path.join(here, file)], { cwd: here });
    let out = '';
    child.stdout.on('data', (d) => (out += d));
    child.stderr.on('data', (d) => (out += d));
    child.on('close', (code) => resolve({ file, code, out }));
  });

const files = fs
  .readdirSync(here)
  .filter((f) => f.endsWith('.test.mjs'))
  .sort();

if (!files.length) {
  console.error('No *.test.mjs files found next to run_all.mjs');
  process.exit(1);
}

let failed = 0;
for (const file of files) {
  const { code, out } = await run(file);
  const summary = out.trim().split('\n').filter((l) => l.startsWith('PASS'));
  console.log(`${code === 0 ? 'PASS' : 'FAIL'}  ${file}${summary.length ? '  ' + summary[0] : ''}`);
  if (code !== 0) {
    failed++;
    console.log(
      out
        .trim()
        .split('\n')
        .filter((l) => l.includes('FAIL:'))
        .map((l) => '        ' + l.trim())
        .join('\n'),
    );
  }
}

console.log(failed ? `\n${failed} из ${files.length} файлов провалились` : `\nВсе ${files.length} файлов прошли`);
process.exit(failed ? 1 : 0);