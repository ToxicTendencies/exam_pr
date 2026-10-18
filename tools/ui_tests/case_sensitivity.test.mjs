import { boot, q, qa, txt, click as clickEl } from './harness.mjs';

const txtEl = (el) => (el ? el.textContent.replace(/\s+/g, ' ').trim() : '<none>');
let pass = 0; const fails = [];
const ok = (n, c, e = '') => (c ? pass++ : fails.push(`${n}${e ? ' :: ' + e : ''}`));

const questions = [
  { id: 1, type: 'open_text', question: 'Чувствительный', accepted_answers: ['Гиппократ'], case_sensitive: true },
  { id: 2, type: 'open_text', question: 'Нечувствительный', accepted_answers: ['Гиппократ'], case_sensitive: false },
];
const meta = { id: 'cs', title: 'Регистр', language: 'ru', order: 1, item_count: 2, question_count: 2,
  ticket_count: 0, test_question_count: 2, ticket_group_count: 0, explanation_count: 0, explanations_script: '', canonical_sha256: 'x' };
const catalog = { schema_version: '1.1-multi-subject-runtime', subjects: [meta], by_id: { cs: { subject: meta, questions } } };
const { document } = boot({ catalog });
const click = (s) => clickEl(typeof s === 'string' ? q(s, document) : s, s);

click('[data-action="start-mode"][data-mode="ordered"]');
q('#text-answer', document).value = 'гиппократ';
click('[data-action="submit"]');
ok('case_sensitive=true rejects wrong case', !!q('.result.bad', document), txtEl(q('.result', document)));
click('[data-action="next"]');
q('#text-answer', document).value = 'гиппократ';
click('[data-action="submit"]');
ok('case_sensitive=false accepts wrong case', !!q('.result.good', document), txtEl(q('.result', document)));

console.log(`PASS ${pass}  FAIL ${fails.length}`);
for (const f of fails) console.log('  FAIL: ' + f);
process.exit(fails.length ? 1 : 0);
