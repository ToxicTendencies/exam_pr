#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_path import launch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SUBJECTS = ROOT / 'data' / 'subjects'
ASSETS = ROOT / 'app' / 'src' / 'main' / 'assets'
BUILDER = ROOT / 'tools' / 'build_data_bundles.py'
TEMP = SUBJECTS / 'zz_smoke_subject.json'
TEMP_TICKETS = SUBJECTS / 'zz_smoke_tickets_only.json'


def build():
    subprocess.run(['python', str(BUILDER)], cwd=ROOT, check=True, capture_output=True, text=True)


def make_temp_subject():
    data = {
        'schema_version': '2.1-subject-bank',
        'subject': {'id': 'smoke_subject', 'title': 'Тестовый предмет', 'language': 'ru', 'order': 9999},
        'questions': [
            {
                'id': 1,
                'type': 'single_choice',
                'question': 'Тестовый вопрос',
                'ticket_number': 7,
                'ticket_question_number': 1,
                'topic': 'Тестовая тема',
                'subtopic': 'Один ответ',
                'options': [
                    {'id': 1, 'text': 'Неправильно', 'correct': False},
                    {'id': 2, 'text': 'Правильно', 'correct': True},
                ],
                'explanation': {
                    'topic_markdown': 'Тестовая тема',
                    'answers_markdown': 'Тестовый разбор',
                    'correct_answer_markdown': '**2. Правильно**',
                },
            },
            {
                'id': 2,
                'type': 'matching',
                'question': 'Тестовое соответствие',
                'ticket_number': 7,
                'ticket_question_number': 2,
                'topic': 'Тестовая тема',
                'subtopic': 'Соответствие',
                'left_items': [{'id': 1, 'text': 'A'}, {'id': 2, 'text': 'B'}],
                'right_items': [{'id': 1, 'text': '1'}, {'id': 2, 'text': '2'}],
                'correct_mapping': [{'left_id': 1, 'right_id': 2}, {'left_id': 2, 'right_id': 1}],
                'explanation': {
                    'topic_markdown': 'Тема соответствия',
                    'answers_markdown': 'Разбор соответствия',
                    'correct_answer_markdown': 'A → 2; B → 1',
                },
            },
            {
                'id': 3,
                'type': 'ticket',
                'ticket_number': 7,
                'topic': 'Тестовая тема',
                'ticket': 'Тестовый билет',
                'answer_markdown': '**Развёрнутый ответ**\n\nТекст билета.',
            },
        ],
    }
    TEMP.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    ticket_only = {
        'schema_version': '2.1-subject-bank',
        'subject': {'id': 'smoke_tickets_only', 'title': 'Только билеты', 'language': 'ru', 'order': 10000},
        'questions': [
            {'id': 1, 'type': 'ticket', 'ticket': 'Билет без тестовых вариантов', 'answer_text': 'Ответ на билет'}
        ],
    }
    TEMP_TICKETS.write_text(json.dumps(ticket_only, ensure_ascii=False, indent=2), encoding='utf-8')


def inline_page():
    html = (ASSETS / 'index.html').read_text(encoding='utf-8')
    css = (ASSETS / 'styles.css').read_text(encoding='utf-8')
    core = (ASSETS / 'subjects_core.js').read_text(encoding='utf-8')
    # The app loads explanation chunks lazily. These tests want everything present
    # immediately, so every generated chunk is inlined into the page up front.
    explanations = '\n'.join(
        p.read_text(encoding='utf-8') for p in sorted((ASSETS / 'subject_data').glob('*.js'))
    )
    appjs = (ASSETS / 'app.js').read_text(encoding='utf-8')
    storage_shim = """<script>(function(){var s={};Object.defineProperty(window,'localStorage',{value:{getItem:function(k){return Object.prototype.hasOwnProperty.call(s,k)?s[k]:null;},setItem:function(k,v){s[k]=String(v);},removeItem:function(k){delete s[k];},clear:function(){s={};},key:function(i){return Object.keys(s)[i]||null;},get length(){return Object.keys(s).length;}}});})();</script>"""
    html = html.replace('<link rel="stylesheet" href="styles.css">', '<style>' + css + '</style>')
    html = html.replace('<script src="subjects_core.js"></script>', storage_shim + '<script>' + core + '</script><script>' + explanations + '</script>')
    html = html.replace('<script src="app.js"></script>', '<script>' + appjs + '</script>')
    return html


