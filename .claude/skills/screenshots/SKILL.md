---
name: screenshots
description: Capture or refresh screenshots of the Colorín Colorado Streamlit UI (workbench, pages, Export PDF and Amazon KDP views) for README.md and docs/images/, from a neutral demo book so no country or city shows. Use this whenever the user asks for screenshots, wants to update docs/images/ui-workbench.png or other UI images after a UI change, wants to "see" how a view looks, or needs a visual check of a Streamlit change that curl cannot show. Drives the running app on port 8502 with Playwright and the system Chrome.
---

# UI screenshots

Streamlit views depend on browser session state (which book is open, which view is selected), so
a screenshot needs a real browser that clicks through the UI. `scripts/capture.py` does that with
Playwright on the system Google Chrome, against the app at http://localhost:8502.

The product is place-neutral: a screenshot must not show a country, city, region or landmark
name. The author's own books can be about anything, so captures never use them: they use a demo
book, **Mi mundo para colorear**, whose captions are written in `scripts/demo_book.py`.

## Workflow

1. **App running, current code.** `.claude/skills/run-app/scripts/app.sh status`. If it is down,
   start it with the run-app skill. Streamlit only reloads changed modules while a tab is
   connected: if `app/` was edited with no tab open (for example between Playwright runs),
   `app.sh restart` first, or the capture shows the old UI.
2. **Demo book** (created once, a no-op afterwards; prints its slug):
   ```bash
   .claude/skills/screenshots/scripts/demo_book.sh      # -> mi-mundo-para-colorear
   ```
   It runs `demo_book.py` in a throwaway container of the app's image (`docker compose run
   --rm`, no rebuild) and adds `books/mi-mundo-para-colorear/` with three pages: toucan
   (approved), pigeons, boy. Photos come from `spike/photos/` (Wikimedia Commons, see its
   `CREDITS.tsv`) or from another book's originals with the same upload name. Each coloring page
   is copied from another book's page made from the same photo when there is one, otherwise it is
   the free draft. It never calls an AI and costs nothing. To change the demo pages, edit
   `DEMO_PAGES` (keep the text place-neutral) and remove the demo book from the app's home page
   (only that one) before running it again.
3. **Playwright** (a throwaway venv outside the repo; prints the interpreter):
   ```bash
   PY=$(.claude/skills/screenshots/scripts/setup.sh)
   ```
4. **Capture into a scratch folder, never into the repo:**
   ```bash
   OUT=$(mktemp -d)
   $PY .claude/skills/screenshots/scripts/capture.py --out "$OUT"     # workbench,pages,export,kdp
   $PY .claude/skills/screenshots/scripts/capture.py --out "$OUT" --only workbench
   ```
5. **Look at every PNG** (Read tool) and compare it with the published one. Check: the view's
   segment highlighted, page 1 "✅ Aprobada", no spinner, images loaded (no grey boxes), no
   expander left open, light theme, and no place name anywhere. The script exits 1 and prints
   `LEAK` when any title, subtitle or caption of another book appears in the page text (the
   whole page, below the fold too, so it is conservative), and `WARNING` when the Gemini or
   local GPU buttons are disabled. Do not publish over a better image: when Gemini is not
   configured (`GOOGLE_CLOUD_PROJECT` or the API key empty in Settings) the **Otra con Gemini**
   button is grey, while the published `ui-workbench.png` shows it red.
6. **Publish** only the screens that passed, under the names the docs link to:
   ```bash
   .claude/skills/screenshots/scripts/publish.sh "$OUT" docs/images workbench
   ```
   It writes `docs/images/ui-<screen>.png`, at most 1280 px wide, quantized to 255 colours
   (palette PNG, ~140 KB for the workbench, like the current file), and prints the old and new
   sizes. Add new screens to the table below and link them from `docs/usage.md`.

## Files the docs expect

| File | Linked from | Shows | Made with |
|---|---|---|---|
| `docs/images/ui-workbench.png` | README "The workbench" | Workbench, page 1 of the demo book (toucan, approved), 1280×1330 | `capture.py --only workbench` + `publish.sh` |
| `docs/images/banner.jpg`, `sample-pages.jpg`, `photo-to-page.jpg`, `more-styles.jpg` | README | Composites of photos, coloring pages and PDF pages | not made by this skill |
| `docs/images/kdp-cover.jpg` | `docs/amazon-kdp.md` | KDP wraparound cover | not this skill |
| `docs/images/stable-diffusion.jpg`, `local-gpu.jpg` | `docs/spike.md` | Spike results | not made by this skill |

`capture.py` also takes `pages`, `export` and `kdp` (book views, safe) and `home`, `usage` (the
home page lists **every** book and the usage panel names them, so they leak whenever another book
is about a place; the guard flags them). None of these is linked from the docs yet.

The UI language is what `UI_LANGUAGE` in `config/.env` says (Spanish by default, as in the
published image). The capture never touches the **Idioma · Language** selector, because changing
it saves to `config/.env`.

## Rules

- Never `docker compose down`, rebuild the image, or delete anything under `books/` or `data/` for
  a screenshot. The demo book is the only thing this skill adds.
- Never take screenshots of the author's own books for the docs, even cropped.
- Keep the settings expander closed in any home capture (it opens by itself when no engine is
  available): it shows the GCP project and auth mode.
- `docs/images/` is committed (GitHub's attachment uploader is browser-only, and relative links
  keep the README working offline); keep each UI screenshot under ~200 KB.

## Selector notes (when the UI changes)

- Home → book: the **Abrir/Open** button has key `open_<slug>`; keyed widgets get the CSS class
  `st-key-<key>`, so `.st-key-open_<slug> button`.
- Views: `st.segmented_control` renders `[data-testid='stButtonGroup'] [role='radio']` with the
  emoji in its own span; match the text without it (`Mesa de trabajo`, `Páginas`...). Clicking the
  selected segment again deselects it, so `open_view` checks `aria-checked` first.
- Opening a book from a card scrolls the main area; `to_top` resets every scrolled element and
  parks the mouse in an empty corner (hovering the sidebar shows its collapse arrow).
- Engine buttons: `[data-testid='stMain'] button` with "Gemini" / "GPU local" in the text.
- Allow 2–4 s after each click: Streamlit reruns are async and images load lazily.
