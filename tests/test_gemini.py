import json
from types import SimpleNamespace as NS

import pytest

from app.core import gemini, usage


def _part(data=None, thought=None):
    return NS(inline_data=NS(data=data) if data else None, thought=thought)


def test_generate_image_returns_the_final_image_not_the_thinking_drafts(monkeypatch):
    parts = [_part(thought=True), _part(b"draft", thought=True), _part(thought=True), _part(b"final")]
    response = NS(candidates=[NS(content=NS(parts=parts), finish_reason="STOP")], usage_metadata=None)
    monkeypatch.setattr(gemini, "_client", lambda location: NS(models=NS(generate_content=lambda **kwargs: response)))
    monkeypatch.setattr(usage, "record", lambda *args, **kwargs: None)
    assert gemini.generate_image("a cat") == b"final"


def test_generate_image_fails_when_only_drafts_come_back(monkeypatch):
    response = NS(candidates=[NS(content=NS(parts=[_part(b"draft", thought=True)]), finish_reason="STOP")], usage_metadata=None)
    monkeypatch.setattr(gemini, "_client", lambda location: NS(models=NS(generate_content=lambda **kwargs: response)))
    monkeypatch.setattr(usage, "record", lambda *args, **kwargs: None)
    with pytest.raises(gemini.GeminiError):
        gemini.generate_image("a cat")


def test_thinking_tokens_are_billed_at_the_text_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(usage, "USAGE_FILE", tmp_path / "usage.jsonl")
    metadata = NS(prompt_token_count=1000, candidates_token_count=1120, thoughts_token_count=500)
    with usage.book_context("book-1"):
        usage.record("image_generation", "gemini-3-pro-image", metadata, images=1)
    entry = json.loads((tmp_path / "usage.jsonl").read_text())
    assert entry["book"] == "book-1"
    assert (entry["input_tokens"], entry["output_tokens"], entry["thinking_tokens"]) == (1000, 1620, 500)
    assert entry["cost_usd"] == pytest.approx(1000 * 2 / 1e6 + 1120 * 120 / 1e6 + 500 * 12 / 1e6)
    assert usage.summarize([entry])["tokens"] == 2620
