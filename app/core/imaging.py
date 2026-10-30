"""Coloring-page generation.

The uploaded photo is always the reference image: the model redraws that exact
subject as line art, it never invents one from text. Whatever comes back goes
through ``lineart.clean`` before anyone sees it.
"""

from __future__ import annotations

from app.core import gemini, lineart, pages, usage
from app.core.books import now
from app.core.schema import Book, Engine, Page, Version

STYLE_PROMPTS = {
    "realistic": (
        "realistic field-guide line drawing traced from the photo: accurate anatomy or "
        "architecture and proportions, the characteristic markings and patterns drawn as "
        "outlined regions, clean confident contour lines"
    ),
    "cartoon": (
        "friendly children's cartoon: simplified rounded shapes, slightly bigger head and "
        "expressive eyes when the subject has a face, smooth even outlines, fewer and bigger "
        "areas to color; still unmistakably the same subject as the photo"
    ),
}

AGE_PROMPTS = {
    "3-5": {
        "detail": (
            "VERY SIMPLE, for ages 3 to 5: only the main silhouette and a few big inner shapes "
            "(roughly 10 to 20 areas to color), no small details, no textures; any background is "
            "at most a few big simple shapes, even in a busy scene"
        ),
        "lines": "VERY THICK, like a marker: about 1/80 of the image width, the same everywhere",
    },
    "6-8": {
        "detail": (
            "SIMPLE, for ages 6 to 8: the main features and the few details that make the "
            "subject recognizable (roughly 25 to 60 areas to color), mostly large areas"
        ),
        "lines": "thick and even: about 1/130 of the image width",
    },
    "9+": {
        "detail": (
            "DETAILED, for ages 9 and up: full detail, textures such as feathers, fur, stones or "
            "leaves drawn as many small outlined areas"
        ),
        "lines": "medium: about 1/200 of the image width, slightly finer for inner details",
    },
}

BACKGROUND_PROMPTS = {
    "keep": (
        "keep the setting and the framing of the photo, redrawn as outlined shapes to color at "
        "the detail level above"
    ),
    "simplify": (
        "replace the background with a few simple outlined elements that suggest the setting "
        "(for example a branch, the ground, a horizon line, a couple of clouds); zoom in on the "
        "main subject so it fills most of the page"
    ),
    "remove": (
        "no background at all: the subject alone on plain white, zoomed in so it fills most of "
        "the page"
    ),
}

COLORING_PAGE_PROMPT = """\
Turn the attached photo into a coloring-book page for children: a BLACK-AND-WHITE LINE
DRAWING, black outlines on a pure white background, with NO COLOR AT ALL.

Do NOT copy the colors or the dark areas of the photo. Every area is left WHITE inside its
outline so a child can color it in, including the parts that are black or dark in the photo:
a black bird's body is an outline with white inside, never a black shape.

SUBJECT: the attached photo IS the subject. Keep what makes it recognizable: the same
species, building, object or person, the same pose and viewpoint, the same proportions,
and its distinctive shapes and markings, drawn as outlined areas to color. Draw exactly the
animals, people and objects that are in the photo: never add new ones, never duplicate one.
{title_line}
STYLE: {style}.
DETAIL: {detail}.
BACKGROUND: {background}.
{instructions_block}
STRICT COLORING-PAGE RULES:
- Pure black outlines on a pure white background. Nothing else: no color anywhere.
- No shading, no gray, no gradients, no hatching, no stippling, no texture strokes.
- No solid black fills, except tiny details such as the pupils of the eyes. Dark fur,
  feathers, hair, windows or shadows are outlines with white inside.
- Every line belongs to a closed shape, so each area can be colored in. No loose strokes:
  grass, leaves, fur, hair and feathers are a few outlined clumps or locks, never many
  separate little lines.
- Line weight: {lines}.
- No text, letters, numbers, signatures, watermarks, borders or frames.
- Flat digital artwork filling the whole image. Not a photo or mockup of a printed page:
  no paper edges, no book, no table, no shadows.
- The whole subject is visible, with a white margin around the drawing.
"""

# Aspect ratios the image model accepts, as width / height.
_ASPECTS = {"3:4": 3 / 4, "1:1": 1.0, "4:3": 4 / 3}


def aspect_for(width: int, height: int) -> str:
    """Closest supported aspect ratio to the photo's, so the framing survives."""
    ratio = width / height
    return min(_ASPECTS, key=lambda key: abs(_ASPECTS[key] - ratio))


def build_prompt(style: str, age_group: str, background: str, title: str = "", instructions: str = "") -> str:
    age = AGE_PROMPTS[age_group]
    title_line = f"The subject is: {title.strip()}.\n" if title.strip() else ""
    instructions_block = (
        f"AUTHOR'S INSTRUCTIONS (highest priority, unless they break the coloring-page rules):\n"
        f"{instructions.strip()}\n"
        if instructions.strip()
        else ""
    )
    return COLORING_PAGE_PROMPT.format(
        title_line=title_line,
        style=STYLE_PROMPTS[style],
        detail=age["detail"],
        background=BACKGROUND_PROMPTS[background],
        instructions_block=instructions_block,
        lines=age["lines"],
    )


def render_coloring_page(photo: bytes, size: tuple[int, int], prompt: str) -> bytes:
    """Raw model output for one photo (PNG bytes, not yet cleaned)."""
    return gemini.generate_image(prompt, reference_images=[photo], aspect_ratio=aspect_for(*size), image_size="2K")


def convert_page(book: Book, page: Page, engine: Engine) -> Page:
    """Convert a page's (cropped) photo and store the result as its new selected version.

    ``engine`` is ``"gemini"`` (AI, paid) or ``"draft"`` (offline, free). Raises
    ``gemini.GeminiError`` when the AI call fails; nothing is stored in that case.
    """
    style = page.style or book.style
    background = page.background or book.background
    photo = pages.cropped_photo(book.slug, page)
    if engine == "gemini":
        prompt = build_prompt(style, book.age_group, background, page.title, page.instructions)
        with usage.book_context(book.id):
            raw = render_coloring_page(pages.jpeg_bytes(photo), photo.size, prompt)
    else:
        raw = lineart.to_png(lineart.draft(photo, style, book.age_group))
    cleaned = lineart.clean(raw, book.age_group)
    version = Version(
        n=0,
        engine=engine,
        style=style,
        age_group=book.age_group,
        background=background,
        instructions=page.instructions,
        warnings=cleaned.warnings,
        created_at=now(),
    )
    return pages.add_version(book.slug, page.id, version, raw, cleaned.image)
