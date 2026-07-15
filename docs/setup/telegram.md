# Telegram Bot Creation Guide

To use `paperless-genie`, you need to register a new bot with Telegram and obtain a **Telegram Bot Token**.

---

## 🤖 Step-by-Step Registration

1. **Find BotFather**: Open Telegram and search for `@BotFather` (the official bot used to create and manage other bots).
2. **Create New Bot**: Send the `/newbot` command to BotFather.
3. **Choose Name**: BotFather will ask for a name. Enter a friendly name for your bot (e.g., `Paperless Genie`).
4. **Choose Username**: Choose a unique username that ends with `bot` (e.g., `my_paperless_archive_bot`).
5. **Get Token**: Once created, BotFather will message you a **HTTP API Token** (e.g., `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`). Copy this token; you will need it for the `TELEGRAM_BOT_TOKEN` environment variable.

---

## 🔒 Get Your Telegram User ID

Since `paperless-genie` only responds to authorized users, you need to find your Telegram User ID:

1. Search for `@userinfobot` or `@GetIDsBot` in Telegram.
2. Start a conversation with it.
3. It will reply with your unique **Id** (a numeric value like `52966251`).
4. Keep this ID handy; you will map it to your Paperless API Token in the configuration step.
