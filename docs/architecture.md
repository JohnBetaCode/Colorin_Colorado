# Architecture

How Colorín Colorado is built. The [plan](plan.md) describes the product and its phases; the
[spike](spike.md) explains why the line-art cleanup looks the way it does.

## Overview

A single Streamlit process (`app/main.py`) renders the home page (`app/ui/home.py`) or one book's
workspace (`app/ui/book.py`), which switches between four views: workbench, pages, export and
Amazon KDP.
Business logic lives in `app/core/` and never imports Streamlit; the UI calls it and renders.

```
app/ui/home.py ─────┐
app/ui/book.py ─────┼──► app/core/books.py     books/<slug>/book.json
  workbench.py      │    app/core/pages.py     pages.json, photos, versions
  pages_grid.py     │
  export_panel.py   ├──► app/core/imaging.py ──┬──► app/core/gemini.py ──► Gemini (Vertex AI or AI Studio)
  kdp_panel.py      │                          │         └──► app/core/usage.py (data/usage.jsonl)
                    │                          ├──► app/core/stable_diffusion.py ──► your sd-server (optional)
                    │                          └──► app/core/lineart.py (clean, draft)
                    ├──► app/core/captions.py  (translations, Amazon listing) ──► gemini.py
                    ├──► app/core/cover_art.py (front cover images) ──► gemini.py
                    ├──► app/core/commons.py   (Wikimedia Commons photos and credits)
                    ├──► app/core/export.py    (ReportLab PDF: the interior) ──► extras.py
                    ├──► app/core/kdp.py       (KDP numbers, review) ──► export.py, cover_art.py
                    ├──► app/core/cover.py     (KDP wraparound cover) ──► export.py, kdp.py, cover_art.py
                    ├──► app/core/marketing.py (listing images) ──► export.py, cover.py
                    └──► app/core/i18n.py, config.py, templates.py
```

## Modules

