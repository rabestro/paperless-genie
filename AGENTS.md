# Agent Guidelines for paperless-genie

This document defines the rules, stack, standards, and workflow conventions for AI agents collaborating on the `paperless-genie` project. It is canonical; `CLAUDE.md` and `GEMINI.md` are thin shims that point here.

## Stack & Architecture

- **Core**: Python 3.14, the single supported version — no compatibility matrix (managed with `uv` package manager).
- **Telegram Bot**: Async Telegram Bot (`pyTelegramBotAPI`/`telebot.async_telebot`).
- **AI Integration**: Google Antigravity SDK (`Agent`, `LocalAgentConfig`, `CapabilitiesConfig`).
- **Paperless MCP tools**: [`@baruchiro/paperless-mcp`](https://github.com/baruchiro/paperless-mcp) (Node.js 24+),
  invoked directly by its pinned, pre-installed binary — never through `npx` at request time.
  Bump the version in both the Dockerfile's `PAPERLESS_MCP_VERSION` build arg and README.md.
- **HTTP client**: `httpx` (async).
- **Formatting / Linting**: `ruff` (linter and formatter).
- **Type Checking**: `mypy` (strict mode).
- **Testing**: `pytest`.
- **Infrastructure**: Docker, Docker Compose, GitHub Actions.

## Quality & Checks

The `mise run` tasks are the canonical local commands (defined in `mise.toml`);
the raw `uv run` form each wraps is shown alongside. Before submitting any code
changes, ensure they pass the local check suite:
- Format code: `mise run format` (`uv run ruff format src tests && uv run ruff check src tests --fix`)
- Lint code: `mise run lint` (`uv run ruff check src tests`)
- Type check: `mise run mypy` (`uv run mypy src`)
- Run unit tests: `mise run test` (`uv run pytest`)
- Check all files with pre-commit: `uv run pre-commit run --all-files`

Run a single test by node id or keyword, e.g.
`uv run pytest tests/test_paperless.py -k duplicate`.

## Git & PR Workflow

- **Branch Naming**: Use conventions: `<type>/<short-desc>` (e.g. `feat/ocr-polling`, `fix/token-exhaustion`, `ci/add-checks`).
  - Allowed types: `feat`, `fix`, `refactor`, `chore`, `docs`, `ci`, `test`, `perf`.
- **Commits**: Follow Conventional Commits style (e.g. `feat: ...`, `fix: ...`, `chore: ...`).
- **Language**: All repository text — commits, PR descriptions, issues, code comments, and docstrings — is English only.
- **Staging**: Explicitly stage files by name. Avoid `git add .` or `git add -A`.
- **Deployment**: Production runs on remote server `aurora` in `~/paperless-genie` using the Docker image published to GHCR.

## Automated PR review

- Every non-fork PR gets an automatic Gemini review (`gemini-review.yml`, Vertex AI).
- CodeRabbit is triggered manually: comment `@coderabbitai review` on PRs that warrant
  a second opinion (free-tier limit is roughly one review per hour — spend it on the
  important PRs).
- Treat bot findings as hypotheses, not verdicts. Verify factual claims (package
  versions, API existence, release status) against authoritative sources before
  acting — bot reviewers have shipped confidently wrong claims here before. Apply
  what holds up; rebut what doesn't, with evidence, in a PR comment.

## Security & boundaries

- Never print, log, or commit secrets. Local secrets live only in `.env` (gitignored).
- Never bypass Git hooks (`--no-verify`).
- Deployments, tag generation, and PR merges are human-approved operations. Propose them, but do not execute them automatically.
