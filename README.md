# Paperless Genie 🧞

An AI-powered Telegram bot for **Paperless-ngx** using the **Google Antigravity SDK** (`google-antigravity`).

[![Quality Checks](https://github.com/rabestro/paperless-genie/actions/workflows/ci.yaml/badge.svg)](https://github.com/rabestro/paperless-genie/actions/workflows/ci.yaml)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)

`paperless-genie` acts as an intelligent, conversational interface to your Paperless-ngx document archive. It runs completely conversational and doesn't require mounting local files on the server. It supports multiple users, routing actions to Paperless-ngx dynamically using the corresponding user's API token.

<p align="center">
  <img src="docs/assets/demo.gif" alt="Demo: searching the archive and auto-archiving a document from a Telegram chat" width="360">
  <br>
  <sub><i>Illustrative demo — a mock-up chat with sample data, not a recording of a live instance.</i></sub>
</p>

---

## 🚀 Key Features

* **Conversational Search & Query**: Ask questions about your archive in natural language (e.g., *"Find John Doe's passport"* or *"What contracts do we have from 1993?"*). The bot routes the query to an autonomous agent which uses Paperless-ngx MCP tools to find the answers.
* **Intelligent Document Archiving**: Upload a document (PDF, JPG, PNG and more) directly in Telegram. The bot downloads it to a temporary directory and runs the Antigravity agent to analyze its contents. The agent suggests metadata (Title, Date, Correspondent, Type, Tags), uploads the document via the `post_document` MCP tool, waits for OCR, sets the metadata, and writes a detailed note in Paperless. All responses are automatically delivered in the language you write in.
* **Multi-User Security & Permissions**: Mappings between Telegram User IDs and Paperless API Tokens ensure that each user can only search, see, and edit documents they have permissions to view in Paperless-ngx.
* **Modern Developer Tooling**: Orchestrated using `uv`, `mise`, `ruff` for formatting/linting, `mypy` for static typing, and `pytest` for tests.

---

## 🛠️ Configuration & Setup

### 1. Environment Variables

Create a `.env` file in the root folder of the project:

```ini
TELEGRAM_BOT_TOKEN="your_telegram_bot_token"
PAPERLESS_URL="https://your-paperless-instance.com"
GEMINI_API_KEY="your_google_ai_studio_gemini_api_key"

# JSON mapping between Telegram User IDs and their Paperless API Tokens
PAPERLESS_USER_TOKENS='{"52966251": "token_for_user_1", "12345678": "token_for_user_2"}'
```

### 2. Local Environment Setup

Make sure you have `mise` installed on your machine.

```bash
# Install Python 3.14 and uv
mise install

# Install project dependencies (dev + docs dependency groups included)
uv sync --all-groups

# Setup pre-commit hooks
uv run pre-commit install
```

The bot talks to Paperless-ngx through the [`@baruchiro/paperless-mcp`](https://github.com/baruchiro/paperless-mcp)
MCP server. Install Node.js 24+ and pre-install the exact pinned version globally so the
bot can find it on `PATH` (the Docker image does this automatically):

```bash
npm install -g @baruchiro/paperless-mcp@2.0.0
```

This version must match the `PAPERLESS_MCP_VERSION` build argument in the [Dockerfile](Dockerfile) —
when bumping one, bump the other.

### 3. Available Tasks (via `mise`)

* **Run the bot**: `mise run run`
* **Format code**: `mise run format`
* **Lint code**: `mise run lint`
* **Type check**: `mise run mypy`
* **Run tests**: `mise run test`

---

## 🐳 Docker Deployment (Recommended)

You can run the bot in the background using Docker and Docker Compose. This packages Node.js automatically so the bot can execute Node-based MCP servers.

### 1. Build and Start Container

Make sure you have created your `.env` file, then run:

```bash
docker compose up -d --build
```

### 2. View Logs

```bash
docker compose logs -f
```

---

## 📋 Production Deployment (systemd)

To run the bot in the background on your Linux server, create a systemd service file: `/etc/systemd/system/paperless-genie.service`

```ini
[Unit]
Description=Paperless Genie Telegram Bot
After=network.target

[Service]
Type=simple
User=your-linux-username
WorkingDirectory=/home/your-linux-username/Repositories/paperless-genie
ExecStart=/home/your-linux-username/Repositories/paperless-genie/.venv/bin/python -m paperless_genie
Restart=always
RestartSec=10
EnvironmentFile=/home/your-linux-username/Repositories/paperless-genie/.env

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl start paperless-genie
sudo systemctl enable paperless-genie
```

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for the
development setup, check suite, and workflow. First-time contributors sign the
[Contributor License Agreement](CLA.md) as part of their first pull request. We follow
the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md); security issues go
through [private vulnerability reporting](SECURITY.md), never public issues.

---

## 📝 License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.
See the [LICENSE](LICENSE) file for details.

This means that if you deploy a modified version of this bot as a network service,
you must make your modified source code publicly available under the same license.
