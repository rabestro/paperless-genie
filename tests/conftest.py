# Importing paperless_genie.bot constructs AsyncTeleBot(Config.TELEGRAM_BOT_TOKEN)
# at module load time, and telebot rejects tokens that aren't "<digits>:<rest>".
# Set a syntactically valid placeholder before any test module can trigger that
# import, unless a real value is already present in the environment.
import os

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-token")
