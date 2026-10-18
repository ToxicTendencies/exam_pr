import { boot, q, qa, txt, click as clickEl, input } from './harness.mjs';

const txtEl = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : '<none>');
let pass = 0; const fails = [];
const ok = (n, c, e = '') => (c ? pass++ : fails.push(`${n}${e ? ' :: ' + e : ''}`));
const eq = (n, a, b) => ok(n, a === b, `got ${JSON.stringify(a)} want ${JSON.stringify(b)}`);

function mkSubject(id, title, order, questions, extra = {}) {
  const tickets = questions.filter((x) => x.type === 'ticket').length;
  const meta = { id, title, language: 'ru', order, item_count: questions.length, question_count: questions.length,
    ticket_count: tickets, test_question_count: questions.length - tickets, ticket_group_count: 0,
    explanation_count: 0, explanations_script: '', canonical_sha256: 'x', ...extra };
  return { meta, entry: { subject: meta, questions } };
}

const a = mkSubject('alpha', 'Альфа', 10, [
  { id: 1, type: 'single_choice', question: 'A1', options: [{ id: 1, text: 'x', correct: true }, { id: 2, text: 'y', correct: false }], correct_option_ids: [1] },
  { id: 2, type: 'open_text', question: 'A2 термин', accepted_answers: ['Гиппократ'], case_sensitive: true },
  { id: 3, type: 'ticket', question: 'A3 билет' },
]);
const b = mkSubject('beta', 'Бета', 20, [
  { id: 1, type: 'single_choice', question: 'B1', options: [{ id: 1, text: 'p', correct: true }], correct_option_ids: [1] },
]);

const catalog = { schema_version: '1.1-multi-subject-runtime', subjects: [a.meta, b.meta], by_id: { alpha: a.entry, beta: b.entry } };

const steps = [];
const step = (n, f) => steps.push([n, f]);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* ---- simulate leftover progress from an older APK build ---- */
const stale = {
  'examtraining_current_subject_v1': 'alpha',
  'examtraining_subject_state_v1::alpha': JSON.stringify({
    v: 5, records: { 99: { attempts: 2, wrong: 1, mastered: false } },
    errorQueue: [99, 1234], lastMode: 'errors', lastQuestionId: 99, testFeedback: false,
    testStats: { started: 0, completed: 0, correct: 0, wrong: 0 },
  }),
};

const { window, document, errors } = boot({ catalog, storage: stale });
const click = (s) => clickEl(typeof s === 'string' ? q(s, document) : s, s);
const byId = (id) => clickEl(qa('.option', document).find((b) => b.dataset.id === String(id)), 'option ' + id);
// From a question the subject switcher is not on screen, so leave via system back.
const toHome = () => { if (window.examTrainingHandleBack()) toHome(); };

step('startup-with-stale-progress', () => {
  ok('startup: no uncaught js error screen', !/Ошибка интерфейса/.test(txt(document)), txtEl(document.body).slice(0, 200));
  ok('startup: no page errors', errors.length === 0, errors.join(' | '));
  ok('startup: subject resolved', /Альфа/.test(txt(document)));
});

step('errors-mode-with-stale-ids', () => {
  click('[data-action="start-mode"][data-mode="errors"]');
  ok('errors mode survives stale ids', !/Ошибка интерфейса/.test(txt(document)), txtEl(document.body).slice(0, 250));
  const hasQ = !!q('.question-text', document);
  ok('errors mode opens a real question or home', hasQ || !!q('.hero-continue', document), txtEl(document.body).slice(0, 200));
});

step('case-sensitive-open-text', () => {
  click('[data-action="tab"][data-tab="learn"]');
  click('[data-action="start-mode"][data-mode="ordered"]');
  // a1 -> answer wrong, then a2
  byId(2); click('[data-action="submit"]');
  click('[data-action="next"]');
  const inputEl = q('#text-answer', document);
  ok('open_text input present for case_sensitive item', !!inputEl, txtEl(document.body).slice(0, 200));
  inputEl.value = 'гиппократ';
  click('[data-action="submit"]');
  ok('case_sensitive=true must reject lowercase', !!q('.result.bad', document), txtEl(q('.result', document)));
});

step('subject-switch-isolation', () => {
  toHome();
  ok('learn-home reached', !!q('[data-action="start-mode"][data-mode="ordered"]', document), txtEl(document.body).slice(0, 200));
  click('[data-action="subject-open"]');
  ok('picker lists both', qa('[data-action="subject-select"]', document).length === 2);
  click('[data-action="subject-select"][data-id="beta"]');
  ok('switched to beta', /Бета/.test(txt(document)));
  ok('beta has fresh progress', /выучено/.test(txt(document)));
  click('[data-action="subject-open"]');
  click('[data-action="subject-select"][data-id="alpha"]');
  ok('back to alpha', /Альфа/.test(txt(document)));
  click('[data-action="tab"][data-tab="progress"]');
  ok('alpha keeps its own stats', !!q('.stats-grid', document));
});

step('ticket-without-explanation', () => {
  click('[data-action="tab"][data-tab="learn"]');
  toHome();
  click('[data-action="start-mode"][data-mode="ordered"]');
  // walk to the ticket (a3)
  for (let i = 0; i < 6; i++) {
    if (/Показать ответ/.test(txt(document))) break;
    const opt = qa('.option', document)[0];
    if (opt) clickEl(opt);
    const sub = q('[data-action="submit"]');
    if (sub) clickEl(sub);
    const nx = q('[data-action="next"]');
    if (nx) clickEl(nx);
  }
  ok('reached a ticket', /Показать ответ/.test(txt(document)), txtEl(document.body).slice(0, 150));
  click('[data-action="ticket-reveal"]');
  ok('missing ticket answer handled', !/Ошибка интерфейса/.test(txt(document)), txtEl(q('.ticket-answer', document) || document.body).slice(0, 150));
});

for (const [name, fn] of steps) {
  try { await fn(); } catch (e) { fails.push(`${name} THREW :: ${e.message}`); }
}
console.log(`PASS ${pass}  FAIL ${fails.length}`);
for (const f of fails) console.log('  FAIL: ' + f);
process.exit(fails.length ? 1 : 0);
