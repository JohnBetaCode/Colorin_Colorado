import pytest

from app.core import config, gemini


@pytest.fixture
def env(monkeypatch):
    for key in ("GEMINI_AUTH", "GEMINI_API_KEY", "GOOGLE_CLOUD_PROJECT"):
        monkeypatch.delenv(key, raising=False)
    gemini.reset_clients()
    yield monkeypatch
    gemini.reset_clients()


def test_google_cloud_needs_a_project_and_keys_need_a_key(env):
    assert config.get_settings().auth == "adc" and not config.get_settings().configured
    env.setenv("GOOGLE_CLOUD_PROJECT", "demo-project")
    assert config.get_settings().configured
    env.setenv("GEMINI_AUTH", "studio_key")
    assert not config.get_settings().configured
    env.setenv("GEMINI_API_KEY", " key ")
    assert config.get_settings().configured and config.get_settings().api_key == "key"
    env.setenv("GEMINI_AUTH", "something-else")
    assert config.get_settings().auth == "adc"


@pytest.mark.parametrize("auth, vertexai", [("studio_key", False), ("vertex_key", True)])
def test_api_keys_pick_the_backend(env, auth, vertexai):
    env.setenv("GEMINI_AUTH", auth)
    env.setenv("GEMINI_API_KEY", "test-key")
    client = gemini._client("global")
    assert bool(client.vertexai) is vertexai
    assert client._api_client.api_key == "test-key"
