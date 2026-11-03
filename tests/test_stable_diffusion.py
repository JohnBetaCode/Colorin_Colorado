import base64
import json
from io import BytesIO
from types import SimpleNamespace as NS

import pytest
import requests
from PIL import Image, ImageDraw

from app.core import books, config, imaging, kdp, pages, stable_diffusion, usage

from .conftest import png_bytes


def _drawing(size: tuple[int, int]) -> bytes:
    """What the server sends back: a few black outlines on white."""
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((size[0] // 4, size[1] // 4, size[0] * 3 // 4, size[1] * 3 // 4), outline="black", width=6)
    draw.rectangle((20, 20, size[0] - 20, size[1] - 20), outline="black", width=6)
    return png_bytes(image)


class FakeServer:
    """Answers like sd-server: ``fail`` lists what the first calls do (a status code or an exception)."""

    def __init__(self, fail=()):
        self.fail = list(fail)
        self.posts, self.gets = [], []

    def post(self, url, files, data, timeout):
        self.posts.append(NS(url=url, files=files, data=data, timeout=timeout))
        if self.fail:
            outcome = self.fail.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return NS(status_code=outcome, text="busy", raise_for_status=self._raiser(outcome))
        width, height = (int(n) for n in data["size"].split("x"))
        body = {"data": [{"b64_json": base64.b64encode(_drawing((width, height))).decode()}]}
        return NS(status_code=200, json=lambda: body, raise_for_status=lambda: None)

    def get(self, url, timeout):
        self.gets.append(url)
        return NS(json=lambda: {"state": "ready"}, raise_for_status=lambda: None)

    @staticmethod
    def _raiser(status):
        def raise_for_status():
            if status >= 400:
                raise requests.HTTPError(f"{status} error")

        return raise_for_status


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("STABLE_DIFFUSION_URL", "http://sd.test:8081/")
    monkeypatch.setenv("STABLE_DIFFUSION_STEPS", "10")
    monkeypatch.setenv("STABLE_DIFFUSION_SIZE", "768")
    monkeypatch.setattr(usage, "USAGE_FILE", tmp_path / "usage.jsonl")
    monkeypatch.setattr(stable_diffusion.time, "sleep", lambda seconds: None)
    fake = FakeServer()
    monkeypatch.setattr(stable_diffusion.requests, "post", fake.post)
    monkeypatch.setattr(stable_diffusion.requests, "get", fake.get)
    return fake


def test_settings_are_off_by_default_and_clamped(monkeypatch):
    for key in ("STABLE_DIFFUSION_URL", "STABLE_DIFFUSION_STEPS", "STABLE_DIFFUSION_SIZE"):
        monkeypatch.delenv(key, raising=False)
    settings = config.get_settings()
    assert not settings.sd_configured and (settings.sd_steps, settings.sd_size) == (12, 768)
    monkeypatch.setenv("STABLE_DIFFUSION_URL", " http://sd.test:8081/ ")
    monkeypatch.setenv("STABLE_DIFFUSION_STEPS", "200")
    monkeypatch.setenv("STABLE_DIFFUSION_SIZE", "lots")
    settings = config.get_settings()
    assert settings.sd_configured and settings.sd_url == "http://sd.test:8081"
    assert (settings.sd_steps, settings.sd_size) == (config.SD_STEPS_RANGE[1], 768)


def test_the_photo_goes_small_with_the_steps_and_comes_back_as_png(server, tmp_path):
    png = stable_diffusion.edit_image(Image.new("RGB", (2000, 1333), "gray"), "Make it a coloring page.")
    sent = server.posts[0]
    assert sent.url == "http://sd.test:8081/v1/images/edits" and sent.timeout >= 600
    assert sent.data["size"] == "768x512"
    assert Image.open(BytesIO(sent.files[0][1][1])).size == (768, 512)
    assert sent.data["prompt"].startswith("Make it a coloring page. <sd_cpp_extra_args>")
    assert '"sample_steps": 10' in sent.data["prompt"]
    assert Image.open(BytesIO(png)).size == (768, 512)
    entry = json.loads((tmp_path / "usage.jsonl").read_text())
    assert (entry["model"], entry["images"], entry["cost_usd"]) == ("stable-diffusion", 1, 0.0)


def test_sizes_are_multiples_of_8():
    assert stable_diffusion.request_size(1280, 1706, 768) == (576, 768)
    assert stable_diffusion.request_size(1280, 1558, 768) == (632, 768)


def test_a_busy_or_restarting_server_is_retried(server):
    server.fail = [503, requests.ConnectionError("restarting")]
    assert stable_diffusion.edit_image(Image.new("RGB", (100, 100)), "x")
    assert len(server.posts) == 3


def test_failures_raise_a_clear_error(server, monkeypatch):
    server.fail = [requests.Timeout("slow")] * 3
    with pytest.raises(stable_diffusion.StableDiffusionError, match="slow"):
        stable_diffusion.edit_image(Image.new("RGB", (100, 100)), "x")
    server.fail, server.posts = [400], []
    with pytest.raises(stable_diffusion.StableDiffusionError):  # a bad request is not retried
        stable_diffusion.edit_image(Image.new("RGB", (100, 100)), "x")
    assert len(server.posts) == 1
    monkeypatch.setenv("STABLE_DIFFUSION_URL", "")
    with pytest.raises(stable_diffusion.StableDiffusionError, match="not configured"):
        stable_diffusion.edit_image(Image.new("RGB", (100, 100)), "x")


def test_the_connection_test_does_not_wake_the_model(server):
    assert stable_diffusion.check_connection() == "ready"
    assert server.gets == ["http://sd.test:8081/sdcpp/v1/models/status"]


def test_prompts_are_short_and_follow_age_style_and_background():
    prompt = imaging.build_sd_prompt("cartoon", "3-5", "remove", "only the bird")
    assert "ages 3 to 5" in prompt and "cartoon" in prompt and "plain white" in prompt
    assert prompt.endswith("only the bird") and len(prompt) < 600
    for style in imaging.STYLE_PROMPTS:
        for age in imaging.AGE_PROMPTS:
            for background in imaging.BACKGROUND_PROMPTS:
                assert imaging.build_sd_prompt(style, age, background)


def test_a_page_converted_with_stable_diffusion_is_cleaned_and_declared_as_ai(server, photo):
    book = books.create_book("Difusión")
    page = pages.add_photo(book.slug, "foto.png", photo)
    page = imaging.convert_page(book, page, "stable_diffusion")
    version = page.selected_version
    assert version.engine == "stable_diffusion"
    assert Image.open(pages.version_path(book.slug, page.id, version.n)).mode == "1"
    assert server.posts[0].data["size"] == "768x576"
    assert kdp._uses_ai(page)


def test_a_failed_page_does_not_stop_the_others(server, photo):
    book = books.create_book("Difusión")
    first = pages.add_photo(book.slug, "a.png", photo)
    second = pages.add_photo(book.slug, "b.png", photo)
    server.fail = [400]
    failures = imaging.convert_pages(book, [first, second], "stable_diffusion")
    assert len(failures) == 1
    assert sum(bool(p.versions) for p in pages.load_pages(book.slug)) == 1
