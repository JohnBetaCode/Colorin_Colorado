# Features

Everything Colorín Colorado does, in short. The [user guide](usage.md) explains how to use each
part.

## What you get

- **Any photos.** JPG, PNG, WebP or HEIC straight from the phone, or a Wikimedia Commons link,
  which brings its author and license along.
- **Four styles, four ages, four kinds of book.** Realistic, cartoon, kawaii or mandala; line
  weight and detail follow the age group; templates for nature, landmarks and family albums
  suggest what each page says.
- **Convert the whole book at once**, or page by page in the workbench.
- **Tone curves** on each photo, like GIMP's Curves, with the histogram behind and before/after
  previews: they shape every conversion (a mosaic depends a lot on them) and the original photo
  stays untouched.
- **Color grouping** after the curve, with mean shift and a single bandwidth: texture turns into
  flat areas, so the mosaic and the draft see shapes.
- **Versions, never lost.** Every conversion is kept; pick the one you like, and delete the ones
  you don't want (after a confirmation).
- **A free draft mode** to lay out a book before spending anything.
- **Mystery mosaics** (monochrome color-by-number), free and offline: the photo becomes a faint
  grid with a number in each cell; filled in as the legend says (pencil tones, or one of four
  black-pen pattern palettes: classic, lines, stippling, geometric), the picture appears. White
  cells can go without a number, so the finished picture stays clean. Square cells or cells split diagonally,
  2 to 5 tones, the grid size and the contrast are adjustable; the page hides its title and photo,
  and the solutions are printed at the end of the book.
- **One-pen mosaics**: every cell gets one of six marks (■ ✳ ✕ \ / or nothing), and from a
  distance they blend into the photo, like a newspaper picture. The single strokes follow the
  photo's edges. The menu shows the real cell size and how long the page takes to draw.
- **Background removal for mosaics**, offline: a small model that runs on your computer keeps
  only the subject, frames the grid on it and leaves the rest as white paper.
- **Page templates**: a frame around every coloring page (double frame, stars, sky and grass,
  corner flowers, waves, lace), which can be colored too, for the whole book or page by page; or
  upload your own design, and the app finds where the drawing goes.
- **Activities from your own pages**: a word search with the book's words, a maze, a
  connect-the-dots traced from a drawing, their solutions, a color test page, a diploma and a
  closing page.
- **Bilingual books**: every caption in Spanish and English, translated by the AI and editable.
- **Photo credits**: each photo's author and license, printed on the copyright page.
- **A print-ready PDF**: title page, copyright page with the photo credits, "this book belongs
  to" page, one coloring page per sheet with the reference photo and caption, in Letter, A4,
  8 × 10 or square, with blank backs so markers never bleed into another drawing.
- **A printable cover**: back, spine and front in one PDF, with a color front image you upload or
  the AI draws from a collage of your pages, a description or the book's theme.
- **Spanish and English**, for the app and for each book.
- **Duplicate a book, or move it as a ZIP** to back it up or open it on another computer.
- **Your choice of access to Gemini**: a Google Cloud project, or just an API key.
- **A second engine, Stable Diffusion**: your own stable-diffusion.cpp server with FLUX.1 Kontext
  draws the coloring pages for no cost per image, one at a time, set up in the same Settings panel.
- **Costs in sight.** About $0.14 per AI conversion; the tokens and cost of every call are
  tracked per book and in total.

## Other notes

- **Development cost**: building this repository cost about **$8.64** in Gemini calls (54 calls,
  50 images, 137,355 tokens), mostly the line-art spike. The breakdown is in
  [development-cost.md](development-cost.md).
- **Printing and publishing**: [amazon-kdp.md](amazon-kdp.md) covers the print specs, covers and
  photo rights for print-on-demand.
