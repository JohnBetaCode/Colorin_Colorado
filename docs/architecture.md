# Architecture

How Colorín Colorado is built. The [plan](plan.md) describes the product and its phases; the
[spike](spike.md) explains why the line-art cleanup looks the way it does.

## Overview

A single Streamlit process (`app/main.py`) renders the home page (`app/ui/home.py`) or one book's
workspace (`app/ui/book.py`), which switches between three views: workbench, pages and export.
Business logic lives in `app/core/` and never imports Streamlit; the UI calls it and renders.

```
app/ui/home.py ─────┐
app/ui/book.py ─────┼──► app/core/books.py    books/<slug>/book.json
  workbench.py      │    app/core/pages.py    pages.json, photos, versions
  pages_grid.py     │
  export_panel.py   ├──► app/core/imaging.py ──► app/core/gemini.py ──► Vertex AI
                    │          │                       └──► app/core/usage.py (data/usage.jsonl)
                    │          └──► app/core/lineart.py (clean, draft)
                    ├──► app/core/export.py   (ReportLab PDF)
                    └──► app/core/i18n.py, config.py
```

## Modules

| Module | Responsibility |
|---|---|
| `core/config.py` | Loads `config/.env`; `Settings`; `save_settings` merges new values into `.env` (keys not passed are kept). |
| `core/gemini.py` | One cached `genai.Client` per location, created under a lock (concurrent first calls used to build throwaway clients that closed their connection when garbage-collected). `generate_image` takes reference images (JPEG/PNG/WebP sniffed), aspect ratio and size, and retries once when no image comes back. Every call records usage. |
| `core/usage.py` | One JSON line per call with tokens and estimated cost (`PRICING`); `book_context(book_id)` attributes calls to a book. |
| `core/schema.py` | Pydantic models `Book`, `Page`, `Version`, `Crop` and the option tuples (`STYLES`, `AGE_GROUPS`...). |
| `core/books.py` | Book folders under `books/`, `book.json`, slugs (accents folded), create/list/delete. |
| `core/pages.py` | `pages.json`; photo ingestion (EXIF rotation, HEIC, 2048 px), crop, versions (`add_version`, `select_version`, `approve`), order, deletion, thumbnails. |
| `core/imaging.py` | Prompt pieces (`STYLE_PROMPTS`, `AGE_PROMPTS`, `BACKGROUND_PROMPTS`), `build_prompt`, aspect ratio from the photo, and `convert_page`, which runs an engine, cleans the result and stores it as a new version. |
| `core/lineart.py` | The black-and-white guarantee (`clean`) and the offline draft engine (`draft`). |
| `core/export.py` | `preflight` (what the PDF will contain, captions that overflow) and `export_book_pdf`. |
| `core/i18n.py` | `STRINGS` in Spanish and English, `t(key, lang=None, **params)`. |

## Data layout

There is no database. Each book is a folder under `books/` (git-ignored, bind-mounted):

```
books/<slug>/
  book.json                       Book
  pages.json                      list[Page], in book order
  originals/<page-id>.jpg         uploaded photo (EXIF-rotated, max 2048 px)
  lineart/<page-id>/v<n>-raw.png  what the engine returned
  lineart/<page-id>/v<n>.png      1-bit cleaned coloring page
  exports/<slug>-<timestamp>.pdf  one file per build, never overwritten
```

A page's status moves `pending → converted → approved`; a new version or switching versions puts
it back to `converted`. Versions are numbered and never overwritten. Usage is attributed by book
id, not slug, because a deleted book's slug can be reused.

## Pipelines

### Conversion (`imaging.convert_page`)

1. Crop the original photo (`pages.cropped_photo`).
2. **AI engine**: build the prompt from the style, the age group, the background, the page title
   (it names the subject) and the author's instructions; send the photo as the reference image
   with the closest supported aspect ratio (`3:4`, `1:1`, `4:3`) at `2K`.
   **Draft engine**: mean shift + k-means flatten the photo into a few color areas and their
   borders become the lines, so every area is closed. Free, deterministic, and not a drawing.
3. `lineart.clean` the result and store raw + clean as the next version, selected.

### Cleanup (`lineart.clean`)

In order, all at 2400 px on the long side:

1. **Mockup check**: if the outer strip of the image is mostly not white paper, the model returned
   a photo of a printed page; cut the sheet out.
2. **Ink** = darker than `min(Otsu, 150)` and not saturated: light gray shading and colors copied
   from the photo drop out; near-black stays.
3. Remove specks; fill tiny white holes inside lines.
4. **Frames**: remove ink that lives only in the outer 5% ring and runs along a side.
5. **Hollow fills**: black areas that still contain a disk three strokes wide, and are not tiny
   (pupils stay), are replaced by their outline.
6. **Thicken** one pixel per side at a time toward the age group's minimum width, stopping before
   areas big enough to color at that age close up or the page gets too dark.
7. Crop to the drawing plus a margin; save as a 1-bit PNG.

It reports `CleanResult.warnings` (`was_mockup`, `had_color`, `had_shading`, `filled_areas`,
`too_dark`, `too_few_regions`); the workbench shows them and they never block.

### PDF export (`export.export_book_pdf`)

ReportLab canvas, Letter or A4, Andika (SIL) as the typeface. Cover with the cover page's line art,
optional owner page, then one sheet per included page: line art in the top box, and an info box
(rounded rectangle) with the cropped reference photo and the caption. Caption text shrinks in
steps until it fits, otherwise it is clipped to the box (`preflight` lists those pages). Line art
is embedded as 8-bit grayscale with lossless compression, so it stays pure 0/255; photos are
bounded JPEGs. Optional blank back after every sheet.

## UI rules

- **Widget identity.** Streamlit hashes `value=`/`index=` and the formatted option labels into a
  widget's identity. A widget whose starting value comes from saved data, saved by its own
  `on_change`, gets re-created on the next run, and in practice that lost the next button click
  (the page selector showed titles, so editing a title reset it to page 1). Keyed widgets are
  therefore seeded with `common.seed(key, value)` and called without `value`/`index`, and option
  labels never include data that changes while you work. "Use the book's setting" is the
  `"book"` option, not `None`, because a selectbox whose state is `None` shows as empty.
- Fields save themselves through `on_change` callbacks, so their values are on disk before a
  button in the same rerun converts or approves the page.
- Every user-facing string goes through `i18n.t`; `tests/test_i18n.py` checks that every key used
  in `app/` exists in both languages with the same placeholders.

## Differences from the plan

| Plan | Built | Why |
|---|---|---|
| Draft engine: bilateral filter + adaptive threshold | Color-area segmentation | Edge detectors left loose strokes with no closed areas to color. |
| Crop in phase 2 | Crop in the MVP workbench | The spike showed small subjects stay small; cropping is the fix. |
| Blank backs in phase 3 | In the MVP | One `showPage()` per sheet. |
| Thicken lines to the age group's width | Thicken step by step, stop before areas merge | Growing dense drawings to the 3–5 width turned them into black blobs. |
