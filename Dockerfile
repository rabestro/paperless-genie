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

# Install system dependencies and Node.js (required to run the Paperless MCP server)
# Node 24+ is required by @baruchiro/paperless-mcp's engines constraint.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_24.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Pre-install an exact pinned version of the Paperless MCP server so message
# handling never fetches package code from npm at request time. Bump this
# alongside the version documented in README.md's local setup instructions.
ARG PAPERLESS_MCP_VERSION=2.0.0
RUN npm install -g "@baruchiro/paperless-mcp@${PAPERLESS_MCP_VERSION}" \
    && npm cache clean --force

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
