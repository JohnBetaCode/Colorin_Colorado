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
        "es": "Google Cloud aún no está configurado: abre **⚙️ Ajustes** para usar la IA. Mientras tanto puedes usar el borrador gratis.",
        "en": "Google Cloud is not configured yet: open **⚙️ Settings** to use the AI. Meanwhile you can use the free draft.",
    },
    "home.new_book": {"es": "Nuevo libro", "en": "New book"},
    "home.title_placeholder": {"es": "p. ej. Aves de Colombia", "en": "e.g. Birds of Colombia"},
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
    "settings.title": {"es": "⚙️ Ajustes: Gemini en Vertex AI", "en": "⚙️ Settings: Gemini on Vertex AI"},
    "settings.help": {
        "es": "La autenticación usa las Application Default Credentials de Google (`gcloud auth application-default login`). Estos valores se guardan en `config/.env`.",
        "en": "Authentication uses Google Application Default Credentials (`gcloud auth application-default login`). These values are saved to `config/.env`.",
    },
    "settings.project": {"es": "ID del proyecto de GCP", "en": "GCP project ID"},
    "settings.text_location": {"es": "Región del modelo de texto", "en": "Text model location"},
    "settings.image_location": {"es": "Región del modelo de imagen", "en": "Image model location"},
    "settings.text_model": {"es": "Modelo de texto", "en": "Text model"},
    "settings.image_model": {"es": "Modelo de imagen", "en": "Image model"},
    "settings.save": {"es": "Guardar", "en": "Save"},
    "settings.save_test": {"es": "Guardar y probar", "en": "Save & test"},
    "settings.saved": {"es": "Ajustes guardados en config/.env.", "en": "Settings saved to config/.env."},
    "settings.testing": {"es": "Probando la conexión con Vertex AI…", "en": "Testing the connection to Vertex AI…"},
    "settings.ok": {"es": "Conexión correcta: el modelo respondió “{reply}”", "en": "Connection OK: the model replied “{reply}”"},
    "settings.failed": {"es": "La conexión falló: {error}", "en": "Connection failed: {error}"},
    # Usage
    "usage.title": {"es": "📊 Uso y costos", "en": "📊 Usage & costs"},
    "usage.empty": {"es": "Aún no hay uso de la API.", "en": "No API usage recorded yet."},
    "usage.calls": {"es": "Llamadas", "en": "API calls"},
    "usage.images": {"es": "Imágenes", "en": "Images"},
    "usage.cost": {"es": "Costo estimado", "en": "Est. cost"},
    "usage.note": {
        "es": "Estimaciones con los precios públicos de Vertex AI. La consola de facturación de GCP es la fuente de verdad.",
        "en": "Estimates based on public Vertex AI list prices. Your GCP billing console is the source of truth.",
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
    "book.spend": {"es": "Gasto estimado: ${cost:.2f} (imágenes: {images})", "en": "Est. spend: ${cost:.2f} (images: {images})"},
    "view.workbench": {"es": "🎨 Mesa de trabajo", "en": "🎨 Workbench"},
    "view.pages": {"es": "🗂️ Páginas", "en": "🗂️ Pages"},
    "view.export": {"es": "📄 Exportar PDF", "en": "📄 Export PDF"},
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
        "es": "Configura Google Cloud en la página de inicio para usar la IA.",
        "en": "Configure Google Cloud on the home page to use the AI.",
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
        "es": "Dónde vive: bosques húmedos de Colombia\nDato curioso: su pico es liviano y hueco",
        "en": "Where it lives: rainforests of Central America\nFun fact: its beak is light and hollow",
    },
    "wb.caption_too_long": {
        "es": "El texto no cabe en el recuadro y se cortará en el PDF. Acórtalo un poco.",
        "en": "The text does not fit in the box and will be cut in the PDF. Shorten it a little.",
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
    # PDF
    "pdf.owner": {"es": "Este libro pertenece a:", "en": "This book belongs to:"},
}
