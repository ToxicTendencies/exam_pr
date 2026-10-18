import { boot, q, qa, txt, click as clickEl, input } from './harness.mjs';

const txtEl = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : '<none>');
let pass = 0;
const fails = [];
function ok(name, cond, extra = '') {
  if (cond) pass++;
  else fails.push(`${name}${extra ? ' :: ' + extra : ''}`);
}
function eq(name, a, b) { ok(name, a === b, `got ${JSON.stringify(a)} want ${JSON.stringify(b)}`); }

/* ---------- synthetic canonical bank ---------- */
const questions = [
  { id: 1, type: 'single_choice', question: 'Первый вопрос', options: [
    { id: 1, text: 'A', correct: false }, { id: 2, text: 'B', correct: true },
    { id: 3, text: 'C', correct: false }, { id: 4, text: 'D', correct: false }],
    correct_option_ids: [2], ticket_number: 1, ticket_question_number: 1, topic: 'Тема 1', subtopic: 'Подтема 1', difficulty: 'easy', skill: 'воспроизведение', tags: ['альфа'] },
  { id: 2, type: 'multiple_choice', question: 'Второй вопрос', options: [
    { id: 1, text: 'A', correct: true }, { id: 2, text: 'B', correct: false }, { id: 3, text: 'C', correct: true }],
    correct_option_ids: [1, 3], ticket_number: 1, ticket_question_number: 2, topic: 'Тема 1' },
  { id: 3, type: 'open_text', question: 'Введите термин', accepted_answers: ['Митаза', 'митаза '], ticket_number: 2, ticket_question_number: 1, topic: 'Тема 2' },
  { id: 4, type: 'matching', question: 'Установите соответствие', ticket_number: 2, ticket_question_number: 2,
    left_items: [{ id: 1, text: 'Л1' }, { id: 2, text: 'Л2' }],
    right_items: [{ id: 1, text: 'П1' }, { id: 2, text: 'П2' }, { id: 3, text: 'П3' }],
    correct_mapping: [{ left_id: 1, right_id: 2 }, { left_id: 2, right_id: 3 }] },
  { id: 5, type: 'ticket', question: 'Билет 1. Тема для запоминания', ticket_number: 1, topic: 'Тема 1' },
  { id: 6, type: 'single_choice', question: 'Шестой вопрос', options: [
    { id: 1, text: 'да', correct: true }, { id: 2, text: 'нет', correct: false }], correct_option_ids: [1] },
];

const explanations = {
  subject_id: 'syn', question_count: 6, explanation_count: 2, complete: false,
  by_id: {
    1: { topic_markdown: '**Разбор** темы', answers_markdown: 'Разбор вариантов', correct_answer_markdown: '**B**' },
    5: { ticket_answer_markdown: 'Ответ на билет', ticket_answer_text: 'Ответ на билет' },
  },
};

const meta = { id: 'syn', title: 'Синтетика', language: 'ru', order: 10, item_count: 6, question_count: 6,
  ticket_count: 1, test_question_count: 5, ticket_group_count: 2, explanation_count: 2, explanations_script: '', canonical_sha256: 'x' };

const catalog = { schema_version: '1.1-multi-subject-runtime', subjects: [meta], by_id: { syn: { subject: meta, questions } } };

const { window, document, errors } = boot({ catalog, explanations: { syn: explanations } });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const steps = [];
function step(name, fn) { steps.push([name, fn]); }
async function astep(name, fn) { steps.push([name, fn]); }

const click = (sel) => clickEl(typeof sel === 'string' ? q(sel, document) : sel, sel);
const byId = (id) => clickEl(qa('.option', document).find((b) => b.dataset.id === String(id)), 'option ' + id);

/* 1. startup */
step('startup', () => {
  ok('startup: no js errors', errors.length === 0, errors.join(' | '));
  ok('startup: subject title shown', /Синтетика/.test(txt(document)));
  eq('startup: header count', txtEl(q('.app-sub', document)), '6 заданий · 1 билет');
  ok('startup: bottom nav', qa('.nav-btn', document).length === 4);
});

