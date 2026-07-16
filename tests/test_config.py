import os

import pytest

from paperless_genie.config import Config


def test_config_validation_empty_token() -> None:
    Config.TELEGRAM_BOT_TOKEN = ""
    Config.PAPERLESS_URL = "http://localhost:8000"
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Config.validate()


def test_config_validation_empty_url() -> None:
    Config.TELEGRAM_BOT_TOKEN = "dummy-token"
    Config.PAPERLESS_URL = ""
    with pytest.raises(ValueError, match="PAPERLESS_URL"):
        Config.validate()


def test_config_validation_empty_gemini_api_key() -> None:
    Config.TELEGRAM_BOT_TOKEN = "dummy-token"
    Config.PAPERLESS_URL = "http://localhost:8000"
    Config.GEMINI_API_KEY = ""
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        Config.validate()


def test_config_validation_invalid_json() -> None:
    Config.TELEGRAM_BOT_TOKEN = "dummy-token"
    Config.PAPERLESS_URL = "http://localhost:8000"
    Config.GEMINI_API_KEY = "dummy-gemini-key"
    os.environ["PAPERLESS_USER_TOKENS"] = "invalid-json"
    with pytest.raises(ValueError, match="Failed to parse PAPERLESS_USER_TOKENS"):
        Config.validate()


def test_config_validation_success() -> None:
    Config.TELEGRAM_BOT_TOKEN = "dummy-token"
    Config.PAPERLESS_URL = "http://localhost:8000"
    Config.GEMINI_API_KEY = "dummy-gemini-key"
    os.environ["PAPERLESS_USER_TOKENS"] = '{"12345678": "token"}'
    Config.validate()
    assert Config.get_token_for_user(12345678) == "token"
