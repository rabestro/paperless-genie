# Configuration Guide

All configurations in `paperless-genie` are set using environment variables. These can be defined in a `.env` file in the root of the project or passed directly to Docker / systemd.

---

## ⚙️ Environment Variables Reference

| Variable | Description | Required | Example |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token obtained from `@BotFather`. | Yes | `123456789:ABCdefGhI...` |
| `PAPERLESS_URL` | Base URL of your Paperless-ngx instance. | Yes | `https://paperless.example.com` |
| `GEMINI_API_KEY` | API Key from Google AI Studio. | Yes | `AIzaSyD...` |
| `GEMINI_MODEL` | Gemini model to use. Defaults to `gemini-3.1-flash-lite`. | No | `gemini-3.1-flash-lite` |
| `PAPERLESS_USER_TOKENS` | JSON mapping of Telegram User IDs to Paperless API Tokens. | Yes | See mapping section below. |

---

## 👥 Setting up `PAPERLESS_USER_TOKENS` Mapping

The `PAPERLESS_USER_TOKENS` variable maps a user's Telegram User ID to their Paperless API token. It must be formatted as a valid single-line JSON string:

```json
{"52966251": "your_paperless_token", "12345678": "brother_paperless_token"}
```

### Formatting for `.env`

Ensure the JSON string is wrapped in single quotes to prevent terminal shell parsing issues:

```ini
PAPERLESS_USER_TOKENS='{"52966251": "your_paperless_token", "12345678": "brother_paperless_token"}'
```

### Verification

When the bot starts up, it automatically validates:
1. That the JSON string is correctly formatted.
2. That all Telegram User IDs are integers.
If configuration validation fails, the bot will log a detailed error and exit immediately to prevent running in an unconfigured state.
