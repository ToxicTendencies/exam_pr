import { boot, q, qa, txt, click as clickEl, input } from './harness.mjs';

const txtEl = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : '<none>');
let pass = 0; const fails = [];
const ok = (n, c, e = '') => (c ? pass++ : fails.push(`${n}${e ? ' :: ' + e : ''}`));
const eq = (n, a, b) => ok(n, a === b, `got ${JSON.stringify(a)} want ${JSON.stringify(b)}`);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* 420 questions: enough to force the bank to paginate */
const questions = [];
for (let i = 1; i <= 420; i++) {
  questions.push({
    id: i, type: 'single_choice', question: `Вопрос номер ${i}`,
    options: [{ id: 1, text: `да ${i}`, correct: true }, { id: 2, text: 'нет', correct: false }],
    correct_option_ids: [1], ticket_number: Math.ceil(i / 20), ticket_question_number: (i % 20) + 1,
  });
}
questions[417] = { id: 418, type: 'open_text', question: 'Назовите фермент', accepted_answers: ['Уникарин'], case_sensitive: false, ticket_number: 21 };
questions[418] = { id: 419, type: 'matching', question: 'Соедините термины', ticket_number: 21,
  left_items: [{ id: 1, text: 'Гемоглобин' }, { id: 2, text: 'Миоглобин' }],
  right_items: [{ id: 1, text: 'Кислород' }, { id: 2, text: 'Углекислый газ' }],
  correct_mapping: [{ left_id: 1, right_id: 1 }, { left_id: 2, right_id: 2 }] };
questions[419] = { id: 420, type: 'ticket', question: 'Билет 21 для запоминания', ticket_number: 21 };

const index = {
  by_id: { 1: 'c0', 418: 'c1', 420: 'c1' },
  chunks: { c0: 'subject_data/big_ex_000.js', c1: 'subject_data/big_ex_001.js' },
  chunk_count: 2,
};
const meta = { id: 'big', title: 'Большой банк', language: 'ru', order: 10, item_count: 420, question_count: 420,
  ticket_count: 1, test_question_count: 419, ticket_group_count: 21, explanation_count: 3,
  explanations_script: '', explanations_index: index, canonical_sha256: 'x' };

const catalog = { schema_version: '1.1-multi-subject-runtime', subjects: [meta], by_id: { big: { subject: meta, questions } } };
const { window, document, errors } = boot({ catalog });
const click = (s) => clickEl(typeof s === 'string' ? q(s, document) : s, s);
const back = () => click('[data-action="question-back"]');
const setQuery = async (v) => { const s = q('#bank-search', document); s.value = v; input(s); await sleep(250); };
const openBank = () => click('[data-action="tab"][data-tab="bank"]');
const openBankItem = (id) => clickEl(qa('.bank-item', document).find((b) => b.dataset.id === String(id)), 'bank item ' + id);

/* capture the chunk <script> the app injects instead of letting jsdom fetch it */
const injected = [];
document.head.appendChild = (node) => { injected.push(node); return node; };

const steps = [];
const step = (n, f) => steps.push([n, f]);

step('startup', () => {
  ok('startup: no page errors', errors.length === 0, errors.join(' | '));
});

step('bank-pagination', async () => {
  openBank();
  eq('bank: first page capped at 150', qa('.bank-item', document).length, 150);
  const more = q('[data-action="bank-more"]', document);
  ok('bank: show-more button present', !!more, txtEl(document.body).slice(0, 120));
  ok('bank: show-more reports remaining', /Показать ещё · 270 из 270/.test(txtEl(more)), txtEl(more));
  click(more);
  eq('bank: next page reaches the end', qa('.bank-item', document).length, 420);
  ok('bank: no show-more at the end', !q('[data-action="bank-more"]', document));
});

step('bank-search', async () => {
  await setQuery('Вопрос номер 7');
  ok('bank: search narrows', qa('.bank-item', document).length < 20, String(qa('.bank-item', document).length));
  await setQuery('');
  eq('bank: clearing search restores full page', qa('.bank-item', document).length, 150);
});

step('search-covers-accepted-answers', async () => {
  await setQuery('уникарин');
  eq('search: finds question by accepted answer', qa('.bank-item', document).length, 1);
  ok('search: found the open_text item', /Назовите фермент/.test(txtEl(q('.bank-item', document))));
});

step('search-covers-matching-items', async () => {
  await setQuery('миоглобин');
  eq('search: finds question by matching item', qa('.bank-item', document).length, 1);
  ok('search: found the matching item', /Соедините термины/.test(txtEl(q('.bank-item', document))));
});

