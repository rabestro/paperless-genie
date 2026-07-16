# Use Python slim base image
FROM python:3.14-slim

# OCI standard image labels (static metadata)
# Dynamic labels — version, created, revision — are injected by CI (docker/metadata-action)
LABEL org.opencontainers.image.title="Paperless Genie" \
      org.opencontainers.image.description="AI-powered Telegram bot for Paperless-ngx" \
      org.opencontainers.image.authors="Jegors Čemisovs <jegors.cemisovs@gmail.com>" \
      org.opencontainers.image.url="https://github.com/rabestro/paperless-genie" \
      org.opencontainers.image.source="https://github.com/rabestro/paperless-genie" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

# Install system dependencies and Node.js (required to run Node-based MCP servers via npx)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency configuration files
COPY pyproject.toml uv.lock README.md ./

# Install python dependencies (cached layer)
RUN uv sync --frozen --no-dev --no-install-project

# Copy project source code
COPY src/ ./src/

# Install the project package itself
RUN uv sync --frozen --no-dev

# Set entry point to launch the bot
CMD ["uv", "run", "python", "-m", "paperless_genie"]
