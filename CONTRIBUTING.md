# Contributing

Thank you for considering a contribution to Paperless Genie! This document covers the
practical side: signing the CLA, setting up a development environment, and getting a
pull request merged.

## Contributor License Agreement

Before your first pull request can be accepted, you must sign the project's
[Contributor License Agreement](CLA.md). Signing is self-service: append yourself to
the `signatures` array in [`.github/cla-signatures.json`](.github/cla-signatures.json)
in the same pull request (see [CLA.md](CLA.md), "How to Sign"). The `CI: CLA` status
check fails until the entry is present. Repository-owner and bot pull requests are
exempt.

Why a CLA: the project follows an open-core model. The public repository is
AGPL-3.0, and the project owner retains the ability to combine the code with
closed-source modules and to offer it under additional licenses. The CLA preserves
that option while your contribution always remains available under AGPL-3.0 — and
you keep the copyright to your work. A plain DCO (`Signed-off-by`) would not grant
relicensing rights, which is why a CLA is used instead.

## Development Setup

Prerequisites: [mise](https://mise.jdx.dev/) (manages Python and uv) and, for running
the bot locally, Node.js 24+ with the pinned Paperless MCP server (see the README's
local setup section for the exact version).

```bash
mise install                 # Python 3.14 + uv
uv sync --all-groups         # project + dev + docs dependency groups
uv run pre-commit install    # git hooks (ruff, mypy, secret scanning, hygiene)
```

Running the bot end-to-end additionally needs a Telegram bot token, a Paperless-ngx
instance, and a Gemini API key — see the README's Configuration section.

## Quality Checks

Every pull request must pass the same suite CI runs:

```bash
mise run format   # ruff format + ruff check --fix
mise run lint     # ruff check
mise run mypy     # strict type checking
mise run test     # pytest
uv run pre-commit run --all-files
```

Run a single test with `uv run pytest tests/test_config.py -k <name>`.

## Workflow

- **Branch** from `main` using `<type>/<short-desc>` — allowed types: `feat`, `fix`,
  `refactor`, `chore`, `docs`, `ci`, `test`, `perf`. Do not commit directly to `main`.
- **Commits** follow [Conventional Commits](https://www.conventionalcommits.org/)
  (`feat: ...`, `fix: ...`, `chore: ...`).
- **Language**: pull requests, commits, issues, code comments, and docstrings are
  English only.
- **Pull request**: reference the issue it addresses (`Closes #NN`) when one exists.
  Nontrivial behavior changes should come with tests.
- Machine-readable conventions for AI agents live in [AGENTS.md](AGENTS.md) — humans
  are welcome to read it too; it is the canonical rules file.

## Automated Review

Every non-fork pull request receives an automatic Gemini review; the maintainer may
additionally summon CodeRabbit with an `@coderabbitai review` comment. Findings from
either bot are hypotheses, not verdicts — maintainers verify factual claims before
acting on them, and so should you.

## Releases

Releases are cut by the maintainer; contributors never touch versioning in a pull
request. Because `main` requires a pull request, the version bump goes through one too:

1. `mise run release <patch|minor|major>` — bumps the version in `pyproject.toml` and
   `uv.lock` locally (via `uv version --bump`) and prints the remaining steps.
2. Commit the bump on a `release/vX.Y.Z` branch, open a PR, let CI pass, and merge it.
3. From an updated `main`, push the tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.

Pushing the tag (as a human, not a bot token, so the workflows actually trigger) builds
and publishes the image (`publish.yaml`) and creates the GitHub Release with generated,
label-categorized notes (`tag-release.yaml`).

## Security Issues

Please do not open public issues for vulnerabilities — see [SECURITY.md](SECURITY.md).