/* 2. ordered walkthrough */
step('ordered', () => {
  click('[data-action="start-mode"][data-mode="ordered"]');
  eq('ordered: q1 counter', txtEl(q('.qcounter', document)), '1.1');
  ok('ordered: radio indicator', !!q('.select-indicator.radio', document));
  ok('ordered: context label', /Билет №1 · вопрос 1/.test(txtEl(q('.question-context', document))));

  byId(1); click('[data-action="submit"]');
  ok('wrong: result.bad', !!q('.result.bad', document));
  ok('wrong: option.wrong', !!q('.option.wrong', document));
  ok('wrong: explanation details', !!q('.details', document));
  ok('wrong: user answer block', /1\. A/.test(txtEl(q('.user-answer', document))), txtEl(q('.result', document)));
  click('[data-action="next"]');

  eq('ordered: q2 counter', txtEl(q('.qcounter', document)), '1.2');
  ok('ordered: checkbox indicator', !!q('.select-indicator.checkbox', document));
  byId(1); byId(3); click('[data-action="submit"]');
  ok('multiple: result.good', !!q('.result.good', document), txtEl(q('.result', document)));
  click('[data-action="next"]');

  eq('ordered: q3 counter', txtEl(q('.qcounter', document)), '2.1');
  ok('open_text: input rendered', !!q('#text-answer', document));
  q('#text-answer', document).value = '  МИТАЗА  ';
  click('[data-action="submit"]');
  ok('open_text: normalization accepts', !!q('.result.good', document), txtEl(q('.result', document)));
  click('[data-action="next"]');

  eq('ordered: q4 counter', txtEl(q('.qcounter', document)), '2.2');
  clickEl(qa('.match-picker', document)[0]);
  clickEl(qa('.match-choices .match-choice', document).find((b) => b.dataset.right === '2'));
  clickEl(qa('.match-picker', document)[1]);
  clickEl(qa('.match-choices .match-choice', document).find((b) => b.dataset.right === '3'));
  ok('matching: progress', /2 \/ 2/.test(txtEl(q('.match-progress', document))));
  click('[data-action="submit"]');
  ok('matching: correct', !!q('.result.good', document), txtEl(q('.result', document)));
  click('[data-action="next"]');

  eq('ordered: q5 counter (ticket)', txtEl(q('.qcounter', document)), 'Билет 1');
  ok('ticket: no options', qa('.option', document).length === 0);
  ok('ticket: reveal button', /Показать ответ/.test(txt(document)));
  click('[data-action="ticket-reveal"]');
  ok('ticket: answer rendered', /Ответ на билет/.test(txtEl(q('.ticket-answer', document))));
  click('[data-action="ticket-repeat"]');

  eq('ordered: q6 counter', txtEl(q('.qcounter', document)), '№6 / 6');
  byId(1); click('[data-action="submit"]');
  ok('ordered: q6 correct', !!q('.result.good', document));
  click('[data-action="next"]');
});

step('ordered-tail', () => {
  ok('ordered: keeps drilling error queue', !!q('.question-text', document), txtEl(document.body).slice(0, 120));
  const counter = txtEl(q('.qcounter', document));
  ok('ordered: error queue resumed at q1', counter === '1.1', counter);
});

/* 3. progress tab */
step('progress', () => {
  click('[data-action="tab"][data-tab="progress"]');
  ok('progress: stats grid', !!q('.stats-grid', document));
  ok('progress: test stats card', /Попытки тестов/.test(txt(document)));
});

/* 4. errors mode */
step('errors-mode', () => {
  click('[data-action="tab"][data-tab="learn"]');
  click('[data-action="start-mode"][data-mode="errors"]');
  ok('errors: opens queued question', !!q('.question-text', document), txtEl(document.body).slice(0, 200));
});

