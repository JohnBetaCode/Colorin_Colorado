# User guide

## A book from start to finish

1. **Create the book** on the home page: title, subtitle, style, age group and book language.
   All of it, title included, can be changed later in **✏️ Edit book** (sidebar); the page size
   and the other print options are in **📄 Export PDF**.
2. **Add photos** in **🗂️ Pages → 📷 Add photos**. Select many at once; each becomes a page in the
   order you uploaded them.
3. **Convert in the 🎨 Workbench**, one page at a time:
   - **Crop** the photo first if the subject is small in it. The model keeps the photo's framing,
     so a dog in a corner of a lawn becomes a page full of grass.
   - **✨ Convert with AI** takes 30–40 seconds and costs about $0.14. **✏️ Free draft** is instant
     and free, but it only traces the photo's color areas: use it to lay out a book, not to print.
   - Not happy? Add **extra instructions** ("only the bird, not the branch", "remove the people in
     the back"), change the page's **style** or **background**, and regenerate. Every attempt is
     kept under **Versions**; pick the one you like.
   - Warnings under the page tell you when the cleanup had to fix something (copied colors, black
     fills, a photo of a printed page). They never block; regenerate if the result looks off.
   - **✅ Approve and next** moves to the next page.
4. **Write the caption** next to the photo: a title, a subtitle and an info text. They are
   printed in the box under the coloring page. Add the **photo credit** too.
5. **Export** in **📄 Export PDF**: choose the options, check the summary, **Build PDF**, preview
   it and download it.
6. **To sell it**, go to **🛒 Amazon KDP**: fix what it lists, pick or make the cover image, and
   build the cover ([Selling on Amazon](#selling-on-amazon)).

## Styles, ages and backgrounds

| Setting | Options | Effect |
|---|---|---|
| Style | Realistic, Cartoon | Field-guide drawing traced from the photo, or a friendly cartoon of the same subject. |
| Age | 3–5, 6–8, 9+ | Line weight and how many areas there are to color. 3–5 gets very thick lines and a few big areas. |
| Background | Keep, Simplify, Remove | Keep the setting, reduce it to a few shapes and zoom in on the subject, or draw the subject alone. |

Style and background are set per book and can be overridden per page. The age group is per book.
Changing any of them affects new conversions only.

## Captions

- **Title**: the name of what is being colored ("Tucán pico iris", "Palomas en la plaza").
  It also tells the model what the subject is, so write it before converting.
- **Subtitle**: a scientific name, a place, a date.
- **Info**: free text. A line that starts with a short label and a colon gets the label in bold:

  ```
  Dónde vive: bosques tropicales húmedos
  Dato curioso: su pico es enorme pero liviano
  ```

- **Photo credit**: who took the photo and its license ("My own photo", "Bernard Gagnon, CC0").
  Credits are printed on the copyright page, not under the drawing. A book for sale needs the right
  to use every photo: see [Rights to the photos](amazon-kdp.md#rights-to-the-photos).

The caption text shrinks to fit the box. If it still does not fit, the workbench and the export
summary warn you and the PDF cuts it at the edge of the box.

## Export options

| Option | Default | What it does |
|---|---|---|
| Page size | Letter | Letter (*carta*) or A4. |
| Cover | First page | Which coloring page goes on the title page, which is the cover when you print at home (also from **🗂️ Pages → Use as cover**). The KDP cover uses it too when it has no cover image. |
| Reference photo on every page | On | The small color photo in the info box. |
| "This book belongs to" page | On | A page for the child's name after the cover. |
| Blank back on every sheet | Off | For double-sided printing, so markers never bleed into another drawing. Turn it on for Amazon. |
| Copyright page | Empty | Text for the page behind the title page (© year and author, rights, ISBN), printed with the photo credits. With no text and no credits there is no copyright page. |

The fixed labels of the PDF follow the **book language**, not the app language: a Spanish app can
make an English book. Pages without a coloring page are skipped; pages not yet approved are
included and listed in the summary. Every build is a new file in `books/<slug>/exports/`.

## Selling on Amazon

**🛒 Amazon KDP** shows what Amazon's print-on-demand service would make of the book:

- **Interior ink** (black, standard color, premium color) and **list price**, with the page count,
  spine width, printing cost and royalty per copy on Amazon.com, and the lowest price KDP accepts.
- **Before uploading**: errors that block publishing (too few pages, a price under the minimum, an
  ink KDP does not offer in that size) and warnings (no blank backs, pages without a photo credit,
  no copyright text, pages not approved), plus the AI disclosure reminder.
- The settings to choose when uploading to KDP.
- **KDP cover**:
  - **Front cover image**: the cover page's drawing (uncolored), an image you upload (a portrait,
    full-color illustration without text, about 2600 × 3400 px to print sharp), or one the AI
    draws in 4K, about $0.25 each:
    - **A collage of pages**: pick up to six pages; the AI redraws them together and colors them
      in with the real colors of their photos.
    - **A description** you write.
    - **The book's theme**: the title, subtitle and page titles.

    Every image is kept as a version (v1, v2…); choose which one the front uses. The title goes on
    a label in the background color over the top of the image.
  - **Color and text**: background color, and the text for the back cover.
  - **Build cover** makes the wraparound PDF. Build it again whenever the interior's page count
    changes; the view warns when it is stale.

[Selling on Amazon](amazon-kdp.md) has the full specs, costs, rules and the KDP setup steps.

## Languages

The **🌐 Idioma · Language** selector in the sidebar switches the whole app between Spanish and
English and is remembered. Captions are printed exactly as you type them; nothing is translated.

## Costs

Each AI conversion is one image from `gemini-3-pro-image`, about **$0.14**; a cover image in 4K is
about **$0.25**. A 20-page book with one or two attempts per page costs about $4.

Every Gemini call is logged with its tokens and estimated cost. The sidebar shows the open book's
spend, images and tokens; **📊 Usage & costs** on the home page shows the totals (calls, images,
tokens, cost) and splits them by book and by operation. Calls made outside a book, like the
connection test, appear as "no book". Estimates use public list prices; your Google billing is the
source of truth.