| Module | Responsibility |
|---|---|
| `core/config.py` | Loads `config/.env`; `Settings` (including the auth method: `adc`, `vertex_key` or `studio_key`); `save_settings` merges new values into `.env` (keys not passed are kept). |
| `core/gemini.py` | One cached `genai.Client` per location, created under a lock (concurrent first calls used to build throwaway clients that closed their connection when garbage-collected): Vertex AI with ADC and a project, Vertex AI with an API key, or the Gemini Developer API with an AI Studio key. `generate_image` takes reference images (JPEG/PNG/WebP sniffed), aspect ratio and size, returns the final image (not the low-resolution drafts the model thinks with, which come first, marked `thought`), and retries once when no image comes back. Every call records usage. |
| `core/stable_diffusion.py` | The optional second image engine: a stable-diffusion.cpp server (`sd-server`, FLUX.1 Kontext) at `STABLE_DIFFUSION_URL`. `edit_image` shrinks the photo to `STABLE_DIFFUSION_SIZE` on its long side (multiples of 8), passes the steps inside the prompt (`<sd_cpp_extra_args>`), posts it to `/v1/images/edits` one call at a time (the server draws one image at a time), retries busy or restarting servers with backoff (15 min timeout) and records one image at no cost. `check_connection` reads `/sdcpp/v1/models/status`, which does not wake the model (`/v1/models` does). Only coloring pages use it: captions, translations and covers stay on Gemini. |
| `core/usage.py` | One JSON line per call with input, output and thinking tokens and the estimated cost (`PRICING`; thinking tokens of image models at the text rate); `book_context(book_id)` attributes calls to a book; `summarize` and `breakdown` feed the usage panel and the sidebar. |
| `core/schema.py` | Pydantic models `Book`, `Page`, `Version`, `Crop`, `CoverArt` and the option tuples (`STYLES`, `AGE_GROUPS`...). |
| `core/books.py` | Book folders under `books/`, `book.json`, slugs (accents folded), create/list/delete, `duplicate_book`, and `export_zip`/`import_zip` (a book as a ZIP without its exports; imports become new books, and entries outside the book layout are ignored). |
| `core/pages.py` | `pages.json`; photo ingestion (EXIF rotation, HEIC, 2048 px), crop, versions (`add_version`, `select_version`, `approve`), order, deletion, thumbnails. |
| `core/imaging.py` | Prompt pieces (`STYLE_PROMPTS`, `AGE_PROMPTS`, `BACKGROUND_PROMPTS`), `build_prompt`, aspect ratio from the photo; Stable Diffusion's short English prompt (`SD_STYLE_PROMPTS`, `SD_AGE_PROMPTS`, `SD_BACKGROUND_PROMPTS`, `build_sd_prompt`); `render_page` (run an engine and clean the result), `convert_page` (render and store as a new version) and `convert_pages` (many pages, three Gemini calls at a time or one at a time for the other engines, stored from the calling thread). `AI_ERRORS` is what a failed AI conversion raises, whichever engine. |
| `core/lineart.py` | The black-and-white guarantee (`clean`) and the offline draft engine (`draft`). |
| `core/grouping.py` | Color grouping after the tone curve: mean shift (`pyrMeanShiftFiltering`) with one setting, the bandwidth (color radius); at most 1200 px, cached by what the photo was made from. |
| `core/tones.py` | Tone curves for a page's photo, like GIMP's Curves: `lut` (control points joined by a monotone cubic, flat beyond the end points, which are the black and white points), `apply`, `histogram` for the editor, `PRESETS`. |
| `core/background.py` | Background removal for mosaics with SAM2 (2.1 base-plus through `transformers`, CPU): `subject_mask` (the subject from the author's points, cleaned, cached in `masks/`; computed on the photo without its tone curve, so moving the curve never cuts again), `clicked`, `outline` (the check image), `available`/`model_downloaded`. Imports torch only when a mask is computed. |
| `core/mosaic.py` | Mystery mosaics, the third engine: `make_grid` (photo → tones per cell or triangle), `render_solution` (1-bit), and the vector drawing of the puzzle, its legend and the solution. Settings per age group, book or page (`settings_for`). |
| `core/export.py` | `preflight` (what the PDF will contain, captions that overflow, extras the pages cannot make), `sheets` (every interior page in print order) and `export_book_pdf`. |
| `core/extras.py` | The extra pages: color test, word search, maze, connect-the-dots, solutions, diploma, closing page. Generated, never drawn by the AI, seeded with the book id; `available` says which ones the pages can make. |
| `core/captions.py` | Text from the text model: `translate` (a caption into the book's second language) and `suggest_listing` (the Amazon description, keywords, categories, reading age). |
| `core/commons.py` | Wikimedia Commons: `lookup` (author, license, link of a file page, license mapped to the app's), `download`, `add_page`. |
| `core/templates.py` | Kinds of book: default background and the info labels the workbench inserts. |
| `core/marketing.py` | Listing images: builds the interior and cover into a temporary folder, renders them with pdfium and composes a 3D mockup, a look inside and the front cover. |
| `core/kdp.py` | Amazon KDP numbers (trims, page ranges, spine, cover size, printing cost, royalty) and `review`, which measures a book against them. The numbers and their sources are in [amazon-kdp.md](amazon-kdp.md); update both together. |
| `core/cover_art.py` | Color front-cover images, versioned under `cover_art/`: `add_upload`, `generate` (the AI, from a collage of pages, a description or the book's theme), `select`, and `to_cmyk`. |
| `core/cover.py` | `export_cover_pdf`: the KDP wraparound cover (back, spine, front) in CMYK. |
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
                                  (mosaic versions: v<n>-raw.png is the grid, v<n>.png the solution)
  masks/<page-id>-<hash>.png      SAM2 subject masks, a cache keyed by crop, point and model
  cover_art/v<n>.jpg              front cover image, uploaded or drawn by the AI (RGB)
  exports/<slug>-<timestamp>.pdf  one file per build, never overwritten
  exports/covers/<slug>-cover-<pages>p-<timestamp>.pdf
                                  KDP cover, sized for an interior of <pages> pages
  exports/marketing/<slug>-images-<timestamp>.zip
                                  listing images: mockup, look inside, front cover
```

A page's status moves `pending → converted → approved`; a new version or switching versions puts
it back to `converted`. The author can delete a version from the workbench, after a confirmation
(`pages.delete_version`): its files go, its number is never given again (`Page.last_version`), and
when it was the selected one the newest remaining version is selected (`converted`), or the page
goes back to `pending` when none is left. Versions are numbered and never overwritten, and neither are cover images
(`Book.cover_art`, with `cover_art_selected` naming the one the front uses, or `None` for line art). Usage is attributed by book
id, not slug, because a deleted book's slug can be reused.

## Pipelines

### Conversion (`imaging.convert_page`)

1. Crop the original photo and apply its tone curve, if any (`pages.cropped_photo`; the curve is
   `Page.curve`, stored as points and never baked into the photo, and recorded on each version).
   The workbench edits it next to the crop with a static HTML component (`ui/curve_editor.py`):
   click adds a point, drag moves it, right click or double click removes it.
   Then, when the page has one (`Page.group`, the bandwidth), the color grouping: mean shift
   merges neighboring pixels of similar color into flat areas, at most 1200 px on the long side
   (it takes 1–3 s there, so the result is cached by photo, crop, curve and bandwidth). The PDF's
   reference photo and the cover collage use the curve but not the grouping, which is for the
   engines; the version records both.
2. **AI engine**: build the prompt from the style, the age group, the background, the page title
   (it names the subject) and the author's instructions; send the photo as the reference image
   with the closest supported aspect ratio (`3:4`, `1:1`, `4:3`) at `2K` (1792 × 2400 for `3:4`).
   **Draft engine**: mean shift + k-means flatten the photo into a few color areas and their
   borders become the lines, so every area is closed. Free, deterministic, and not a drawing.
3. `lineart.clean` the result and store raw + clean as the next version, selected.

`convert_pages` runs step 1–2 for many pages in a thread pool (three AI calls at a time; the
draft engine one at a time) and stores each result from the calling thread as it arrives, so
`pages.json` is never written by two threads. `usage.book_context` is process-wide, so it is set
once around the pool.

### Mystery mosaics (`mosaic`)

The third engine, offline and free. The cropped photo is turned to gray, its tones spread by a
blend of a 1–99 percentile stretch and histogram equalization (`EQUALIZE`; a plain stretch leaves
most photos in the middle tones), then the author's contrast and brightness. Each cell is measured
on 8 × 8 samples and gets one of 2–5 tones (0 is black). With diagonal cells, a cell is split
along "/" or "\" when its two triangles cut the squared error to `SPLIT_GAIN` of the whole cell's
and get different tones, so flat areas stay square and edges get a diagonal.

The grid is stored as an RGB PNG, one pixel per cell (tone of the cell or first triangle, tone of
the second triangle, split), and `v<n>.png` is the solution rendered through pdfium and dithered
to 1 bit; `lineart.clean` is skipped. Settings: the page's, else the book's ("Use for the whole
book"), else `AGE_DEFAULTS`; each version records the ones it was made with. The options panel
previews the mosaic the current settings make (`imaging.mosaic_draft`, cached in the UI by the
saved book and page) before anything is stored, and can save it as a new version or replace the
selected mosaic version (`convert_page(..., replace=n)`: store, then delete `n`, so the
replacement takes the next number).

In the PDF a mosaic page has no title, caption or photo: "Mystery N", the instructions, the grid
and a number per cell or triangle in light gray vectors (none on white cells unless
`number_white`, so the finished picture has no stray digits), and a legend (number → pencil gray,
or a pattern from one of `mosaic.PALETTES`: four patterns from darkest to lightest, always
starting with solid, of which `patterns` picks as many as the tones need, then white). Patterns are
stroked over the whole grid, clipped to the shapes of their tone; dots, dashes and checkers are
dashed lines, whose dash restarts on each row, so shifting a row staggers them. `export.sheets` adds `mosaic_solutions:<i>`
sheets (six per page, filled in, with number and title) after the activities, before the diploma
and closing page. Mosaics are left out of the word search and the connect-the-dots.

**Background removal.** With `remove_background`, `background.subject_mask` asks SAM2 for the
subject from the page's `points` (percent of the cropped photo; with no subject point, the middle
is one). The author adds them by clicking the photo in the workbench (`ui/point_picker.py`, a
static HTML component: left click subject, right click or Shift+click background, a click on a
point removes it; `background.clicked` decides, and keeps the middle point shown before the first
click). Each subject
point is a SAM2 call of its own with every background point as a negative, and the masks are
joined: prompting two birds as one object made SAM2 mix them up, while one call per point keeps
both whole. A single point takes the best of three masks by predicted IoU. The joined mask drops
specks under 1% of it and fills its holes. `make_grid` then measures the tone range on the subject's pixels alone and
blends every sample toward white by the share of background under it, so the background is white
cells (without numbers) and the subject's edge follows the mask. On a CPU the model loads in about
20 s once per process and takes 2–3 s per photo, hence the mask cache. The model's weights are in
`models/huggingface` (`HF_HOME`); torch is the CPU build, from PyTorch's CPU index.

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

ReportLab canvas, Letter, A4, 8 × 10 in or 8.5 × 8.5 in, Andika (SIL) as the typeface. `sheets` lists the pages in print
order and both the builder and the KDP page count use it: a title page with the cover page's line
art; a copyright page on its back (the book's `legal` text and the pages' photo `credit`s, printed
only when there is one or the other); the optional owner page; then one sheet per included page:
line art in the top box, and an info box (rounded rectangle) with the cropped reference photo and
the caption. Caption text shrinks in steps until it fits, otherwise it is clipped to the box
(`preflight` lists those pages). Optional blank back after every sheet, so every drawing is a
right-hand page.

Line art is embedded as 8-bit grayscale with lossless compression, so it stays pure 0/255. Where it
would print below 300 ppi (a full-page drawing), it is upsampled with Lanczos and thresholded again,
which keeps curves smooth and pixels pure. Photos are bounded JPEGs. Every font is embedded: the
canvas is created with `initialFontName`, because ReportLab otherwise references Helvetica on every
page, which is never embedded and makes KDP reject the file.

### Extra pages (`extras`)

`export.sheets` asks `extras.available` which of the book's extras the pages can make and puts
them in a fixed order: the color test after the owner page; word search, maze, connect-the-dots
and solutions after the coloring pages; then the diploma and the closing page. Puzzles are seeded
with the book id, so every export draws the same ones and the solutions match.

- **Word search**: the longest word of each page title, uppercased without accents (Ñ kept),
  on a grid of 8 to 16 cells with the directions the age group allows.
- **Maze**: a perfect maze carved depth-first, solved by breadth-first search for the solutions.
- **Connect-the-dots**: the subject's silhouette is what the white background cannot reach from
  the border; it is smoothed (opening and closing remove thin spikes and notches), the outline is
  erased from the drawing, and dots are spaced evenly along it, clockwise from the top. Only
  drawings with no background are used unless the author picks one: in a scene the outline runs
  through the background.

### Bilingual captions

`Book.languages` is the book's language plus the second one, if any. The caption box prints the
page's `translation` under its caption (smaller, muted, subtitle once), and fixed labels come from
`i18n.t_all`. `captions.translate` asks the text model for a `Caption` and never invents content.

### KDP cover (`cover.export_cover_pdf`)

The page count comes from `export.sheets`, so the cover matches the interior built from the same
settings, and it is written into the file name (the KDP view warns when it no longer matches). The
size, spine and barcode box come from `kdp`. Back, spine and front are drawn on one CMYK page: a
background color, white text, and the line art in white panels converted to CMYK with black on the
K plate only (a plain RGB→CMYK conversion would print black as four inks). With a cover image, the
front is that image cropped to fill the front and its bleed, converted with `cover_art.to_cmyk`
(full black generation, no press profile) and embedded as a CMYK JPEG, under rounded labels for the
title and the dedication. Spine text only from 79 pages and when it fits at 5 pt or more.

`cover_art.to_cmyk` converts through Ghostscript's CMYK press profile (`libgs-common` in the
image) with LittleCMS, perceptual intent, which keeps colors closer and the total ink near 300%;
`plain_cmyk` is the fallback when the profile is missing.

### Cover art (`cover_art.generate`)

The prompt depends on the mode: a **collage** sends each chosen page's line art and photo as a pair
of references and asks for the subjects redrawn together and colored in with outlines visible; a
**description** sends only the text; the **theme** sends the title, subtitle and every page title.
All three ask for no text (the app sets the title, so it is always spelled right), a calm top
quarter for the title label, and a full-bleed portrait image. The image is drawn at `3:4` in `4K`
(3584 × 4800), stored as `cover_art/v<n>.jpg` and selected. It is not cleaned: it is not a coloring
page.

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

## Security

The app has no login: it is a single-user tool for one computer. What keeps it safe:

| Risk | Measure |
|---|---|
| Others on the network using the app (photos, Gemini credit) | Compose publishes the port on `127.0.0.1` only; `COLORIN_BIND` opens it on purpose. |
| The API key leaking from the UI | The Settings field never receives the saved key; an empty field keeps it. |
| A book ZIP from someone else reaching outside its folder | Names that become paths (`Book.slug`, `Page.id`, `Page.original`) must match the patterns in `schema.py`, and `books.inside` checks every page path stays in its book; archive entries outside the book layout are skipped, and their total size is capped. |
| Text from a book (titles, captions) turning into markup | The UI escapes Markdown with `ui.common.plain`; every user string in the PDF goes through `escape` or `plain_markup`, since ReportLab paragraphs read tags like `<img src>`. |
| Secrets in git or in the image | `config/.env` and the Compose override are git-ignored; `.dockerignore` keeps them and the user data out of the image. |
| Vulnerable dependencies | Pinned versions, audited with `pip-audit` on 2026-10-31 (none known); Dependabot proposes updates for pip, Docker and the dev container. |

Not covered: the photos and captions sent to Gemini are processed by Google under the terms of the
chosen access (Vertex AI or AI Studio).

## Differences from the plan

| Plan | Built | Why |
|---|---|---|
| Draft engine: bilateral filter + adaptive threshold | Color-area segmentation | Edge detectors left loose strokes with no closed areas to color. |
| Crop in phase 2 | Crop in the MVP workbench | The spike showed small subjects stay small; cropping is the fix. |
| Blank backs in phase 3 | In the MVP | One `showPage()` per sheet. |
| No print-on-demand in v1 | Amazon KDP files and checks | Selling the books on Amazon became a goal; see [amazon-kdp.md](amazon-kdp.md). |
| Never draw from text | Cover art may be drawn from text | The front cover is a color illustration, not a coloring page. |
| Vertex AI with ADC only | ADC or an API key | Not everyone has a Google Cloud project. |
| Convert all pending in phase 2 | Done, with three AI calls at a time | Converting a 50-page book one by one took too long. |
| More styles and templates in phase 3 | Kawaii, mandala, an adult level, and four kinds of book | Asked for after the MVP. |
| AI caption suggestions in phase 2 | Translations and the Amazon listing only | Suggesting facts risks inventing them; translating and describing what is there does not. |
| Thicken lines to the age group's width | Thicken step by step, stop before areas merge | Growing dense drawings to the 3–5 width turned them into black blobs. |