step('no-chunk-loaded-yet', async () => {
  ok('lazy: nothing injected while browsing the bank', injected.length === 0, String(injected.length));
});

step('explanation-requested-only-when-needed', async () => {
  await setQuery('');
  openBankItem(1);
  ok('question opened', /Вопрос номер 1/.test(txt(document)));
  await sleep(60);
  eq('browsing a question injects nothing', injected.length, 0);
  clickEl(qa('.option', document).find((o) => o.dataset.id === '1'), 'correct option');
  click('[data-action="submit"]');
  ok('result shown', !!q('.result.good', document), txtEl(q('.result', document)));
  await sleep(60);
  ok('explanation requested after answering', /Разбор загружается/.test(txt(document)), txtEl(document.body).slice(0, 200));
  eq('exactly one chunk script injected', injected.length, 1);
  ok('chunk path taken from index', /subject_data\/big_ex_000\.js$/.test(injected[0].src), injected[0].src);
  ok('explanation still hidden while pending', !/Разбор темы/.test(txt(document)));
});

step('chunk-onload-merges', async () => {
  window.EXAM_EXPLANATION_CHUNKS = window.EXAM_EXPLANATION_CHUNKS || {};
  window.EXAM_EXPLANATION_CHUNKS.big = { c0: { 1: { topic_markdown: '**Тема** разбор', answers_markdown: 'Разбор вариантов' } } };
  injected[0].onload();
  await sleep(30);
  ok('explanation rendered after load', /Разбор темы/.test(txt(document)), txtEl(q('.result', document)));
  ok('markdown converted', /<strong>Тема<\/strong>/.test(q('.details-body', document).innerHTML));
});

step('chunk-loaded-once', async () => {
  back();
  openBankItem(2);
  clickEl(qa('.option', document).find((o) => o.dataset.id === '1'), 'correct option');
  click('[data-action="submit"]');
  ok('item without explanations has no placeholder', !/Разбор/.test(txt(document)), txtEl(q('.result', document)));
  back();
  openBankItem(1);
  clickEl(qa('.option', document).find((o) => o.dataset.id === '1'), 'correct option');
  click('[data-action="submit"]');
  await sleep(30);
  ok('cached chunk is reused, nothing re-injected', injected.length === 1, String(injected.length));
  ok('cached explanation shown instantly', /Разбор темы/.test(txt(document)), txtEl(q('.result', document)));
});

step('ticket-answer-loads-lazily', async () => {
  back();
  await setQuery('Билет 21 для запоминания');
  openBankItem(420);
  ok('ticket opened', /Показать ответ/.test(txt(document)), txtEl(document.body).slice(0, 150));
  click('[data-action="ticket-reveal"]');
  ok('ticket answer pending', /Ответ загружается/.test(txt(document)), txtEl(document.body).slice(0, 200));
  ok('second chunk injected', injected.length, 2);
  ok('ticket chunk path from index', /subject_data\/big_ex_001\.js$/.test(injected[1].src), injected[1].src);
  window.EXAM_EXPLANATION_CHUNKS.big.c1 = {
    420: { ticket_answer_markdown: 'Ответ **билета** 21' },
    418: { topic_markdown: 'Разбор термина', correct_answer_markdown: 'Уникарин' },
  };
  injected[1].onload();
  await sleep(30);
  ok('ticket answer shown after load', /Ответ билета 21/.test(txt(document)), txtEl(q('.ticket-answer', document)));
  ok('ticket markdown converted', /<strong>билета<\/strong>/.test(q('.ticket-answer-body', document).innerHTML));
});

step('open-text-item-explanation', async () => {
  back();
  await setQuery('Назовите фермент');
  openBankItem(418);
  const inp = q('#text-answer', document);
  ok('text input present', !!inp);
  inp.value = 'уникарин';
  click('[data-action="submit"]');
  ok('case-insensitive accepted answer marked correct', !!q('.result.good', document), txtEl(q('.result', document)));
  ok('no extra chunk needed, same one already loaded', injected.length === 2, String(injected.length));
  ok('explanation came from the loaded chunk', /Разбор термина/.test(txt(document)), txtEl(q('.result', document)));
});

for (const [name, fn] of steps) {
  try { await fn(); } catch (e) { fails.push(`${name} THREW :: ${e.message}`); }
}
console.log(`PASS ${pass}  FAIL ${fails.length}`);
for (const f of fails) console.log('  FAIL: ' + f);
process.exit(fails.length ? 1 : 0);