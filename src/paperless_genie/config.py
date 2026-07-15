import json
import os


class Config:
    """Configuration provider for paperless-genie."""

    TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    PAPERLESS_URL: str = os.environ.get("PAPERLESS_URL", "")

    # Mapping of Telegram user IDs to Paperless API tokens
    USER_TOKENS: dict[int, str] = {}

    @classmethod
    def validate(cls) -> None:
        """Validates that all required environment variables are set and correct.

        Raises:
            ValueError: If any required configuration is missing or invalid.
        """
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set!")
        if not cls.PAPERLESS_URL:
            raise ValueError("PAPERLESS_URL environment variable is not set!")

        raw_tokens = os.environ.get("PAPERLESS_USER_TOKENS", "")
        if not raw_tokens:
            raise ValueError("PAPERLESS_USER_TOKENS environment variable is not set!")
        try:
            tokens_dict = json.loads(raw_tokens)
            cls.USER_TOKENS = {int(k): str(v) for k, v in tokens_dict.items()}
        except (json.JSONDecodeError, ValueError) as e:
            raise ValueError(f"Failed to parse PAPERLESS_USER_TOKENS JSON mapping: {e}") from e

    @classmethod
    def get_token_for_user(cls, user_id: int) -> str:
        """Retrieves the Paperless API token mapped to a Telegram user ID.

        Args:
            user_id: The Telegram user ID.

        Returns:
            The Paperless API token.

        Raises:
            KeyError: If the user ID is not mapped to any token.
        """
        if user_id not in cls.USER_TOKENS:
            raise KeyError(f"User ID {user_id} is not authorized.")
        return cls.USER_TOKENS[user_id]
