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

# Create an unprivileged user to run the bot as — it needs no elevated
# privileges. Created early so this layer is cache-independent of source
# changes.
RUN groupadd --system app \
    && useradd --system --gid app --create-home --home-dir /home/app --shell /usr/sbin/nologin app

# Pre-install an exact pinned version of the Paperless MCP server so message
# handling never fetches package code from npm at request time. Bump this
# alongside the version documented in README.md's local setup instructions.
ARG PAPERLESS_MCP_VERSION=2.0.0
RUN npm install -g "@baruchiro/paperless-mcp@${PAPERLESS_MCP_VERSION}" \
    && npm cache clean --force

# Install uv for fast dependency management (version pinned for reproducible builds)
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/

# Create the working directory owned by the unprivileged user and switch to
# it now, before any application files are copied in — every COPY/RUN below
# then runs as that user directly, instead of needing a `chown -R` afterward
# that would otherwise copy-up the whole dependency tree into a new layer.
RUN mkdir /app && chown app:app /app
WORKDIR /app
ENV HOME=/home/app
USER app

# Copy dependency configuration files
COPY --chown=app:app pyproject.toml uv.lock README.md ./

# Install python dependencies (cached layer)
RUN uv sync --frozen --no-dev --no-install-project

# Copy project source code
COPY --chown=app:app src/ ./src/

# Install the project package itself
RUN uv sync --frozen --no-dev

# Set entry point to launch the bot
CMD ["uv", "run", "python", "-m", "paperless_genie"]
