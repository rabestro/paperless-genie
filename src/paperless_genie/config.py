import os


class Config:
    TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    ALLOWED_USER_IDS: list[int] = [
        int(x.strip()) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip()
    ]
    WORKSPACE_PATH: str = os.environ.get("WORKSPACE_PATH", "/data/Latvia")

    @classmethod
    def validate(cls) -> None:
        if not cls.TELEGRAM_BOT_TOKEN:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set!")
        if not cls.ALLOWED_USER_IDS:
            raise ValueError("ALLOWED_USER_IDS environment variable is empty or not set!")
        if not os.path.exists(cls.WORKSPACE_PATH):
            # We don't raise error, just log a warning or let it run
            pass
