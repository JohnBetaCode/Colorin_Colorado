"""Capture screenshots of the running Colorín Colorado app (http://localhost:8502).

Usage:
    python capture.py --out DIR [--book SLUG] [--only workbench,pages] [--base URL]

Drives the app with Playwright on the system Google Chrome (channel="chrome"), light theme,
1280 px wide. The app must be running (run-app skill) and the demo book must exist
(demo_book.sh prints its slug). Screens, saved as DIR/<screen>.png:

    workbench   the workbench on page 1 (approved): photo, caption, coloring page, engine buttons
                -> docs/images/ui-workbench.png (README "The workbench")
    pages       the pages view (grid of all pages)
    export      the Export PDF view (preflight; the PDF is not built)
    kdp         the Amazon KDP view
    home        the home page (lists EVERY book: only when all their titles are place-neutral)
    usage       home page with the usage panel open (lists books by title)

Default: workbench, pages, export, kdp. The UI language is whatever config/.env says
(UI_LANGUAGE); the script never touches the language selector, which saves to config/.env.

Place-neutral guard: after each capture, the visible text is checked for the titles, subtitles
and page captions of every OTHER book under books/; a match is reported as LEAK and the exit
code is 1. It catches data from other books, not a place name typed into the demo book itself:
still look at every image.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[4]
BOOK_SCREENS = ["workbench", "pages", "export", "kdp"]
HOME_SCREENS = ["home", "usage"]
# i18n keys view.<id> in both languages (the UI may be in either), without the emoji: the
# segmented control renders it in its own span.
VIEW_LABELS = {
    "workbench": ["Mesa de trabajo", "Workbench"],
    "pages": ["Páginas", "Pages"],
    "export": ["Exportar PDF", "Export PDF"],
    "kdp": ["Amazon KDP"],
}
USAGE_LABELS = ["📊 Uso y costos", "📊 Usage & costs"]
HEIGHTS = {"workbench": 1330, "pages": 1100, "export": 1100, "kdp": 1100, "home": 1000, "usage": 1000}


def book_strings(folder: Path) -> set[str]:
    """Title, subtitle, slug and page captions of one book folder."""
    try:
        book = json.loads((folder / "book.json").read_text(encoding="utf-8"))
        page_list = json.loads((folder / "pages.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    found = {book.get("title", ""), book.get("subtitle", ""), folder.name}
    for page in page_list:
        found.update([page.get("title", ""), page.get("subtitle", ""), *page.get("info", "").splitlines()])
    return {s.strip() for s in found if len(s.strip()) >= 4}


def other_books_text(demo_slug: str) -> list[str]:
    """Text of the other books that must not show up in a demo screenshot (text the demo book
    shares with them, such as a copied caption, is allowed)."""
    others: set[str] = set()
    for meta in (ROOT / "books").glob("*/book.json"):
        if meta.parent.name != demo_slug:
            others |= book_strings(meta.parent)
    return sorted(others - book_strings(ROOT / "books" / demo_slug))


def settle(page, seconds: float = 2.5) -> None:
    """Wait for Streamlit's rerun to finish and lazy images to arrive."""
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PlaywrightTimeout:
        pass  # the websocket keeps the page "busy"; fall through to the spinner check
    try:
        page.locator("[data-testid='stStatusWidget']").wait_for(state="hidden", timeout=30_000)
    except PlaywrightTimeout:
        pass
    time.sleep(seconds)


def click_first(page, labels: list[str]) -> None:
    for label in labels:
        loc = page.get_by_text(label, exact=True)
        if loc.count():
            loc.first.click()
            return
    raise SystemExit(f"none of {labels} found on the page; the UI changed (see SKILL.md selector notes)")


def open_view(page, labels: list[str]) -> None:
    """Select a view in the segmented control (radios in an stButtonGroup), unless it is already
    selected: clicking the selected segment again deselects it, and the screenshot would show
    no view highlighted."""
    for label in labels:
        radio = page.locator("[data-testid='stButtonGroup'] [role='radio']", has_text=label)
        if radio.count():
            if radio.first.get_attribute("aria-checked") != "true":
                radio.first.click()
            return
    raise SystemExit(f"view {labels} not found; the UI changed (see SKILL.md selector notes)")


