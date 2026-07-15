# Use Python slim base image
FROM python:3.13-slim

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
COPY --from=astral-sh/setup-uv:latest /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency configuration files
COPY pyproject.toml uv.lock ./

# Install python dependencies (cached layer)
RUN uv sync --frozen --no-dev --no-install-project

# Copy project source code
COPY src/ ./src/

# Install the project package itself
RUN uv sync --frozen --no-dev

# Set entry point to launch the bot
CMD ["uv", "run", "python", "-m", "paperless_genie"]
