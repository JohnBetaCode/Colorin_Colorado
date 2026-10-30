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
3. **Pick a style** for the book (realistic or cartoon) and an age group. Whatever the style, the
   output is always pure black outlines on white, ready to color.
4. **Caption every page**: a title, an optional subtitle and a short text the user types (later,
   suggested by AI and edited by the user).
5. **Export the book as a PDF**: cover, "this book belongs to" page, and one coloring page per
   sheet with the color reference photo and the caption in a box at the bottom.

**Not in v1:** accounts or multi-user, public hosting, print-on-demand integrations, coloring pages
generated from text only (there is always a source photo), mobile layout.

## Example books

| Book | Photo | Style | Info box |
|---|---|---|---|
| Birds of Colombia | A toucan on a branch | Realistic | Name, scientific name, where it lives, one fun fact |
| Famous places of Colombia | Caño Cristales | Cartoon | Small real photo, what you are coloring, where it is |
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

Python 3.12, Streamlit, `google-genai` on Vertex AI with Application Default Credentials,
Pydantic 2, Pillow (+ `pillow-heif` for iPhone photos), OpenCV headless + NumPy for the line-art
cleanup, ReportLab for the PDF, Docker Compose. No database: one folder of JSON and images per
book, as in Once Upon a Time.

## User flow

1. **Home.** List of books with a thumbnail and progress (`7/12 approved`). *New book* asks for
   title, subtitle, dedication/author, style, age group, page size and the language of the PDF
   labels.
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
  layout (bottom_box | facing_pages), labels_language (es | en), include_reference_photo,
  include_owner_page, blank_backs, cover_page_id, created_at, updated_at`.
- **Page**: `id, original, original_name, title, subtitle, info, style (null = inherit book),
  background (keep | simplify | remove), instructions, versions, selected_version,
  status (pending | converted | approved), in_book`.
- **Version**: `n, engine (gemini | draft), style, age_group, prompt_hash, raw, clean, warnings,
  created_at`.

Versions are never overwritten; regenerating adds `v2`, `v3`... and selects the newest.

## PDF layout

Letter (*carta*, what people print on in Colombia) by default, A4 as an option. Line art is
placed at 300 DPI; reference photos are re-encoded as bounded JPEGs to keep the file small.

1. **Cover:** title, subtitle, the chosen cover page as line art (the cover can be colored too),
   dedication/author.
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
4. **Blank backs** (optional): a blank page after each coloring page, for single-sided printing so
   markers do not bleed through.
5. **Facing pages** (phase 3): left page shows the large color photo and the caption, right page
   the coloring page, for duplex printing and binding.

Fixed labels ("Este libro pertenece a", page numbers) follow `labels_language`, Spanish by default.

## AI captions (phase 2)

**Suggest with AI** on a page: the text model receives the original photo, the page title (if
any) and the book title as context, with Google Search grounding, and returns a validated
`Caption {title, subtitle, info}` in the book's language, written for kids, within a word limit.
Same rule as Once Upon a Time: nothing invented. If it cannot identify the subject it says so and
returns the title only. The user always edits and saves; the suggestion never overwrites typed text
without confirmation.

## Costs

One conversion is one image generation (`gemini-3-pro-image`, about $0.13 per image at the current
`PRICING`). A 20-page book at ~1.5 attempts per page is ~30 images, about **$4**. Caption
suggestions cost cents. The draft engine is free. Every call is recorded in `data/usage.jsonl` and
attributed to its book, as in Once Upon a Time.

## Phases

**Phase 0: plan and repository** (this commit).

**Phase 1: MVP**

1. Scaffold from Once Upon a Time: config, Gemini client, usage, Docker on port 8502.
2. **De-risk first:** a throwaway script converts 5 test photos (bird, landmark, pet, person, busy
   scene) in both styles and all three age groups, then runs the cleanup. Tune the prompts until
   the outputs are clean, closed-shape line art. The whole product rests on this, so it happens
   before any UI.
3. Schema and storage: books, pages, versions; upload with EXIF rotation, HEIC and downscaling.
4. `lineart.clean()`, quality warnings and the draft engine.
5. Workbench: convert, regenerate with instructions, versions, approve, captions, prev/next.
6. Pages grid: order, exclude, delete, cover.
7. PDF export: cover, owner page, bottom-box layout, Letter/A4, inline preview, download.
8. Docs (`README.md`, `docs/architecture.md`, `docs/setup.md`), `CLAUDE.md`, `run-app` skill.

**Phase 2**

- AI caption suggestions.
- **Convert all pending** with a progress bar (synchronous, like Once Upon a Time).
- Home thumbnails, usage panel, ZIP of the PNG pages.
- `screenshots` and `usage-report` skills; README with sample pages.

**Phase 3**

- Facing-pages layout and blank backs.
- More styles (`kawaii`, `mandala`).
- Book templates with predefined caption fields (birds: name, habitat, fun fact; places: city,
  region, why it is famous).
- Print-shop export: bleed and crop marks.

## MVP acceptance criteria

- Create "Aves de Colombia", upload 10 photos, convert and approve each one, type captions, export
  a Letter PDF.
- Every coloring page in the PDF contains only pure black and pure white pixels (checked by a test
  over the exported images).
- Each coloring page shows the reference photo and the caption box; long text never overflows.
- Restarting the container keeps every book, page, version and export.
- The cost of each conversion is visible in the app.

## Risks

| Risk | Mitigation |
|---|---|
| The model adds gray shading or filled areas | Prompt rules + `lineart.clean()` thresholding + "too much black" warning |
| Cartoon style loses what makes the subject recognizable (species markings) | The photo is always the reference image; `realistic` is the default for educational books |
| Photos of children trigger safety filters or person-generation limits on Vertex AI | Spike tests a person photo first; draft engine as fallback; clear error in the UI |
| Big PDFs | 1-bit PNGs compress very well; reference photos are bounded JPEGs |
| Privacy of family photos | Everything stays local in `books/` (git-ignored); only the photo being converted is sent to Vertex AI |

## Open decisions

- **UI language:** Spanish, English, or both. PDF labels default to Spanish either way.
- **Repository visibility:** created private; switch to public when there is something to show.
- **Name:** *Colorín Colorado* unless there is a better one.
