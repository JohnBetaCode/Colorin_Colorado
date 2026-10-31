# Colorín Colorado — plan

> *"Colorín colorado, este cuento se ha acabado."* The Spanish line that closes a children's story,
> the way *Once Upon a Time* opens one.

Turn your own photos into a printable coloring book for kids. Upload a set of photos, convert them
one by one into black-and-white line art in the style you choose, write a short caption about what
each page shows, and export a print-ready PDF where every coloring page carries a small color
reference photo and an info box.

Sibling project of [Once Upon a Time](https://github.com/JohnBetaCode/Once_Upon_a_Time): same
stack, same conventions, and as much of its code as fits.

## Goals

1. **Upload** a batch of photos into a book. Each photo becomes one page.
2. **Convert page by page** in a workbench: original on the left, coloring page on the right;
   convert, compare versions, regenerate with extra instructions, approve, move to the next one.
3. **Pick a style** for the book (realistic or cartoon; kawaii and mandala came later) and an age group. Whatever the style, the
   output is always pure black outlines on white, ready to color.
4. **Caption every page**: a title, an optional subtitle and a short text the user types (later,
   suggested by AI and edited by the user).
5. **Export the book as a PDF**: cover, "this book belongs to" page, and one coloring page per
   sheet with the color reference photo and the caption in a box at the bottom.

**Not in v1:** accounts or multi-user, public hosting, coloring pages generated from text only
(there is always a source photo), mobile layout. Print-on-demand was out of v1 too; Amazon KDP files
came right after the MVP (see Decisions).

## Example books

| Book | Photo | Style | Info box |
|---|---|---|---|
| Birds of the rainforest | A toucan on a branch | Realistic | Name, scientific name, where it lives, one fun fact |
| Famous landmarks | A church on a bridge over a canyon | Cartoon | Small real photo, what you are coloring, where it is |
| Family album | The dog at the park | Cartoon | Name and a line about the day |

## What we reuse from Once Upon a Time

| Once Upon a Time | Here | Notes |
|---|---|---|
| `core/config.py` | As is | Same `config/.env` keys; can point at the same GCP project. |
| `core/gemini.py` | Adapt | Keep `generate_image` (reference images + aspect ratio), `extract_structured`, `web_research`; add image inputs to the text calls for captions. |
| `core/usage.py` | As is | Same `PRICING` table and per-project attribution (per book here). |
| `core/projects.py` | Adapt | `books/<slug>/book.json` instead of `projects/<slug>/project.json`. |
| `core/thumbnails.py` | Adapt | Home-page collage from approved coloring pages. |
| `core/export.py` | Rewrite | New layout; keep its helpers (DejaVu Sans, bounded JPEG re-encode, footer, `splitInRow`). |
| `core/imaging.py` | Rewrite | Coloring-page prompts instead of character sheets. |
| Dockerfile, compose, devcontainer, dependabot | Copy | Port **8502** so both apps can run side by side. |
| Skills `run-app`, `screenshots`, `usage-report` | Copy and adapt | Phase 1 ships `run-app`; the rest in phase 2. |

New modules: `core/lineart.py` (black-and-white guarantee), `core/pages.py` (pages, versions,
order), `core/captions.py` (AI caption suggestions, phase 2).

## Stack

Python 3.12, Streamlit, `google-genai` on Vertex AI with Application Default Credentials (or an API key),
Pydantic 2, Pillow (+ `pillow-heif` for iPhone photos), OpenCV headless + NumPy for the line-art
cleanup, ReportLab for the PDF, Docker Compose. No database: one folder of JSON and images per
book, as in Once Upon a Time.

## User flow

1. **Home.** List of books with a thumbnail and progress (`7/12 approved`). *New book* asks for
   title, subtitle, dedication/author, style, age group, page size and the book language
   (defaults to the current UI language).
2. **Upload.** Drag and drop many photos (JPG, PNG, WebP, HEIC). Each one becomes a page in upload
   order. EXIF rotation is applied and the photo is downscaled to 2048 px on the long side.
3. **Workbench**, one page at a time:
   - Left: the original photo. Right: the selected coloring version, with a strip of earlier
     versions to switch between.
   - Controls: style (inherit from the book or override), background (*keep*, *simplify*,
     *remove*), extra instructions ("only the bird, not the branch"), **Convert** /
     **Regenerate**, **Approve**.
   - Caption: title, subtitle, info text (and, in phase 2, **Suggest with AI**).
   - Navigation: previous / next, `page 3 of 12`, status chip (*pending*, *converted*,
     *approved*), and **Approve and next** for a fast pass through the book.
4. **Pages.** Grid of every page with its status: reorder, exclude from the book, delete, choose
   the cover page.
5. **Export.** Layout options, build, inline preview (`st.pdf`) and download. Every build is a new
   file; nothing is overwritten.

## Languages

The app speaks **Spanish and English**, with a switch in the sidebar. There are two separate
settings:

- **UI language**: the language of the app itself. Saved as `UI_LANGUAGE` in `config/.env`
  (`es` by default), so it survives restarts.
- **Book language** (`Book.language`): the language of the book's fixed PDF labels ("Este libro
  pertenece a" / "This book belongs to") and of AI caption suggestions. A new book starts with the
  current UI language, and you can change it, so a Spanish UI can produce an English book.

Every user-facing string goes through `core/i18n.py`: a `STRINGS` table with an `es` and an `en`
entry per key, and `t(key, **params)`. The UI modules contain no hard-coded user-facing text, and
a test fails if any key is missing either language. Captions typed by the user are stored as typed;
there is no translation. Prompts sent to Gemini stay in English.

## Styles

Two knobs, independent of each other:

**Style** (book default, per-page override)

| Key | Intent |
|---|---|
| `realistic` | Field-guide line drawing traced from the photo: accurate proportions, characteristic markings drawn as outlined regions, medium-to-high detail. The default for educational books. |
| `cartoon` | Friendly *caricatura*: simplified rounded shapes, expressive eyes when the subject has a face, thick even outlines, fewer and bigger areas. |

Later: `kawaii`, `mandala` (subject filled with decorative patterns, for older kids and adults).

**Age group** controls line weight and how many regions there are to color:

| Age | Lines | Detail |
|---|---|---|
| 3–5 | Very thick | Main shape only, a handful of big areas, no background |
| 6–8 | Thick | Main features, simple background |
| 9+ | Medium | Full detail, textures as outlined regions |

**Rules appended to every prompt**, whatever the style:

- Pure black outlines on a pure white background.
- No shading, gray, gradients, hatching or solid black fills (small details like pupils excepted).
- Closed shapes, so every region can be colored.
- The reference photo is the subject: same species/building/person, pose, proportions and
  distinctive markings. A toucan stays recognisably a toucan in cartoon style too.
- No text, letters, signatures, watermarks or frames.
- Portrait composition (3:4), subject centered with a margin.

## The black-and-white guarantee

The model output is never trusted to be pure black and white. `lineart.clean()` runs on every
result and keeps both files (`raw` and `clean`):

1. Convert to grayscale.
2. Threshold (Otsu) to 1-bit: every pixel ends up pure black or pure white.
3. Remove specks smaller than a few pixels (connected components).
4. Normalize line thickness to the age group (dilate when lines are too thin).
5. Crop to content and pad to the page aspect.
6. Save as a 1-bit PNG: sharp at 300 DPI and tiny on disk.

**Quality warnings** shown next to the result: too much black (big filled areas are bad for
coloring), too few regions, subject touching the edge. They suggest regenerating; they never block.

**Draft engine (offline, free).** An OpenCV edge pipeline (bilateral filter + adaptive threshold)
gives an instant, lower-quality preview with no API call. Useful for laying out a book before
spending money, and to test the whole pipeline without GCP credentials.

## Data model

```
books/<slug>/                       git-ignored, bind-mounted into the container
  book.json                         Book
  pages.json                        list[Page], in book order
  originals/<page-id>.jpg           uploaded photo (rotated, downscaled)
  lineart/<page-id>/v1-raw.png      model output, untouched
  lineart/<page-id>/v1.png          1-bit cleaned coloring page
  exports/<slug>-<timestamp>.pdf    one file per build
```

Pydantic models (`core/schema.py`):

- **Book**: `id, slug, title, subtitle, dedication, style, age_group, page_size (letter | a4),
  layout (bottom_box | facing_pages), language (es | en), include_reference_photo,
  include_owner_page, blank_backs, cover_page_id, created_at, updated_at`.
- **Page**: `id, original, original_name, title, subtitle, info, style (null = inherit book),
  background (keep | simplify | remove), instructions, versions, selected_version,
  status (pending | converted | approved), in_book`.
- **Version**: `n, engine (gemini | draft), style, age_group, prompt_hash, raw, clean, warnings,
  created_at`.

Versions are never overwritten; regenerating adds `v2`, `v3`... and selects the newest.

As built, `Book` has no `layout` yet (facing pages are phase 3) and has a default `background`;
the page's version is `Page.selected`; `Version` keeps its `background` and `instructions` but no
prompt hash or file names (they follow from `n`); and the *New book* form asks for title, subtitle,
style, age group and language only (dedication is in ✏️ Edit book, page size in 📄 Export PDF). After the MVP, `Book` gained the copyright page text
(`legal`), the KDP settings (`kdp_ink`, `list_price`, `cover_color`, `back_text`) and its cover
images (`cover_art`, `cover_art_selected`), and `Page` gained `crop` and the photo `credit`. See
`app/core/schema.py`.

## PDF layout

Letter (8.5 × 11 in, the usual home paper in the Americas and the usual Amazon KDP size for
coloring books) by default, A4 as an option. Line art is placed at 300 DPI or more; reference
photos are re-encoded as bounded JPEGs to keep the file small.

1. **Cover** (the title page in a KDP paperback, whose real cover is a separate file): title,
   subtitle, the chosen cover page as line art (the cover can be colored too), dedication/author.
   On its back, the **copyright page** with the photo credits, when there is either.
2. **Owner page** (optional): "Este libro pertenece a: ______" in a simple frame.
3. **Coloring pages**, one per sheet:

```
┌──────────────────────────────┐
│                              │
│                              │
│      coloring line art       │   ~72% of the height
│                              │
│                              │
│ ╭──────────────────────────╮ │
│ │ ┌───────┐  TITLE         │ │
│ │ │ photo │  subtitle      │ │   info box ~22%, rounded border
│ │ └───────┘  info text ... │ │
│ ╰──────────────────────────╯ │
│              7               │
└──────────────────────────────┘
```

   Caption text shrinks to fit the box (down to 9 pt); if it still does not fit, the export panel
   warns before building. A page with no caption and no photo gives the line art the whole sheet.
4. **Blank backs** (optional): a blank page after each coloring page, so the book can be printed
   double-sided (as KDP always does) without markers bleeding into another drawing.
5. **Facing pages** (phase 3): left page shows the large color photo and the caption, right page
   the coloring page, for duplex printing and binding.

Fixed labels ("Este libro pertenece a" / "This book belongs to") follow the book `language`.

## AI captions (phase 2)

**Suggest with AI** on a page: the text model receives the original photo, the page title (if
any) and the book title as context, with Google Search grounding, and returns a validated
`Caption {title, subtitle, info}` in the book's language, written for kids, within a word limit.
Same rule as Once Upon a Time: nothing invented. If it cannot identify the subject it says so and
returns the title only. The user always edits and saves; the suggestion never overwrites typed text
without confirmation.

## Costs

One conversion is one image generation (`gemini-3-pro-image`, about $0.14 per image; the
[spike](spike.md) logged $0.17 before thinking tokens were priced at the text rate). A 20-page book
at ~1.5 attempts per page is ~30 images, about **$4**. A 4K cover image is about $0.25. Caption
suggestions cost cents. The draft engine is free. Every call is recorded in `data/usage.jsonl` and
attributed to its book, as in Once Upon a Time.

## Phases

**Phase 0: plan and repository.** Done.

**Phase 1: MVP.** Done on 2026-10-30; [architecture.md](architecture.md) lists where it differs.

1. Scaffold from Once Upon a Time: config, Gemini client, usage, Docker on port 8502, plus
   `core/i18n.py` and the language switch.
2. **De-risk first:** a throwaway script converts 5 test photos (bird, landmark, pet, person, busy
   scene) in both styles and all three age groups, then runs the cleanup. Tune the prompts until
   the outputs are clean, closed-shape line art. The whole product rests on this, so it happens
   before any UI. Done: see [spike.md](spike.md).
3. Schema and storage: books, pages, versions; upload with EXIF rotation, HEIC and downscaling.
4. `lineart.clean()`, quality warnings and the draft engine.
5. Workbench: crop, convert, regenerate with instructions, versions, approve, captions, prev/next.
6. Pages grid: order, exclude, delete, cover.
7. PDF export: cover, owner page, bottom-box layout, Letter/A4, inline preview, download.
8. Docs (`README.md`, `docs/architecture.md`, `docs/setup.md`), `CLAUDE.md`, `run-app` skill.

**Phase 2**

- AI caption suggestions (translations and the Amazon listing shipped; suggesting facts did not).
- ~~**Convert all pending** with a progress bar~~: done 2026-10-31, three AI calls at a time.
- ZIP of the PNG pages; delete single versions. (A ZIP of the whole book shipped instead.)
- `screenshots` and `usage-report` skills.

(Home thumbnails, the usage panel and the README sample pages shipped in phase 1.)

**Phase 3**

- Facing-pages layout (blank backs shipped in phase 1).
- ~~More styles (`kawaii`, `mandala`)~~: done 2026-10-31, with an adult level.
- ~~Book templates with predefined caption fields~~: done 2026-10-31 (nature, landmarks, family).
- Print-shop export: bleed and crop marks.

**After the MVP (2026-10-31)**

- Amazon KDP: interior to KDP's specs, copyright page with photo credits, cost and royalty,
  pre-upload checklist, wraparound cover ([amazon-kdp.md](amazon-kdp.md)).
- Front cover image: uploaded, or drawn by the AI from a collage of pages, a description or the
  book's theme.
- Gemini by API key (Vertex AI or Google AI Studio) besides Google Cloud credentials.
- Tokens shown next to the cost, per book and in total.
- Convert all pending pages; Wikimedia Commons photos with their credit; photo licenses checked.
- Extra pages: color test, word search, maze, connect-the-dots, solutions, diploma, closing page.
- Bilingual books with AI translation; Amazon listing drafted by AI; listing images.
- KDP costs for the UK and EU stores; 8 × 10 and square trims; CMYK through a press profile.
- Templates, kawaii and mandala styles, an adult level.
- Duplicate a book; export and import it as a ZIP; credentials mounted only when used.

## MVP acceptance criteria

- Create a bird book, upload 10 photos, convert and approve each one, type captions, export
  a Letter PDF.
- Every coloring page in the PDF contains only pure black and pure white pixels (checked by a test
  over the exported images).
- Each coloring page shows the reference photo and the caption box; long text never overflows.
- Restarting the container keeps every book, page, version and export.
- The cost of each conversion is visible in the app.
- Switching the UI language changes every label in the app, and an English book exports with
  English labels from a Spanish UI.

Checked on 2026-10-30 by the test suite (pure black and white in the exported PDF, labels in both
languages, captions that do not fit are reported and clipped to the box) and by a Playwright run
through the UI with three photos, one AI conversion included. A full 10-photo book has not been
run end to end yet.

## Risks

| Risk | Mitigation |
|---|---|
| The model adds gray shading or filled areas | Prompt rules + `lineart.clean()` thresholding + "too much black" warning |
| Cartoon style loses what makes the subject recognizable (species markings) | The photo is always the reference image; `realistic` is the default for educational books |
| Photos of children trigger safety filters or person-generation limits in Gemini | Spike tests a person photo first; draft engine as fallback; clear error in the UI |
| Big PDFs | 1-bit PNGs compress very well; reference photos are bounded JPEGs |
| Privacy of family photos | Everything stays local in `books/` (git-ignored); only the photo being converted is sent to Gemini |

## Decisions

- **2026-10-30, UI language:** Spanish and English, switchable (see [Languages](#languages)).
- **2026-10-30, name:** *Colorín Colorado*.
- **2026-10-30, repository visibility:** private.
- **2026-10-31, Amazon KDP:** the books are meant to be sold as paperbacks on Amazon. The interior
  PDF follows KDP's specs (embedded fonts, 300 ppi, margins, copyright page with photo credits), and
  a new view estimates cost and royalty, lists what to fix and builds the wraparound cover. See
  [amazon-kdp.md](amazon-kdp.md).
- **2026-10-31, place-neutral:** the product, its docs and its examples name no country or city;
  the author's own books can be about any place.
- **2026-10-31, cover art:** the KDP front cover can carry a full-color image, uploaded or drawn by
  the AI, even from text alone. It is the one image that skips `lineart.clean` and the "always from
  a photo" rule: it is not a coloring page.
- **2026-10-31, API keys:** Gemini can be reached with an API key (Vertex AI express or Google AI
  Studio), for people without a Google Cloud project.
- **2026-10-31, activities are generated, not drawn:** word searches, mazes and connect-the-dots
  come from code and the book's own pages, seeded with the book id: reproducible, free, and the
  solutions always match. The AI is not asked to draw puzzles.
- **2026-10-31, AI text only from what is there:** the text model translates captions and
  describes the book for Amazon; it is not asked for facts about the subjects.
