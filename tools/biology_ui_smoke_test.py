#!/usr/bin/env python3
"""Open the real generated biology subject and verify its key UI paths.

Optional check: it needs Playwright plus a Chromium build (``playwright install
chromium``). The always-available coverage is ``tools/verify_runtime_bundle.py``
for the data and ``tools/ui_tests`` for the UI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_path import launch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "app" / "src" / "main" / "assets"


def load_catalog() -> dict:
    text = (ASSETS / "subjects_core.js").read_text(encoding="utf-8")
    return json.loads(text[len("window.EXAM_SUBJECTS="):].strip().rstrip(";"))


def inline_page() -> str:
    html = (ASSETS / "index.html").read_text(encoding="utf-8")
    css = (ASSETS / "styles.css").read_text(encoding="utf-8")
    core = (ASSETS / "subjects_core.js").read_text(encoding="utf-8")
    # Biology explanations live in many small chunk files; inline them all so the
    # walkthrough is available without waiting for lazy loading.
    chunks = "\n".join(p.read_text(encoding="utf-8") for p in sorted((ASSETS / "subject_data").glob("biology_ex_*.js")))
    appjs = (ASSETS / "app.js").read_text(encoding="utf-8")
    storage_shim = """<script>(function(){var s={};Object.defineProperty(window,'localStorage',{value:{getItem:function(k){return Object.prototype.hasOwnProperty.call(s,k)?s[k]:null;},setItem:function(k,v){s[k]=String(v);},removeItem:function(k){delete s[k];},clear:function(){s={};},key:function(i){return Object.keys(s)[i]||null;},get length(){return Object.keys(s).length;}}});})();</script>"""
    html = html.replace('<link rel="stylesheet" href="styles.css">', "<style>" + css + "</style>")
    html = html.replace(
        '<script src="subjects_core.js"></script>',
        storage_shim + "<script>" + core + "</script><script>" + chunks + "</script>",
    )
    html = html.replace('<script src="app.js"></script>', "<script>" + appjs + "</script>")
    return html


def main() -> None:
    catalog = load_catalog()
    biology = next((s for s in catalog["subjects"] if s["id"] == "biology"), None)
    if biology is None:
        raise SystemExit("Предмет biology не найден в subjects_core.js: сначала выполните tools/build_data_bundles.py")

    errors: list[str] = []
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.set_content(inline_page(), wait_until="load", timeout=30000)

        page.locator('[data-action="subject-open"]').first.click()
        page.locator('[data-action="subject-select"][data-id="biology"]').click()
        body = page.locator("body")
        assert f"{biology['item_count']} заданий · {biology['ticket_count']} билетов" in body.inner_text()

        page.locator('[data-action="start-mode"][data-mode="ordered"]').click()
        assert "Билет №1" in page.locator(".question-context").inner_text()
        page.locator('[data-action="ticket-reveal"]').click()
        page.locator(".ticket-answer").wait_for(state="visible", timeout=15000)
        assert "Нервная система" in page.locator(".ticket-answer").inner_text()
        page.locator('[data-action="question-back"]').click()

        page.locator('[data-action="tab"][data-tab="test"]').click()
        selector = page.locator('[data-action="set-test-ticket"]')
        # One "all tickets" option plus one per exam ticket.
        assert selector.locator("option").count() == biology["ticket_group_count"] + 1
        last_ticket = biology["ticket_group_count"]
        selector.select_option(str(last_ticket))
        page.locator('[data-action="start-test-final"]').click()
        assert f"Билет №{last_ticket}" in page.locator(".question-context").inner_text()
        page.locator('[data-action="test-home"]').last.click()

        page.locator('[data-action="tab"][data-tab="bank"]').click()
        page.locator("#bank-search").fill("Длительность миграции")
        page.wait_for_timeout(350)
        assert page.locator(".bank-item").count() >= 1
        assert "Длительность миграции" in page.locator(".bank-list").inner_text()
        assert not errors, errors
        browser.close()
    print("PASS: real biology subject, ticket answer, ticket filter, and metadata search")


if __name__ == "__main__":
    main()
