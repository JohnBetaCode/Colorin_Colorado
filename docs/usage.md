# User guide

## A book from start to finish

1. **Create the book** on the home page: title, subtitle, style, age group and book language.
   Everything except the title can be changed later in **✏️ Edit book** (sidebar).
2. **Add photos** in **🗂️ Pages → 📷 Add photos**. Select many at once; each becomes a page in the
   order you uploaded them.
3. **Convert in the 🎨 Workbench**, one page at a time:
   - **Crop** the photo first if the subject is small in it. The model keeps the photo's framing,
     so a dog in a corner of a lawn becomes a page full of grass.
   - **✨ Convert with AI** takes 30–40 seconds and costs about $0.17. **✏️ Free draft** is instant
     and free, but it only traces the photo's color areas: use it to lay out a book, not to print.
   - Not happy? Add **extra instructions** ("only the bird, not the branch", "remove the people in
     the back"), change the page's **style** or **background**, and regenerate. Every attempt is
     kept under **Versions**; pick the one you like.
   - Warnings under the page tell you when the cleanup had to fix something (copied colors, black
     fills, a photo of a printed page). They never block; regenerate if the result looks off.
   - **✅ Approve and next** moves to the next page.
4. **Write the caption** next to the photo: a title, a subtitle and an info text. They are
   printed in the box under the coloring page.
5. **Export** in **📄 Export PDF**: choose the options, check the summary, **Build PDF**, preview
   it and download it.

## Styles, ages and backgrounds

| Setting | Options | Effect |
|---|---|---|
| Style | Realistic, Cartoon | Field-guide drawing traced from the photo, or a friendly cartoon of the same subject. |
| Age | 3–5, 6–8, 9+ | Line weight and how many areas there are to color. 3–5 gets very thick lines and a few big areas. |
| Background | Keep, Simplify, Remove | Keep the setting, reduce it to a few shapes and zoom in on the subject, or draw the subject alone. |

Style and background are set per book and can be overridden per page. The age group is per book.
Changing any of them affects new conversions only.

## Captions

- **Title**: the name of what is being colored ("Tucán pico iris", "Santuario de Las Lajas").
  It also tells the model what the subject is, so write it before converting.
- **Subtitle**: a scientific name, a city, a date.
- **Info**: free text. A line that starts with a short label and a colon gets the label in bold:

  ```
  Dónde vive: bosques húmedos del Caribe y el Darién
  Dato curioso: su pico es enorme pero liviano
  ```

The text shrinks to fit the box. If it still does not fit, the workbench and the export summary
warn you and the PDF cuts it at the edge of the box.

## Export options

| Option | Default | What it does |
|---|---|---|
| Page size | Letter | Letter (*carta*) or A4. |
| Cover | First page | Which coloring page goes on the cover (also from **🗂️ Pages → Use as cover**). |
| Reference photo on every page | On | The small color photo in the info box. |
| "This book belongs to" page | On | A page for the child's name after the cover. |
| Blank back on every sheet | Off | For double-sided printing, so markers never bleed into another drawing. |

The fixed labels of the PDF follow the **book language**, not the app language: a Spanish app can
make an English book. Pages without a coloring page are skipped; pages not yet approved are
included and listed in the summary. Every build is a new file in `books/<slug>/exports/`.

## Languages

The **🌐 Idioma · Language** selector in the sidebar switches the whole app between Spanish and
English and is remembered. Captions are printed exactly as you type them; nothing is translated.

## Costs

Each AI conversion is one image from `gemini-3-pro-image`, about **$0.17**. A 20-page book with
one or two attempts per page costs about $5. The sidebar shows the estimated spend of the open
book; **📊 Usage & costs** on the home page shows all books. Estimates use public list prices; the
Google Cloud billing console is the source of truth.