/* 5. test flow */
step('test', () => {
  click('[data-action="tab"][data-tab="test"]');
  ok('test: ticket select groups', qa('[data-action="set-test-ticket"] option', document).length === 3);
  ok('test: default feedback = off', !!q('[data-action="set-feedback"][data-value="0"].selected', document));
  click('[data-action="set-feedback"][data-value="1"]');
  click('[data-action="start-test-final"]');
  ok('test: question shown', !!q('.qcounter', document));

  // Question order inside a test is randomised, so answer whatever type came up.
  const answerCurrent = () => {
    const type = txtEl(q('.question-type', document));
    if (/Билет/.test(type)) return click('[data-action="ticket-reveal"]');
    if (/Соответствие|Порядок/.test(type)) {
      click('[data-action="match-toggle"][data-left="1"]');
      click('[data-action="match-choose"][data-left="1"][data-right="2"]');
      click('[data-action="match-toggle"][data-left="2"]');
      click('[data-action="match-choose"][data-left="2"][data-right="3"]');
      return undefined;
    }
    const box = q('#text-answer', document) || q('#test-text', document);
    if (box) { box.value = 'Митаза'; input(box); return undefined; }
    return clickEl(qa('.option', document)[0], 'test option');
  };

  answerCurrent();
  click('[data-action="test-answer"]');
  ok('test: immediate feedback', !!q('.result', document), txtEl(document.body).slice(0, 150));
  click('[data-action="test-next"]');
  ok('test: advanced', /Ответить/.test(txt(document)));
  click('[data-action="test-home"]');
  ok('test: home restored', /Количество вопросов/.test(txt(document)));
});

/* 6. bank */
step('bank', () => {
  click('[data-action="tab"][data-tab="bank"]');
  eq('bank: renders all items', qa('.bank-item', document).length, 6);
  const s = q('#bank-search', document);
  s.value = 'Первый'; input(s);
});

step('bank-search-async', async () => {
  await sleep(250);
  eq('bank: search narrows', qa('.bank-item', document).length, 1);
});

step('bank-search-clear', async () => {
  const s = q('#bank-search', document);
  ok('bank: search input preserved after rerender', !!s);
  s.value = 'митаза'; input(s);
  await sleep(250);
  ok('bank: search matches question text', qa('.bank-item', document).length === 1);
});

/* 7. settings + theme + colors */
step('settings', () => {
  click('[data-action="tab"][data-tab="learn"]');
  click('[data-action="open-settings"]');
  ok('settings: screen', /Настройки/.test(txt(document)));
  click('[data-action="set-appearance"][data-value="dark"]');
  eq('theme: dark applied', document.documentElement.getAttribute('data-theme'), 'dark');
  click('[data-action="color-open"][data-color-key="accent"]');
  ok('color editor opens', !!q('.color-editor-modal', document));
  const sl = q('[data-color-slider="r"]', document);
  sl.value = '12'; input(sl);
  ok('color editor: hex preview', /^#0c/i.test(q('[data-color-editor-hex]', document).value), q('[data-color-editor-hex]', document).value);
  click('[data-action="color-close"]');
  ok('color editor closed', !q('.color-editor-modal', document));
});

/* 8. shuffle answers */
astep('shuffle', async () => {
  click('[data-action="set-answer-shuffle"][data-value="1"]');
  click('[data-action="settings-back"]');
  click('[data-action="tab"][data-tab="bank"]');
  const s = q('#bank-search', document);
  s.value = ''; input(s);
  await sleep(250);
  eq('shuffle: search cleared', qa('.bank-item', document).length, 6);
  clickEl(qa('.bank-item', document)[0], 'bank item 0');
  const nums = qa('.option .option-num', document).map((n) => n.textContent);
  ok('shuffle: positional numbering', nums.join(',') === '1,2,3,4', nums.join(','));
  // The displayed order is random, but correctness must follow the option text,
  // not the position it happens to occupy after shuffling.
  const correct = qa('.option', document).find((o) => /B/.test(o.textContent));
  ok('shuffle: correct option still findable', !!correct, qa('.option', document).map((o) => o.textContent).join('|'));
  clickEl(correct, 'shuffled correct option');
  click('[data-action="submit"]');
  ok('shuffle: correct by text, not by position', !!q('.result.good', document), txtEl(q('.result', document)));
});

/* 9. back handling */
step('back', () => {
  ok('back: consumed inside question', window.examTrainingHandleBack() === true);
});

for (const [name, fn] of steps) {
  try { await fn(); } catch (e) { fails.push(`${name} THREW :: ${e.message}`); }
}

console.log(`PASS ${pass}  FAIL ${fails.length}`);
for (const f of fails) console.log('  FAIL: ' + f);
process.exit(fails.length ? 1 : 0);
