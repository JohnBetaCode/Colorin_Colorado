"""User-facing text in Spanish and English.

Every string the UI shows, and the fixed labels of the PDF, comes from ``STRINGS``
through ``t(key, **params)``. The UI language is a global setting (``UI_LANGUAGE``
in ``config/.env``) applied with ``set_language`` at the start of every run; the
PDF passes the book's own language explicitly. ``tests/test_i18n.py`` fails when a
key used in the code, or a language, is missing.
"""

from __future__ import annotations

LANGUAGE_NAMES = {"es": "Español", "en": "English"}

_language = "es"


def set_language(language: str) -> None:
    global _language
    _language = language if language in LANGUAGE_NAMES else "es"


def language() -> str:
    return _language


def t(key: str, lang: str | None = None, **params) -> str:
    text = STRINGS[key][lang or _language]
    return text.format(**params) if params else text


STRINGS: dict[str, dict[str, str]] = {
    # Home
    "home.tagline": {
        "es": "Convierte tus fotos en un libro para colorear.",
        "en": "Turn your photos into a coloring book.",
    },
    "home.unconfigured": {
        "es": "Gemini aún no está configurado: abre **⚙️ Ajustes** para usar la IA. Mientras tanto puedes usar el borrador gratis.",
        "en": "Gemini is not configured yet: open **⚙️ Settings** to use the AI. Meanwhile you can use the free draft.",
    },
    "home.new_book": {"es": "Nuevo libro", "en": "New book"},
    "home.title_placeholder": {"es": "p. ej. Aves del jardín", "en": "e.g. Garden birds"},
    "home.subtitle_placeholder": {"es": "p. ej. Para colorear y aprender", "en": "e.g. Color and learn"},
    "home.create": {"es": "Crear libro", "en": "Create book"},
    "home.title_required": {"es": "Ponle un título al libro.", "en": "Give the book a title."},
    "home.your_books": {"es": "Mis libros", "en": "My books"},
    "home.no_books": {"es": "Aún no hay libros. Crea el primero arriba.", "en": "No books yet. Create your first one above."},
    "home.no_image": {"es": "🖼️ Sin fotos aún", "en": "🖼️ No photos yet"},
    "home.progress": {"es": "{approved}/{total} páginas aprobadas", "en": "{approved}/{total} pages approved"},
    "home.created": {"es": "Creado el {date}", "en": "Created {date}"},
    "home.open": {"es": "Abrir", "en": "Open"},
    "home.delete": {"es": "Borrar", "en": "Delete"},
    "home.confirm_delete": {
        "es": "¿Borrar **{title}** con todas sus fotos y páginas? No se puede deshacer.",
        "en": "Delete **{title}** with all its photos and pages? This cannot be undone.",
    },
    "home.yes_delete": {"es": "Sí, borrarlo", "en": "Yes, delete it"},
    "home.cancel": {"es": "Cancelar", "en": "Cancel"},
    # Settings
    "settings.title": {"es": "⚙️ Ajustes: Gemini", "en": "⚙️ Settings: Gemini"},
    "settings.help": {
        "es": "Conéctate con Google Cloud (`gcloud auth application-default login` y el ID del proyecto) o con una API key. Estos valores se guardan en `config/.env`.",
        "en": "Connect with Google Cloud (`gcloud auth application-default login` and the project ID) or with an API key. These values are saved to `config/.env`.",
    },
    "settings.auth": {"es": "Autenticación", "en": "Authentication"},
    "settings.api_key": {"es": "API key", "en": "API key"},
    "settings.api_key_help": {
        "es": "Solo con autenticación por API key. Se guarda en `config/.env`, que no se sube a git.",
        "en": "Only for API key authentication. Saved in `config/.env`, which is never committed.",
    },
    "auth.adc": {"es": "Google Cloud (gcloud, Vertex AI)", "en": "Google Cloud (gcloud, Vertex AI)"},
    "auth.vertex_key": {"es": "API key de Vertex AI", "en": "Vertex AI API key"},
    "auth.studio_key": {"es": "API key de Google AI Studio", "en": "Google AI Studio API key"},
    "settings.project": {"es": "ID del proyecto de GCP (solo Google Cloud)", "en": "GCP project ID (Google Cloud only)"},
    "settings.text_location": {"es": "Región del modelo de texto", "en": "Text model location"},
    "settings.image_location": {"es": "Región del modelo de imagen", "en": "Image model location"},
    "settings.text_model": {"es": "Modelo de texto", "en": "Text model"},
    "settings.image_model": {"es": "Modelo de imagen", "en": "Image model"},
    "settings.save": {"es": "Guardar", "en": "Save"},
    "settings.save_test": {"es": "Guardar y probar", "en": "Save & test"},
    "settings.saved": {"es": "Ajustes guardados en config/.env.", "en": "Settings saved to config/.env."},
    "settings.testing": {"es": "Probando la conexión con Gemini…", "en": "Testing the connection to Gemini…"},
    "settings.ok": {"es": "Conexión correcta: el modelo respondió “{reply}”", "en": "Connection OK: the model replied “{reply}”"},
    "settings.failed": {"es": "La conexión falló: {error}", "en": "Connection failed: {error}"},
    # Usage
    "usage.title": {"es": "📊 Uso y costos", "en": "📊 Usage & costs"},
    "usage.empty": {"es": "Aún no hay uso de la API.", "en": "No API usage recorded yet."},
    "usage.calls": {"es": "Llamadas", "en": "API calls"},
    "usage.images": {"es": "Imágenes", "en": "Images"},
    "usage.cost": {"es": "Costo estimado", "en": "Est. cost"},
    "usage.tokens": {"es": "Tokens", "en": "Tokens"},
    "usage.tokens_help": {
        "es": "{input:,} de entrada y {output:,} de salida (incluye el razonamiento del modelo).",
        "en": "{input:,} input and {output:,} output (including the model's thinking).",
    },
    "usage.no_book": {"es": "(sin libro: pruebas y ajustes)", "en": "(no book: tests and settings)"},
    "usage.note": {
        "es": "Estimaciones con los precios públicos de Gemini. Tu facturación de Google es la fuente de verdad.",
        "en": "Estimates based on public Gemini list prices. Your Google billing is the source of truth.",
    },
    "usage.by_book": {"es": "Por libro", "en": "By book"},
    "usage.by_operation": {"es": "Por operación", "en": "By operation"},
    # Book
    "book.title": {"es": "Título", "en": "Title"},
    "book.subtitle": {"es": "Subtítulo", "en": "Subtitle"},
    "book.dedication": {"es": "Dedicatoria o autor (portada)", "en": "Dedication or author (cover)"},
    "book.style": {"es": "Estilo", "en": "Style"},
    "book.age_group": {"es": "Edad", "en": "Age"},
    "book.background": {"es": "Fondo por defecto", "en": "Default background"},
    "book.language": {"es": "Idioma del libro", "en": "Book language"},
    "book.language_help": {
        "es": "Idioma de los textos fijos del PDF. Los textos que escribes salen tal cual.",
        "en": "Language of the PDF's fixed labels. The text you type is printed as typed.",
    },
    "book.edit": {"es": "✏️ Editar libro", "en": "✏️ Edit book"},
    "book.save": {"es": "Guardar cambios", "en": "Save changes"},
    "book.saved": {"es": "Libro actualizado.", "en": "Book updated."},
    "book.edit_note": {
        "es": "Cambiar el estilo, la edad o el fondo solo afecta las conversiones nuevas.",
        "en": "Changing the style, age or background only affects new conversions.",
    },
    "book.back": {"es": "← Volver a mis libros", "en": "← Back to my books"},
    "book.spend": {
        "es": "Gasto estimado: ${cost:.2f} · {images} imágenes · {tokens:,} tokens",
        "en": "Est. spend: ${cost:.2f} · {images} images · {tokens:,} tokens",
    },
    "view.workbench": {"es": "🎨 Mesa de trabajo", "en": "🎨 Workbench"},
    "view.pages": {"es": "🗂️ Páginas", "en": "🗂️ Pages"},
    "view.export": {"es": "📄 Exportar PDF", "en": "📄 Export PDF"},
    "view.kdp": {"es": "🛒 Amazon KDP", "en": "🛒 Amazon KDP"},
    # Options
    "style.realistic": {"es": "Realista", "en": "Realistic"},
    "style.cartoon": {"es": "Caricatura", "en": "Cartoon"},
    "age.3-5": {"es": "3–5 años", "en": "Ages 3–5"},
    "age.6-8": {"es": "6–8 años", "en": "Ages 6–8"},
    "age.9+": {"es": "9 años o más", "en": "Ages 9+"},
    "background.keep": {"es": "Conservar el fondo", "en": "Keep the background"},
    "background.simplify": {"es": "Simplificar el fondo", "en": "Simplify the background"},
    "background.remove": {"es": "Sin fondo", "en": "No background"},
    "status.pending": {"es": "⏳ Pendiente", "en": "⏳ Pending"},
    "status.converted": {"es": "🖍️ Convertida", "en": "🖍️ Converted"},
    "status.approved": {"es": "✅ Aprobada", "en": "✅ Approved"},
    "engine.gemini": {"es": "IA", "en": "AI"},
    "engine.draft": {"es": "Borrador", "en": "Draft"},
    "page_size.letter": {"es": "Carta (Letter)", "en": "Letter"},
    "page_size.a4": {"es": "A4", "en": "A4"},
    "ink.black": {"es": "Negra (blanco y negro)", "en": "Black (black and white)"},
    "ink.standard_color": {"es": "Color estándar", "en": "Standard color"},
    "ink.premium_color": {"es": "Color premium", "en": "Premium color"},
    "cover_color.blue": {"es": "Azul", "en": "Blue"},
    "cover_color.green": {"es": "Verde", "en": "Green"},
    "cover_color.orange": {"es": "Naranja", "en": "Orange"},
    "cover_color.purple": {"es": "Morado", "en": "Purple"},
    "cover_color.pink": {"es": "Rosado", "en": "Pink"},
    "cover_color.teal": {"es": "Turquesa", "en": "Teal"},
    # Quality warnings from lineart.clean
    "warning.was_mockup": {
        "es": "La IA devolvió una foto de una hoja impresa; se recortó al dibujo. Revisa los bordes.",
        "en": "The AI returned a photo of a printed page; it was cut down to the drawing. Check the edges.",
    },
    "warning.had_color": {
        "es": "La IA copió colores de la foto y se quitaron. Si quedaron zonas raras, regenera.",
        "en": "The AI copied colors from the photo and they were removed. If some areas look odd, regenerate.",
    },
    "warning.had_shading": {
        "es": "La IA sombreó con gris y se aplanó a blanco y negro. Si se ve manchado, regenera.",
        "en": "The AI shaded with gray and it was flattened to black and white. If it looks patchy, regenerate.",
    },
    "warning.filled_areas": {
        "es": "Había zonas rellenas de negro; se dejaron solo con el contorno.",
        "en": "Some areas were filled black; only their outline was kept.",
    },
    "warning.too_dark": {
        "es": "Hay mucho negro en la página y es difícil de colorear. Prueba regenerar.",
        "en": "There is a lot of black on the page, which is hard to color. Try regenerating.",
    },
    "warning.too_few_regions": {
        "es": "Hay muy pocas zonas para colorear. Prueba regenerar o cambiar el estilo.",
        "en": "There are very few areas to color. Try regenerating or changing the style.",
    },
    # Workbench
    "wb.empty": {"es": "Este libro aún no tiene fotos. Súbelas en **🗂️ Páginas**.", "en": "This book has no photos yet. Upload them in **🗂️ Pages**."},
    "wb.page_of": {"es": "Página {n} de {total}", "en": "Page {n} of {total}"},
    "wb.photo": {"es": "Foto original", "en": "Original photo"},
    "wb.crop": {"es": "✂️ Recortar la foto", "en": "✂️ Crop the photo"},
    "wb.crop_help": {
        "es": "Encuadra lo que quieres colorear. El recorte se usa en las conversiones nuevas y en la foto de referencia del PDF.",
        "en": "Frame what you want to color. The crop is used by new conversions and by the reference photo in the PDF.",
    },
    "wb.crop_horizontal": {"es": "Horizontal (%)", "en": "Horizontal (%)"},
    "wb.crop_vertical": {"es": "Vertical (%)", "en": "Vertical (%)"},
    "wb.crop_reset": {"es": "Quitar recorte", "en": "Remove crop"},
    "wb.coloring_page": {"es": "Página para colorear", "en": "Coloring page"},
    "wb.not_converted": {
        "es": "Aún no se ha convertido. Elige el estilo y pulsa **Convertir con IA**, o prueba el borrador gratis.",
        "en": "Not converted yet. Pick the style and press **Convert with AI**, or try the free draft.",
    },
    "wb.versions": {"es": "Versiones", "en": "Versions"},
    "wb.version_label": {"es": "v{n} · {engine} · {style}", "en": "v{n} · {engine} · {style}"},
    "wb.style": {"es": "Estilo de esta página", "en": "Style of this page"},
    "wb.background": {"es": "Fondo", "en": "Background"},
    "wb.book_default": {"es": "Como el libro ({value})", "en": "Book default ({value})"},
    "wb.instructions": {"es": "Instrucciones extra", "en": "Extra instructions"},
    "wb.instructions_placeholder": {"es": "p. ej. solo el ave, sin la rama", "en": "e.g. only the bird, not the branch"},
    "wb.convert": {"es": "✨ Convertir con IA", "en": "✨ Convert with AI"},
    "wb.regenerate": {"es": "✨ Regenerar con IA", "en": "✨ Regenerate with AI"},
    "wb.draft": {"es": "✏️ Borrador gratis", "en": "✏️ Free draft"},
    "wb.draft_help": {
        "es": "Conversión local sin IA: instantánea y gratis. Dibuja las zonas de color de la foto, no un dibujo de verdad; sirve para armar el libro antes de gastar.",
        "en": "Local conversion without AI: instant and free. It traces the photo's color areas rather than drawing it; good for laying out the book before spending.",
    },
    "wb.ai_disabled": {
        "es": "Configura Gemini en la página de inicio para usar la IA.",
        "en": "Configure Gemini on the home page to use the AI.",
    },
    "wb.converting": {"es": "Convirtiendo… (unos 30–40 segundos)", "en": "Converting… (about 30–40 seconds)"},
    "wb.drafting": {"es": "Dibujando el borrador…", "en": "Drawing the draft…"},
    "wb.converted": {"es": "Página convertida (v{n}).", "en": "Page converted (v{n})."},
    "wb.failed": {"es": "La conversión falló: {error}", "en": "Conversion failed: {error}"},
    "wb.approve": {"es": "✅ Aprobar", "en": "✅ Approve"},
    "wb.approve_next": {"es": "✅ Aprobar y siguiente", "en": "✅ Approve and next"},
    "wb.approved": {"es": "Página aprobada.", "en": "Page approved."},
    "wb.caption": {"es": "Texto de la página", "en": "Page text"},
    "wb.caption_help": {
        "es": "Sale en el recuadro de abajo, junto a la foto de referencia. En la información, una línea como «Hábitat: bosques húmedos» pone la etiqueta en negrita.",
        "en": "Printed in the box at the bottom, next to the reference photo. In the info, a line like “Habitat: rainforests” puts the label in bold.",
    },
    "wb.caption_title": {"es": "Título", "en": "Title"},
    "wb.caption_title_placeholder": {"es": "p. ej. Tucán pico iris", "en": "e.g. Keel-billed toucan"},
    "wb.caption_subtitle": {"es": "Subtítulo", "en": "Subtitle"},
    "wb.caption_subtitle_placeholder": {"es": "p. ej. Ramphastos sulfuratus", "en": "e.g. Ramphastos sulfuratus"},
    "wb.caption_info": {"es": "Información", "en": "Info"},
    "wb.caption_info_placeholder": {
        "es": "Dónde vive: bosques tropicales húmedos\nDato curioso: su pico es liviano y hueco",
        "en": "Where it lives: tropical rainforests\nFun fact: its beak is light and hollow",
    },
    "wb.caption_too_long": {
        "es": "El texto no cabe en el recuadro y se cortará en el PDF. Acórtalo un poco.",
        "en": "The text does not fit in the box and will be cut in the PDF. Shorten it a little.",
    },
    "wb.credit": {"es": "Crédito de la foto", "en": "Photo credit"},
    "wb.credit_placeholder": {"es": "p. ej. Foto propia · Bernard Gagnon, CC0", "en": "e.g. My own photo · Bernard Gagnon, CC0"},
    "wb.credit_help": {
        "es": "Quién tomó la foto y con qué licencia. Sale en la página legal del PDF; para vender el libro necesitas el derecho de usar cada foto.",
        "en": "Who took the photo and under what license. Printed on the PDF's copyright page; to sell the book you need the right to use every photo.",
    },
    "wb.untitled": {"es": "Sin título", "en": "Untitled"},
    # Pages
    "pages.add_photos": {"es": "📷 Agregar fotos", "en": "📷 Add photos"},
    "pages.upload_label": {"es": "Fotos (JPG, PNG, WebP o HEIC)", "en": "Photos (JPG, PNG, WebP or HEIC)"},
    "pages.add_n": {"es": "Agregar {n} fotos", "en": "Add {n} photos"},
    "pages.added": {"es": "Se agregaron {n} fotos.", "en": "Added {n} photos."},
    "pages.unreadable": {"es": "No se pudieron leer: {names}", "en": "Could not read: {names}"},
    "pages.summary": {"es": "{total} páginas · {approved} aprobadas", "en": "{total} pages · {approved} approved"},
    "pages.in_book": {"es": "Incluir en el libro", "en": "Include in the book"},
    "pages.move_left": {"es": "Mover antes", "en": "Move earlier"},
    "pages.move_right": {"es": "Mover después", "en": "Move later"},
    "pages.open": {"es": "Abrir en la mesa de trabajo", "en": "Open in the workbench"},
    "pages.delete": {"es": "Borrar página", "en": "Delete page"},
    "pages.make_cover": {"es": "Usar de portada", "en": "Use as cover"},
    "pages.is_cover": {"es": "⭐ Portada", "en": "⭐ Cover"},
    "pages.confirm_delete": {
        "es": "¿Borrar la página **{title}** con todas sus versiones?",
        "en": "Delete the page **{title}** with all its versions?",
    },
    "pages.deleted": {"es": "Página borrada.", "en": "Page deleted."},
    # Export
    "export.page_size": {"es": "Tamaño de página", "en": "Page size"},
    "export.include_photo": {"es": "Foto de referencia en cada página", "en": "Reference photo on every page"},
    "export.owner_page": {"es": "Página «Este libro pertenece a»", "en": "“This book belongs to” page"},
    "export.blank_backs": {"es": "Reverso en blanco en cada hoja", "en": "Blank back on every sheet"},
    "export.blank_backs_help": {
        "es": "Para imprimir a doble cara sin que los marcadores traspasen a otro dibujo.",
        "en": "For double-sided printing, so markers never bleed into another drawing.",
    },
    "export.cover": {"es": "Portada", "en": "Cover"},
    "export.cover_first": {"es": "La primera página", "en": "The first page"},
    "export.legal": {"es": "Página legal (va detrás de la portada)", "en": "Copyright page (on the back of the title page)"},
    "export.legal_placeholder": {
        "es": "© 2026 Tu nombre. Todos los derechos reservados.\nPrimera edición.\nISBN: …",
        "en": "© 2026 Your name. All rights reserved.\nFirst edition.\nISBN: …",
    },
    "export.legal_help": {
        "es": "Se imprime con los créditos de las fotos. Si no hay texto ni créditos, no hay página legal.",
        "en": "Printed with the photo credits. With no text and no credits, there is no copyright page.",
    },
    "export.labels": {
        "es": "Los textos fijos del PDF salen en {language}; se cambia en **✏️ Editar libro**.",
        "en": "The PDF's fixed labels are in {language}; change it in **✏️ Edit book**.",
    },
    "export.included": {"es": "Páginas en el libro", "en": "Pages in the book"},
    "export.not_approved": {"es": "Sin aprobar", "en": "Not approved"},
    "export.skipped": {"es": "Sin convertir", "en": "Not converted"},
    "export.not_approved_list": {"es": "Sin aprobar (se incluyen igual): {names}", "en": "Not approved (included anyway): {names}"},
    "export.skipped_list": {
        "es": "Se omiten porque no tienen página para colorear: {names}",
        "en": "Skipped because they have no coloring page: {names}",
    },
    "export.overflow_list": {"es": "El texto no cabe en el recuadro: {names}", "en": "Text does not fit in the box: {names}"},
    "export.build": {"es": "Generar PDF", "en": "Build PDF"},
    "export.building": {"es": "Generando el PDF…", "en": "Building the PDF…"},
    "export.failed": {"es": "No se pudo exportar: {error}", "en": "Export failed: {error}"},
    "export.download": {"es": "⬇️ Descargar PDF", "en": "⬇️ Download PDF"},
    "export.latest": {"es": "Último: `exports/{name}` ({size:.1f} MB)", "en": "Latest: `exports/{name}` ({size:.1f} MB)"},
    "export.nothing": {"es": "Convierte al menos una página para exportar.", "en": "Convert at least one page to export."},
    # Amazon KDP
    "kdp.intro": {
        "es": "Lo que pide Amazon KDP para vender este libro en tapa blanda. Medidas, costos, derechos e impuestos, con fuentes, en `docs/amazon-kdp.md`.",
        "en": "What Amazon KDP asks for to sell this book as a paperback. Sizes, costs, rights and taxes, with sources, in `docs/amazon-kdp.md`.",
    },
    "kdp.ink": {"es": "Tinta del interior", "en": "Interior ink"},
    "kdp.ink_help": {
        "es": "Negra: lo más barato, y las fotos de referencia salen en gris. Color estándar: desde 72 páginas y solo en Carta. Color premium: mejor papel y lo más caro.",
        "en": "Black: cheapest, and the reference photos print in gray. Standard color: 72 pages or more, Letter only. Premium color: better paper, most expensive.",
    },
    "kdp.price": {"es": "Precio de lista en Amazon.com (USD)", "en": "List price on Amazon.com (USD)"},
    "kdp.price_help": {
        "es": "Desde $9.99 KDP paga el 60% del precio menos la impresión; por debajo, el 50%.",
        "en": "From $9.99 KDP pays 60% of the price minus printing; below it, 50%.",
    },
    "kdp.pages": {"es": "Páginas del interior", "en": "Interior pages"},
    "kdp.spine": {"es": "Lomo", "en": "Spine"},
    "kdp.cost": {"es": "Impresión por copia", "en": "Printing per copy"},
    "kdp.royalty": {"es": "Regalía por copia", "en": "Royalty per copy"},
    "kdp.min_price": {
        "es": "Precio mínimo que acepta KDP con esta tinta: ${price:.2f}. Costos de Amazon.com; en otras tiendas cambian.",
        "en": "Lowest price KDP accepts with this ink: ${price:.2f}. Amazon.com costs; other stores differ.",
    },
    "kdp.checks": {"es": "Antes de subirlo", "en": "Before uploading"},
    "kdp.ready": {"es": "Nada bloquea la publicación en KDP.", "en": "Nothing blocks publishing on KDP."},
    "kdp.issue.no_pages": {"es": "Convierte al menos una página.", "en": "Convert at least one page."},
    "kdp.issue.ink_not_offered": {
        "es": "KDP no ofrece color estándar en A4: usa Carta o cambia la tinta.",
        "en": "KDP does not offer standard color in A4: use Letter or change the ink.",
    },
    "kdp.issue.too_few_pages": {
        "es": "El interior tiene {pages} páginas y KDP pide al menos {min} con esta tinta. Agrega dibujos: con reverso en blanco cada uno suma dos páginas.",
        "en": "The interior has {pages} pages and KDP needs at least {min} with this ink. Add drawings: with blank backs each one adds two pages.",
    },
    "kdp.issue.too_few_pages_no_backs": {
        "es": "El interior tiene {pages} páginas y KDP pide al menos {min} con esta tinta. Agrega dibujos o activa el reverso en blanco.",
        "en": "The interior has {pages} pages and KDP needs at least {min} with this ink. Add drawings or turn on blank backs.",
    },
    "kdp.issue.too_many_pages": {
        "es": "El interior tiene {pages} páginas; por encima de {max} el margen interior de 0.5 in no alcanza. Divide el libro en dos.",
        "en": "The interior has {pages} pages; above {max} the 0.5 in inside margin is too small. Split the book in two.",
    },
    "kdp.issue.fonts": {
        "es": "La fuente Andika no está instalada, así que el PDF no incrustaría sus fuentes y KDP lo rechazaría. Exporta desde el contenedor de Docker.",
        "en": "The Andika font is not installed, so the PDF would not embed its fonts and KDP would reject it. Export from the Docker container.",
    },
    "kdp.issue.price_too_low": {
        "es": "El precio está por debajo del mínimo de KDP para este libro: ${price:.2f}.",
        "en": "The price is below KDP's minimum for this book: ${price:.2f}.",
    },
    "kdp.issue.no_blank_backs": {
        "es": "Activa «Reverso en blanco» en 📄 Exportar PDF: KDP imprime siempre a doble cara y los marcadores traspasan al dibujo de atrás.",
        "en": "Turn on “Blank back” in 📄 Export PDF: KDP always prints double-sided and markers bleed into the drawing behind.",
    },
    "kdp.issue.not_approved": {
        "es": "Sin aprobar: {names}. Revisa cada dibujo antes de vender; un error de la IA trae malas reseñas.",
        "en": "Not approved: {names}. Check every drawing before selling; an AI mistake brings bad reviews.",
    },
    "kdp.issue.overflowing": {"es": "El texto no cabe en el recuadro: {names}.", "en": "Text does not fit in the box: {names}."},
    "kdp.issue.no_legal": {
        "es": "Falta el texto de la página legal (© año y autor, derechos, ISBN). Escríbelo en 📄 Exportar PDF.",
        "en": "The copyright page text is missing (© year and author, rights, ISBN). Write it in 📄 Export PDF.",
    },
    "kdp.issue.missing_credits": {
        "es": "Sin crédito de la foto: {names}. Escribe en la mesa de trabajo de quién es cada foto y su licencia.",
        "en": "No photo credit: {names}. In the workbench, write who owns each photo and its license.",
    },
    "kdp.issue.low_royalty": {
        "es": "Por debajo de ${threshold:.2f} KDP paga el 50% en vez del 60%.",
        "en": "Below ${threshold:.2f} KDP pays 50% instead of 60%.",
    },
    "kdp.issue.photos_gray": {
        "es": "Con tinta negra las fotos de referencia se imprimen en escala de grises.",
        "en": "With black ink the reference photos print in grayscale.",
    },
    "kdp.issue.ai_disclosure": {
        "es": "Hay imágenes hechas con IA (dibujos o la imagen de portada): al publicar, KDP te pregunta por contenido generado por IA y tienes que declararlas.",
        "en": "Some images were made with AI (drawings or the cover image): when publishing, KDP asks about AI-generated content and you must declare them.",
    },
    "kdp.upload": {"es": "Al subirlo a KDP", "en": "When uploading to KDP"},
    "kdp.upload_steps": {
        "es": "- **Tamaño de corte (trim size):** {trim}\n- **Sangrado (bleed):** sin sangrado (*No Bleed*)\n- **Tinta y papel:** {ink}, papel blanco\n- **Manuscrito:** el último PDF de 📄 Exportar PDF ({pages} páginas)\n- **Portada:** el PDF de abajo, generado para {pages} páginas (*Upload a cover you already have*)",
        "en": "- **Trim size:** {trim}\n- **Bleed:** *No Bleed*\n- **Ink and paper:** {ink}, white paper\n- **Manuscript:** the latest PDF from 📄 Export PDF ({pages} pages)\n- **Cover:** the PDF below, built for {pages} pages (*Upload a cover you already have*)",
    },
    "kdp.trim.letter": {"es": "8.5 × 11 in (21.59 × 27.94 cm)", "en": "8.5 × 11 in (21.59 × 27.94 cm)"},
    "kdp.trim.a4": {"es": "8.27 × 11.69 in (21 × 29.7 cm)", "en": "8.27 × 11.69 in (21 × 29.7 cm)"},
    "kdp.cover": {"es": "Portada para KDP", "en": "KDP cover"},
    "kdp.cover_help": {
        "es": "Un solo PDF con contraportada, lomo y portada, a la medida del interior actual: {width:.3f} × {height:.3f} in con lomo de {spine:.3f} in. El título va en el lomo cuando es lo bastante ancho (unas 96 páginas). La esquina inferior derecha de la contraportada queda libre para el código de barras que pone KDP.",
        "en": "One PDF with back cover, spine and front cover, sized for the current interior: {width:.3f} × {height:.3f} in with a {spine:.3f} in spine. The title goes on the spine once it is wide enough (about 96 pages). The lower right of the back cover is left free for the barcode KDP prints.",
    },
    "kdp.art": {"es": "Imagen de la portada", "en": "Front cover image"},
    "kdp.art_choice": {"es": "Al frente va", "en": "On the front"},
    "kdp.art_line": {"es": "El dibujo de la página de portada, sin color", "en": "The cover page's drawing, uncolored"},
    "kdp.art_version": {"es": "Imagen v{n} · {source}", "en": "Image v{n} · {source}"},
    "kdp.art_upload_tab": {"es": "📤 Subir una imagen", "en": "📤 Upload an image"},
    "kdp.art_upload_help": {
        "es": "Una ilustración vertical a todo color, sin texto: el título se pone encima. Cubre todo el frente hasta el borde; para que se imprima nítida necesita unos {width} × {height} px.",
        "en": "A portrait, full-color illustration with no text: the title goes on top. It covers the whole front to the edge; to print sharp it needs about {width} × {height} px.",
    },
    "kdp.art_upload_label": {"es": "Imagen (JPG, PNG, WebP o HEIC)", "en": "Image (JPG, PNG, WebP or HEIC)"},
    "kdp.art_use": {"es": "Usar esta imagen", "en": "Use this image"},
    "kdp.art_added": {"es": "Imagen de portada guardada (v{n}).", "en": "Cover image saved (v{n})."},
    "kdp.art_unreadable": {"es": "No se pudo leer la imagen.", "en": "Could not read the image."},
    "kdp.art_ai_tab": {"es": "✨ Generar con IA", "en": "✨ Generate with AI"},
    "kdp.art_mode": {"es": "A partir de", "en": "From"},
    "art_mode.collage": {"es": "Un collage de páginas", "en": "A collage of pages"},
    "art_mode.text": {"es": "Un texto", "en": "A description"},
    "art_mode.theme": {"es": "La temática del libro", "en": "The book's theme"},
    "art_mode_help.collage": {
        "es": "La IA junta los dibujos que elijas en una sola ilustración, coloreados con los colores reales de sus fotos.",
        "en": "The AI brings the drawings you pick together in one illustration, colored with the real colors of their photos.",
    },
    "art_mode_help.text": {
        "es": "La IA dibuja lo que describas.",
        "en": "The AI draws what you describe.",
    },
    "art_mode_help.theme": {
        "es": "La IA imagina una portada a partir del título, el subtítulo y los títulos de las páginas.",
        "en": "The AI imagines a cover from the title, the subtitle and the page titles.",
    },
    "kdp.art_pages": {"es": "Páginas del collage (hasta {max})", "en": "Pages in the collage (up to {max})"},
    "kdp.art_text": {"es": "Descripción", "en": "Description"},
    "kdp.art_text_placeholder": {
        "es": "p. ej. un tucán y un zorro leyendo un libro gigante en un bosque lleno de flores",
        "en": "e.g. a toucan and a fox reading a giant book in a forest full of flowers",
    },
    "kdp.art_extra": {"es": "Instrucciones extra (opcional)", "en": "Extra instructions (optional)"},
    "kdp.art_extra_placeholder": {"es": "p. ej. de noche, con estrellas", "en": "e.g. at night, with stars"},
    "kdp.art_generate": {"es": "✨ Generar imagen de portada", "en": "✨ Generate cover image"},
    "kdp.art_generating": {"es": "Dibujando la portada… (unos 40–60 segundos)", "en": "Drawing the cover… (about 40–60 seconds)"},
    "kdp.art_failed": {"es": "No se pudo generar: {error}", "en": "Generation failed: {error}"},
    "kdp.art_need_text": {"es": "Describe la portada que quieres.", "en": "Describe the cover you want."},
    "kdp.art_need_pages": {"es": "Elige al menos una página para el collage.", "en": "Pick at least one page for the collage."},
    "kdp.art_cost": {
        "es": "Cada imagen cuesta unos $0.25 (4K, para que se imprima nítida) y se guarda como una versión nueva. En KDP se declara como imagen generada por IA.",
        "en": "Each image costs about $0.25 (4K, to print sharp) and is kept as a new version. On KDP it must be declared as an AI-generated image.",
    },
    "art_source.upload": {"es": "subida", "en": "uploaded"},
    "art_source.collage": {"es": "IA, collage", "en": "AI, collage"},
    "art_source.text": {"es": "IA, descripción", "en": "AI, description"},
    "art_source.theme": {"es": "IA, temática", "en": "AI, theme"},
    "kdp.cover_text": {"es": "Color y textos", "en": "Color and text"},
    "kdp.issue.cover_art_low_res": {
        "es": "La imagen de portada se imprimiría a {ppi} ppi y KDP pide {min}: usa una imagen más grande.",
        "en": "The cover image would print at {ppi} ppi and KDP asks for {min}: use a bigger image.",
    },
    "kdp.cover_color": {"es": "Color de fondo", "en": "Background color"},
    "kdp.back_text": {"es": "Texto de la contraportada", "en": "Back cover text"},
    "kdp.back_text_placeholder": {
        "es": "p. ej. 30 aves para colorear, cada una con su foto real y un dato curioso.",
        "en": "e.g. 30 birds to color, each with its real photo and a fun fact.",
    },
    "kdp.build_cover": {"es": "Generar portada", "en": "Build cover"},
    "kdp.building_cover": {"es": "Generando la portada…", "en": "Building the cover…"},
    "kdp.cover_failed": {"es": "No se pudo generar la portada: {error}", "en": "Cover build failed: {error}"},
    "kdp.download_cover": {"es": "⬇️ Descargar portada", "en": "⬇️ Download cover"},
    "kdp.cover_latest": {"es": "Última: `exports/covers/{name}` ({size:.1f} MB)", "en": "Latest: `exports/covers/{name}` ({size:.1f} MB)"},
    "kdp.cover_stale": {
        "es": "Esta portada es para {old} páginas y el interior ahora tiene {new}: genera otra.",
        "en": "This cover is for {old} pages and the interior now has {new}: build a new one.",
    },
    # PDF
    "pdf.owner": {"es": "Este libro pertenece a:", "en": "This book belongs to:"},
    "pdf.photo_credits": {"es": "Créditos de las fotografías", "en": "Photo credits"},
    "pdf.credit_line": {"es": "Pág. {n} · {title}: {credit}", "en": "p. {n} · {title}: {credit}"},
}
