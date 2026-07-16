import pytest

from paperless_genie.config import Config


def test_config_validation_empty_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://localhost:8000")
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Config.validate()


def test_config_validation_empty_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "dummy-token")
    monkeypatch.setattr(Config, "PAPERLESS_URL", "")
    with pytest.raises(ValueError, match="PAPERLESS_URL"):
        Config.validate()


def test_config_validation_empty_gemini_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "dummy-token")
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setattr(Config, "GEMINI_API_KEY", "")
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        Config.validate()


def test_config_validation_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "dummy-token")
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setattr(Config, "GEMINI_API_KEY", "dummy-gemini-key")
    monkeypatch.setenv("PAPERLESS_USER_TOKENS", "invalid-json")
    with pytest.raises(ValueError, match="Failed to parse PAPERLESS_USER_TOKENS"):
        Config.validate()


def test_config_validation_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "TELEGRAM_BOT_TOKEN", "dummy-token")
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://localhost:8000")
    monkeypatch.setattr(Config, "GEMINI_API_KEY", "dummy-gemini-key")
    monkeypatch.setattr(Config, "USER_TOKENS", {})
    monkeypatch.setenv("PAPERLESS_USER_TOKENS", '{"12345678": "token"}')
    Config.validate()
    assert Config.get_token_for_user(12345678) == "token"
