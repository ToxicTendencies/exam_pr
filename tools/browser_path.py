#!/usr/bin/env python3
"""Locate a Chromium build for the Playwright smoke tests.

The tests are optional: the primary UI coverage is the dependency-free jsdom
suite in ``tools/ui_tests``. Playwright is only used for the two ``*_smoke_test``
scripts, which additionally need a real browser engine.

Resolution order:

1. ``$CHROMIUM_PATH`` if it points at an existing executable.
2. Playwright's own browser download (``playwright install chromium``).
3. Well-known install locations on Windows / macOS / Linux.

Import this instead of hardcoding a path, otherwise the tests only run on the
machine where they were written.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

CANDIDATES = (
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/google-chrome",
)


def chromium_path() -> str | None:
    """Return an explicit executable path, or ``None`` to use Playwright's default."""
    env = os.environ.get("CHROMIUM_PATH")
    if env and Path(env).exists():
        return env
    for candidate in CANDIDATES:
        if Path(candidate).exists():
            return candidate
    found = shutil.which("chromium") or shutil.which("chrome") or shutil.which("google-chrome")
    return found


def launch(playwright):
    """Launch Chromium, preferring an explicit binary when one can be found."""
    path = chromium_path()
    return playwright.chromium.launch(
        executable_path=path,
        headless=True,
        args=["--no-sandbox"],
    )


def main() -> None:
    path = chromium_path()
    if path:
        print(f"chromium: {path}")
        return
    print("chromium: не найден — выполните `playwright install chromium`")
    print("Либо задайте путь через переменную окружения CHROMIUM_PATH.")


if __name__ == "__main__":
    main()