def run_ui():
    errors = []
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={'width': 390, 'height': 844}, color_scheme='dark')
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        page.set_content(inline_page(), wait_until='load')
        page.wait_for_timeout(100)

        # System theme is the default and must follow a dark device immediately.
        assert page.locator('html').get_attribute('data-theme') == 'dark'
        assert 'Фармакология' in page.locator('.subject-title-btn').first.inner_text()
        page.locator('[data-action="subject-open"]').first.click()
        assert page.locator('.subject-item').count() >= 2
        page.locator('[data-action="subject-select"][data-id="smoke_subject"]').click()
        assert 'Тестовый предмет' in page.locator('.subject-title-btn').first.inner_text()
        assert '3 задания · 1 билет' in page.locator('body').inner_text()

        page.locator('[data-action="start-mode"][data-mode="ordered"]').click()
        page.locator('[data-action="option"][data-id="1"]').click()
        page.locator('[data-action="submit"]').click()
        page.locator('[data-action="question-back"]').click()
        assert page.locator('.summary-cell').nth(1).locator('b').inner_text() == '1'

        page.locator('[data-action="subject-open"]').first.click()
        page.locator('[data-action="subject-select"][data-id="pharmacology"]').click()
        assert page.locator('.summary-cell').nth(1).locator('b').inner_text() == '0'

        page.locator('[data-action="subject-open"]').first.click()
        page.locator('[data-action="subject-select"][data-id="smoke_subject"]').click()
        assert page.locator('.summary-cell').nth(1).locator('b').inner_text() == '1'

        page.locator('[data-action="start-mode"][data-mode="ordered"]').click()
        assert '7.2' in page.locator('.qcounter').inner_text()
        for left, right in [(1, 2), (2, 1)]:
            page.locator(f'[data-action="match-toggle"][data-left="{left}"]').click()
            page.locator(f'[data-action="match-choose"][data-left="{left}"][data-right="{right}"]').click()
        page.locator('[data-action="submit"]').click()
        assert page.locator('details.details').count() >= 1
        page.locator('[data-action="next"]').click()
        assert 'Билет' in page.locator('.question-type').inner_text()
        page.locator('[data-action="ticket-reveal"]').click()
        assert 'Развёрнутый ответ' in page.locator('.ticket-answer').inner_text()
        page.locator('[data-action="ticket-repeat"]').click()
        assert page.locator('.question-type').count() == 1

        page.locator('[data-action="question-back"]').click()

        # Capture learning-only progress before a test. Test answers must not mutate it.
        page.locator('[data-action="tab"][data-tab="progress"]').click()
        learning_before = page.locator('.stats-grid .stat b').all_inner_texts()

        page.locator('[data-action="tab"][data-tab="test"]').click()
        assert '2 вопроса' in page.locator('body').inner_text()
        assert page.locator('[data-action="set-test-ticket"]').count() == 1
        page.locator('[data-action="set-test-ticket"]').select_option('7')
        assert 'билет 7' in page.locator('body').inner_text().lower()
        page.locator('[data-action="start-test-final"]').click()
        for _ in range(2):
            type_text = page.locator('.question-type').inner_text()
            if 'Один ответ' in type_text:
                page.locator('[data-action="test-option"][data-id="1"]').click()
            elif 'Соответствие' in type_text:
                for left in (1, 2):
                    page.locator(f'[data-action="match-toggle"][data-context="test"][data-left="{left}"]').click()
                    page.locator(f'[data-action="match-choose"][data-context="test"][data-left="{left}"][data-right="1"]').click()
            page.locator('[data-action="test-answer"]').click()
        assert 'тест завершён' in page.locator('body').inner_text().lower()

        page.locator('[data-action="tab"][data-tab="progress"]').click()
        assert page.locator('.stats-grid .stat b').all_inner_texts() == learning_before
        assert page.locator('.test-session-stat').nth(0).locator('b').inner_text() == '1'
        assert page.locator('.test-session-stat').nth(1).locator('b').inner_text() == '1'
        assert 'Ответы в тестах · 2' in page.locator('.test-answer-title').inner_text()
        percentages = [int(x.rstrip('%')) for x in page.locator('.test-answer-legend b').all_inner_texts()]
        assert sum(percentages) == 100

        # A launched but abandoned test must not count as completed.
        page.locator('[data-action="tab"][data-tab="test"]').click()
        page.locator('[data-action="start-test-final"]').click()
        page.locator('[data-action="test-home"]').last.click()
        page.locator('[data-action="tab"][data-tab="progress"]').click()
        assert page.locator('.test-session-stat').nth(0).locator('b').inner_text() == '2'
        assert page.locator('.test-session-stat').nth(1).locator('b').inner_text() == '1'
        assert page.locator('.stats-grid .stat b').all_inner_texts() == learning_before

        page.locator('[data-action="tab"][data-tab="test"]').click()
        page.locator('[data-action="subject-open"]').first.click()
        page.locator('[data-action="subject-select"][data-id="smoke_tickets_only"]').click()
        page.locator('[data-action="tab"][data-tab="test"]').click()
        assert 'Тест недоступен' in page.locator('body').inner_text()
        assert 'есть только билеты' in page.locator('body').inner_text()

        # Settings: color editor must be fully in-app. Native input[type=color]
        # used to crash some Android WebView versions.
        page.locator('[data-action="tab"][data-tab="progress"]').click()
        page.locator('[data-action="open-settings"]').first.click()
        assert page.locator('input[type="color"]').count() == 0
        page.locator('[data-action="color-open"][data-color-key="accent"]').click()
        assert page.locator('.color-editor-modal').count() == 1
        slider = page.locator('[data-color-slider="r"]')
        slider.fill('123')
        assert page.locator('[data-color-output="r"]').inner_text() == '123'
        page.locator('[data-action="color-close"]').last.click()
        assert page.locator('.color-editor-modal').count() == 0
        assert not errors, errors
        browser.close()


def main():
    try:
        make_temp_subject()
        build()
        run_ui()
        print('PASS: system dark theme, isolated learning/test statistics, multi-subject selector, matching, tickets, test filtering, explanations, safe color editor')
    finally:
        if TEMP.exists():
            TEMP.unlink()
        if TEMP_TICKETS.exists():
            TEMP_TICKETS.unlink()
        build()


if __name__ == '__main__':
    main()