def to_top(page) -> None:
    """Scroll back to the top (the click on a book's Open button scrolls the main area) and park
    the mouse on empty space (hovering the sidebar shows its collapse arrow, a button its outline)."""
    page.evaluate("document.querySelectorAll('*').forEach(e => { if (e.scrollTop) e.scrollTop = 0; })")
    size = page.viewport_size
    page.mouse.move(size["width"] - 5, size["height"] - 5)
    time.sleep(0.5)


def check_engines(page) -> None:
    """Warn when an engine's buttons are disabled: the docs show Gemini and the local GPU enabled."""
    for engine, labels, how in [
        ("Gemini", ["Gemini"], "set it up in Settings (config/.env: GEMINI_AUTH and its project or key)"),
        ("local GPU", ["GPU local", "Local GPU"], "start its server: run-app's app.sh gpu"),
    ]:
        buttons = page.locator("[data-testid='stMain'] button").filter(
            has_text=re.compile("|".join(labels))
        )
        if buttons.count() and all(buttons.nth(i).is_disabled() for i in range(buttons.count())):
            print(f"WARNING: the {engine} buttons are disabled in this capture; {how}, "
                  "or do not replace a published screenshot that shows them enabled")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:8502")
    ap.add_argument("--out", required=True, help="output folder (a scratch folder, never docs/images)")
    ap.add_argument("--book", default="mi-mundo-para-colorear", help="slug of the demo book")
    ap.add_argument("--only", default="", help="comma-separated screens (default: " + ",".join(BOOK_SCREENS) + ")")
    ap.add_argument("--width", type=int, default=1280)
    args = ap.parse_args()

    wanted = [s.strip() for s in args.only.split(",") if s.strip()] or BOOK_SCREENS
    unknown = set(wanted) - set(BOOK_SCREENS + HOME_SCREENS)
    if unknown:
        sys.exit(f"unknown screens: {', '.join(sorted(unknown))}")
    if not (ROOT / "books" / args.book / "book.json").exists():
        sys.exit(f"no book {args.book!r} under books/: run demo_book.sh first")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    forbidden = other_books_text(args.book)
    leaks: dict[str, list[str]] = {}

    def shot(page, name: str) -> None:
        text = page.locator("body").inner_text()
        hits = [s for s in forbidden if s.lower() in text.lower()]
        path = out / f"{name}.png"
        page.screenshot(path=str(path))
        if hits:
            leaks[name] = hits
            print(f"LEAK {path}: shows text of another book: {hits}")
        else:
            print("saved", path)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": args.width, "height": 1000}, color_scheme="light")
        page = ctx.new_page()
        page.goto(args.base)
        page.get_by_role("button", name="Abrir").or_(page.get_by_role("button", name="Open")).first.wait_for(
            timeout=60_000
        )
        settle(page)

        if "home" in wanted:
            page.set_viewport_size({"width": args.width, "height": HEIGHTS["home"]})
            settle(page, 1)
            shot(page, "home")
        if "usage" in wanted:
            page.set_viewport_size({"width": args.width, "height": HEIGHTS["usage"]})
            click_first(page, USAGE_LABELS)
            settle(page, 1.5)
            page.get_by_text(USAGE_LABELS[0]).or_(page.get_by_text(USAGE_LABELS[1])).first.scroll_into_view_if_needed()
            shot(page, "usage")
            click_first(page, USAGE_LABELS)  # close it again
            settle(page, 1)

        book_screens = [s for s in BOOK_SCREENS if s in wanted]
        if book_screens:
            # Keyed widgets get the CSS class st-key-<key>; the card's button key is open_<slug>.
            page.locator(f".st-key-open_{args.book} button").click()
            settle(page, 4)
            for name in book_screens:
                page.set_viewport_size({"width": args.width, "height": HEIGHTS[name]})
                open_view(page, VIEW_LABELS[name])
                settle(page, 3)
                to_top(page)
                if name == "workbench":
                    check_engines(page)
                shot(page, name)

        browser.close()

    if leaks:
        sys.exit(f"{len(leaks)} screenshot(s) show another book's text: do not publish {sorted(leaks)}")


if __name__ == "__main__":
    main()
