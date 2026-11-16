from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw

from app.core import lineart
from tests.conftest import png_bytes


def _pixels(result: lineart.CleanResult) -> np.ndarray:
    return np.array(result.image.convert("L"))


def _only_black_and_white(result: lineart.CleanResult) -> bool:
    return result.image.mode == "1" and set(np.unique(_pixels(result))) <= {0, 255}


def test_clean_output_is_pure_black_and_white(line_art):
    result = lineart.clean(line_art, "6-8")
    assert _only_black_and_white(result)
    assert result.image.size[1] > 1200  # upscaled from the 1200 px source before thresholding
    assert result.regions >= lineart.MIN_REGIONS


def test_colored_and_shaded_output_is_flattened():
    image = Image.new("RGB", (900, 1200), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 800, 500), fill=(40, 170, 60), outline=(0, 0, 0), width=10)  # copied color
    draw.rectangle((100, 600, 800, 1000), fill=(110, 110, 110), outline=(0, 0, 0), width=10)  # gray shading
    result = lineart.clean(png_bytes(image), "6-8")
    assert _only_black_and_white(result)
    assert "had_color" in result.warnings
    assert result.black_ratio < lineart.TOO_DARK_RATIO


def test_big_fills_become_outlines_and_pupils_stay_black():
    image = Image.new("L", (900, 1200), 255)
    draw = ImageDraw.Draw(image)
    draw.ellipse((150, 150, 750, 750), fill=0)  # a black bird's body
    draw.ellipse((420, 950, 450, 980), fill=0)  # a pupil
    result = lineart.clean(png_bytes(image), "6-8")
    pixels = _pixels(result)
    h, w = pixels.shape
    assert "filled_areas" in result.warnings
    assert pixels[int(h * 0.33), w // 2] == 255  # inside the body is white now
    assert (pixels == 0).mean() < 0.1
    # The pupil survives as a solid dot: some black remains near the bottom.
    assert (pixels[int(h * 0.75) :] == 0).any()


def test_thin_lines_are_thickened_to_the_age_minimum():
    image = Image.new("L", (900, 1200), 255)
    draw = ImageDraw.Draw(image)
    for i in range(4):
        draw.ellipse((100 + i * 50, 100 + i * 80, 800 - i * 50, 1100 - i * 80), outline=0, width=2)
    thin = lineart.clean(png_bytes(image), "9+")
    thick = lineart.clean(png_bytes(image), "3-5")
    assert thick.stroke_px > thin.stroke_px
    assert thick.stroke_px >= lineart.MIN_STROKE_PX["3-5"] * 0.8


def test_thickening_stops_before_lines_merge():
    image = Image.new("L", (900, 1200), 255)
    draw = ImageDraw.Draw(image)
    for y in range(100, 1100, 14):  # dense hatching: gaps narrower than the 3-5 line width
        draw.line((100, y, 800, y), fill=0, width=2)
    result = lineart.clean(png_bytes(image), "3-5")
    assert result.black_ratio <= lineart.THICKEN_MAX_BLACK + 0.05


def test_mockup_photo_is_cut_down_to_the_sheet(line_art):
    sheet = Image.open(BytesIO(line_art)).convert("RGB")
    table = Image.new("RGB", (1200, 1500), (150, 110, 70))
    table.paste(sheet, (150, 150))
    result = lineart.clean(png_bytes(table), "6-8")
    assert "was_mockup" in result.warnings
    assert _only_black_and_white(result)
    assert result.black_ratio < 0.2


def test_frames_are_removed_but_the_drawing_stays(line_art):
    image = Image.open(BytesIO(line_art)).convert("L")
    ImageDraw.Draw(image).rectangle((10, 10, 889, 1189), outline=0, width=8)
    with_frame = lineart.clean(png_bytes(image), "6-8")
    without = lineart.clean(line_art, "6-8")
    assert abs(with_frame.black_ratio - without.black_ratio) < 0.01


def test_draft_engine_produces_a_cleanable_drawing(photo):
    result = lineart.clean(lineart.draft(photo, "cartoon", "6-8"), "6-8")
    assert _only_black_and_white(result)
    assert (_pixels(result) == 0).any()


def _pencil_page() -> bytes:
    """Two pencil circles: each has a short dark arc and the rest in light gray. A flat gray
    patch (shading) and a lone faint scribble that touches no dark line."""
    image = Image.new("L", (1200, 1200), 255)
    draw = ImageDraw.Draw(image)
    for box in ((100, 100, 550, 550), (650, 100, 1100, 550)):
        draw.ellipse(box, outline=185, width=4)  # light pencil, above MAX_THRESHOLD
        draw.arc(box, 200, 260, fill=40, width=4)  # one dark stretch
    draw.rectangle((100, 700, 500, 1100), fill=200)  # flat shading
    draw.line((700, 800, 1100, 900), fill=190, width=3)  # faint, not connected to any dark line
    return png_bytes(image.convert("RGB"))


def _enclosed_white(result: lineart.CleanResult) -> int:
    """White areas that do not touch the image border: closed shapes a child can color."""
    white = (_pixels(result) > 127).astype(np.uint8)
    n, labels = __import__("cv2").connectedComponents(white, connectivity=4)
    border = set(np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]])))
    return len(set(range(1, n)) - border)


def test_sketch_mode_keeps_faint_lines_that_continue_dark_ones():
    data = _pencil_page()
    plain = lineart.clean(data, "9+")
    sketch = lineart.clean(data, "9+", sketch=True)
    assert _only_black_and_white(sketch)
    assert _enclosed_white(plain) == 0  # only the dark arcs survive: open shapes
    assert _enclosed_white(sketch) == 2  # both circles closed
    # The shading and the lone faint line stay out: the page is the two circles.
    h, w = _pixels(sketch).shape
    assert w > 1.8 * h


def test_sketch_mode_leaves_solid_line_art_alone(line_art):
    plain, sketch = lineart.clean(line_art, "6-8"), lineart.clean(line_art, "6-8", sketch=True)
    # The antialiased edge of a solid line is all it adds: one pixel, same areas to color.
    assert abs(sketch.image.size[0] - plain.image.size[0]) <= 4
    assert sketch.regions == plain.regions and sketch.warnings == plain.warnings
    assert abs(sketch.black_ratio - plain.black_ratio) < 0.01
