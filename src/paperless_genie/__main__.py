"""Entry point: validates configuration and starts the bot polling loop."""

import asyncio
import logging

from paperless_genie.config import Config

# Validate config before initializing the bot to avoid import-time crashes
Config.validate()

from paperless_genie.bot import bot  # noqa: E402

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("paperless_genie")


async def main() -> None:
    """Starts the Telegram Bot polling loop."""
    logger.info("Starting Telegram Bot (paperless-genie)...")
    await bot.polling(non_stop=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
