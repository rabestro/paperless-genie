import pytest

from paperless_genie.config import Config


def test_config_validation_empty_token() -> None:
    Config.TELEGRAM_BOT_TOKEN = ""
    Config.ALLOWED_USER_IDS = [123]
    with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
        Config.validate()


def test_config_validation_empty_allowed_users() -> None:
    Config.TELEGRAM_BOT_TOKEN = "dummy-token"
    Config.ALLOWED_USER_IDS = []
    with pytest.raises(ValueError, match="ALLOWED_USER_IDS"):
        Config.validate()


def test_config_validation_success() -> None:
    Config.TELEGRAM_BOT_TOKEN = "dummy-token"
    Config.ALLOWED_USER_IDS = [123]
    # Should not raise exception
    Config.validate()
