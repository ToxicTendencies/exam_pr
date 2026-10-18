import fs from 'node:fs';
import path from 'node:path';
import url from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

/** Real app assets, resolved from this file so the suite works in any checkout. */
export const ASSETS = path.resolve(
  path.dirname(url.fileURLToPath(import.meta.url)),
  '..',
  '..',
  'app',
  'src',
  'main',
  'assets',
);

export function readAsset(name) {
  return fs.readFileSync(path.join(ASSETS, name), 'utf8');
}

export function compact(o) {
  return JSON.stringify(o);
}

/** Boot the real app shell in jsdom with an injected data catalog. */
export function boot({ catalog, explanations = {}, storage = {} } = {}) {
  let html = readAsset('index.html');
  const css = readAsset('styles.css');
  const app = readAsset('app.js');

  const shim = `<script>(function(){var s=${compact(storage)};Object.defineProperty(window,'localStorage',{value:{getItem:function(k){return Object.prototype.hasOwnProperty.call(s,k)?s[k]:null;},setItem:function(k,v){s[k]=String(v);},removeItem:function(k){delete s[k];},clear:function(){s={};},key:function(i){return Object.keys(s)[i]||null;},get length(){return Object.keys(s).length;}}});window.scrollTo=function(){};window.scroll=function(){};})();</script>`;

  const exScripts = Object.entries(explanations)
    .map(([id, payload]) =>
      `<script>window.EXAM_SUBJECT_EXPLANATIONS=window.EXAM_SUBJECT_EXPLANATIONS||{};` +
      `window.EXAM_SUBJECT_EXPLANATIONS[${JSON.stringify(id)}]=${compact(payload)};</script>`)
    .join('');

  html = html.replace('<link rel="stylesheet" href="styles.css">', `<style>${css}</style>`);
  html = html.replace(
    '<script src="subjects_core.js"></script>',
    shim + `<script>window.EXAM_SUBJECTS=${compact(catalog)};</script>${exScripts}`,
  );
  html = html.replace('<script src="app.js"></script>', `<script>${app}</script>`);

  const errors = [];
  const vc = new VirtualConsole();
  vc.on('jsdomError', (e) => errors.push('jsdomError: ' + (e.stack || e.message)));

  const dom = new JSDOM(html, {
    url: 'https://localhost/index.html',
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    virtualConsole: vc,
  });
  const w = dom.window;
  w.addEventListener('error', (e) => errors.push('error: ' + (e.error ? e.error.stack : e.message)));
  return { dom, window: w, document: w.document, errors };
}

export function q(sel, doc) { return doc.querySelector(sel); }
export function qa(sel, doc) { return Array.from(doc.querySelectorAll(sel)); }
export function txt(doc) {
  const clone = doc.body.cloneNode(true);
  clone.querySelectorAll('script').forEach((s) => s.remove());
  return clone.textContent.replace(/\s+/g, ' ').trim();
}

export function click(el, what = 'element') {
  if (!el) throw new Error('click: missing ' + what);
  const w = el.ownerDocument.defaultView;
  el.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true }));
}
export function change(el) {
  const w = el.ownerDocument.defaultView;
  el.dispatchEvent(new w.Event('change', { bubbles: true }));
}
export function input(el) {
  const w = el.ownerDocument.defaultView;
  el.dispatchEvent(new w.Event('input', { bubbles: true }));
}
