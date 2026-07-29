# Paperless Genie 🧞

Welcome to the **Paperless Genie** documentation!

`paperless-genie` is an intelligent, conversational AI Telegram bot for **Paperless-ngx** built using the **Google Antigravity SDK** (`google-antigravity`). It allows you to search and manage your document archive using natural language, directly from Telegram.

<p align="center">
  <img src="assets/demo.gif" alt="Demo: searching the archive, asking for a yearly utilities total with a follow-up comparison, and auto-archiving a document from a Telegram chat" width="360">
  <br>
  <sub><i>Illustrative demo — a mock-up chat with sample data, not a recording of a live instance.</i></sub>
</p>

---

## Key Features

* **Natural Language Queries**: Search your documents by asking questions like *"Where is my passport?"* or *"List all lease agreements from 1992"*.
* **Totals & Follow-Up Questions**: Ask analytical questions like *"How much did we spend on utilities in 2025?"* and refine them conversationally — *"And compared to 2024?"* — thanks to per-user conversation memory. See [Example Queries](examples.md) for more.
* **Smart PDF Archiving**: Send a PDF document via Telegram. The bot analyzes the document, extracts metadata, uploads it to Paperless-ngx, sets the tags/correspondent/date, and appends a detailed note.
* **Granular Multi-User Permissions**: Map Telegram User IDs to Paperless API Tokens so users only see and edit documents they have access to in your Paperless-ngx instance.
* **No Server Mount Required**: The bot interacts entirely via Paperless API and temporary folder paths, keeping your server clean.

---

## ⚠️ Hardware Requirements & CPU Compatibility

This bot relies on the **Google Antigravity SDK** (`google-antigravity`), which includes pre-compiled native Go binaries requiring specific CPU instruction extensions:

* **x86_64 / amd64**: Requires **AVX** instructions (Intel Haswell / 4th Gen 2013+ or AMD Bulldozer+).
  * ❌ *Not supported*: Older CPUs and many Synology NAS models (e.g., Intel Celeron J3455/J4125, Atom) without AVX. Crashes with `FATAL ERROR: This binary was compiled with avx enabled...` (see issue [#79](https://github.com/rabestro/paperless-genie/issues/79)).
* **ARM64 / aarch64**: Requires **ARM Cryptography Extensions (AES)**.
  * ❌ *Not supported*: **Raspberry Pi 3** and **Raspberry Pi 4** (Broadcom BCM2837 and BCM2711 lack hardware AES crypto extensions). Crashes with `FATAL ERROR: This binary was compiled with aes enabled...`.
  * ✅ *Supported*: **Raspberry Pi 5** (Broadcom BCM2712 / Cortex-A76), Apple Silicon, and modern ARM64 cloud servers.

---

## Quick Start

1. **Create a Telegram Bot**: Follow the [Telegram Bot Setup Guide](setup/telegram.md) to get a token.
2. **Get Paperless-ngx API Token**: Learn how to generate your API token in the [Paperless Setup Guide](setup/paperless.md).
3. **Configure Environment Variables**: Setup mappings and credentials in [Configuration Guide](setup/configuration.md).
4. **Deploy**: Choose to deploy using Docker Compose or systemd in the [Deployment Guide](deployment.md).
