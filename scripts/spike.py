"""Prompt spike: convert test photos in every style and age group, clean them, tile the results.

Run inside the container (spike/ is git-ignored and not mounted by default):

    docker compose run --rm -v ./spike:/workspace/spike app \
        python -m scripts.spike spike/photos spike/out

Writes ``<out>/<photo>/<style>-<age>-raw.png`` and ``-clean.png``, ``<out>/results.json`` and
one contact sheet per photo, ``<out>/<photo>-sheet.jpg``. ``--jobs toucan:cartoon:3-5 ...`` runs
only those conversions; ``--reclean`` re-runs ``lineart.clean`` on the raw files already in
``<out>`` without calling Gemini. ``--engine stable_diffusion`` draws with the Stable Diffusion
server instead (``STABLE_DIFFUSION_URL``), one page at a time.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.core import imaging, lineart, stable_diffusion, usage

# Scenes keep their setting; single subjects get a simplified one (the book default).
BACKGROUNDS = {"las-lajas": "keep", "pigeons": "keep"}
TITLES = {"toucan": "Keel-billed toucan", "las-lajas": "Las Lajas Sanctuary"}
TILE = 480


def convert(photo: Path, style: str, age: str, out: Path, engine: str = "gemini") -> dict:
    name = photo.stem
    background = BACKGROUNDS.get(name, "simplify")
    image = lineart.load_image(photo.read_bytes())
    result = {"photo": name, "style": style, "age": age, "background": background, "engine": engine}
    start = time.time()
    try:
        with usage.book_context("spike"):
            if engine == "stable_diffusion":
                raw = stable_diffusion.edit_image(image, imaging.build_sd_prompt(style, age, background))
            else:
                prompt = imaging.build_prompt(style, age, background, TITLES.get(name, ""))
                raw = imaging.render_coloring_page(photo.read_bytes(), image.size, prompt)
    except imaging.AI_ERRORS as exc:
        return {**result, "error": str(exc), "seconds": round(time.time() - start, 1)}
    (out / name).mkdir(parents=True, exist_ok=True)
    (out / name / f"{style}-{age}-raw.png").write_bytes(raw)
    cleaned = lineart.clean(raw, age)
    cleaned.image.save(out / name / f"{style}-{age}-clean.png")
    return {
        **result,
        "seconds": round(time.time() - start, 1),
        "raw_size": Image.open(out / name / f"{style}-{age}-raw.png").size,
        "warnings": cleaned.warnings,
        "stroke_px": cleaned.stroke_px,
        "black_ratio": cleaned.black_ratio,
        "regions": cleaned.regions,
    }


def reclean(raw: Path, out: Path) -> dict:
    name = raw.parent.name
    style, age = raw.name.removesuffix("-raw.png").split("-", 1)
    cleaned = lineart.clean(raw.read_bytes(), age)
    cleaned.image.save(raw.with_name(f"{style}-{age}-clean.png"))
    return {
        "photo": name, "style": style, "age": age, "warnings": cleaned.warnings,
        "stroke_px": cleaned.stroke_px, "black_ratio": cleaned.black_ratio, "regions": cleaned.regions,
    }


def _tile(image: Image.Image | None, label: str, font: ImageFont.ImageFont) -> Image.Image:
    tile = Image.new("RGB", (TILE, TILE + 28), "white")
    if image is not None:
        image = image.convert("RGB")
        image.thumbnail((TILE - 8, TILE - 8))
        tile.paste(image, ((TILE - image.width) // 2, 4 + (TILE - 8 - image.height) // 2))
    ImageDraw.Draw(tile).text((8, TILE + 4), label, fill="black", font=font)
    return tile


def contact_sheet(photo: Path, results: list[dict], out: Path, styles: list[str], ages: list[str]) -> None:
    font = ImageFont.load_default(size=18)
    sheet = Image.new("RGB", ((len(ages) + 1) * TILE, len(styles) * (TILE + 28)), "white")
    sheet.paste(_tile(lineart.load_image(photo.read_bytes()), photo.stem, font), (0, 0))
    for row, style in enumerate(styles):
        for col, age in enumerate(ages, start=1):
            path = out / photo.stem / f"{style}-{age}-clean.png"
            entry = next((r for r in results if r["photo"] == photo.stem and r["style"] == style and r["age"] == age), None)
            if entry is None:
                continue
            label = f"{style} {age}  " + ("ERROR" if "error" in entry else " ".join(entry["warnings"]))
            sheet.paste(_tile(Image.open(path) if path.exists() else None, label, font), (col * TILE, row * (TILE + 28)))
    sheet.save(out / f"{photo.stem}-sheet.jpg", quality=85)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("photos", type=Path)
    parser.add_argument("out", type=Path)
    parser.add_argument("--styles", nargs="+", default=list(imaging.STYLE_PROMPTS))
    parser.add_argument("--ages", nargs="+", default=list(lineart.AGE_GROUPS))
    parser.add_argument("--only", nargs="*", help="photo stems to run (default: all)")
    parser.add_argument("--jobs", nargs="*", help="photo:style:age triples (default: every combination)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--reclean", action="store_true")
    parser.add_argument("--engine", choices=("gemini", "stable_diffusion"), default="gemini")
    args = parser.parse_args()

    photos = sorted(p for p in args.photos.glob("*.jpg") if not args.only or p.stem in args.only)
    if args.reclean:
        results = [reclean(raw, args.out) for photo in photos for raw in sorted((args.out / photo.stem).glob("*-raw.png"))]
        for result in results:
            print(json.dumps(result))
    else:
        if args.jobs:
            by_stem = {p.stem: p for p in photos}
            jobs = [(by_stem[name], style, age) for name, style, age in (job.split(":") for job in args.jobs)]
            photos = sorted({job[0] for job in jobs})
        else:
            jobs = [(p, s, a) for p in photos for s in args.styles for a in args.ages]
        workers = 1 if args.engine == "stable_diffusion" else args.workers  # the server draws one at a time
        print(f"{len(jobs)} conversions, {workers} at a time")
        args.out.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(workers) as pool:
            results = []
            for result in pool.map(lambda job: convert(*job, args.out, args.engine), jobs):
                print(json.dumps(result))
                results.append(result)
    (args.out / "results.json").write_text(json.dumps(results, indent=2))
    for photo in photos:
        contact_sheet(photo, results, args.out, args.styles, args.ages)


if __name__ == "__main__":
    main()
