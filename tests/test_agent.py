import shutil
from collections.abc import AsyncIterator

import pytest

from paperless_genie import agent as agent_module
from paperless_genie.config import Config

_ALLOWED_MCP_ENV_KEYS = {
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "NODE_EXTRA_CA_CERTS",
} | {
    "PAPERLESS_URL",
    "PAPERLESS_API_TOKEN",
    "PAPERLESS_API_KEY",
}


# --- MCP environment allowlist ----------------------------------------------


def test_build_mcp_env_never_contains_bot_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:leaked-bot-token")
    monkeypatch.setenv("GEMINI_API_KEY", "leaked-gemini-key")
    monkeypatch.setenv("PAPERLESS_USER_TOKENS", '{"1": "leaked-other-users-token"}')
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leaked-unrelated-secret")
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://paperless.example")

    env = agent_module._build_mcp_env("this-users-token")

    assert set(env.keys()) <= _ALLOWED_MCP_ENV_KEYS
    assert env["PAPERLESS_API_TOKEN"] == "this-users-token"
    assert env["PAPERLESS_API_KEY"] == "this-users-token"
    assert env["PAPERLESS_URL"] == "http://paperless.example"


def test_build_mcp_env_forwards_allowlisted_plumbing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("HOME", "/home/genie")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:8080")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "/etc/ssl/internal-ca.pem")
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://paperless.example")

    env = agent_module._build_mcp_env("token")

    assert env["PATH"] == "/usr/bin:/bin"
    assert env["HOME"] == "/home/genie"
    assert env["HTTPS_PROXY"] == "http://proxy.example:8080"
    assert env["NODE_EXTRA_CA_CERTS"] == "/etc/ssl/internal-ca.pem"


def test_build_mcp_env_omits_absent_plumbing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://paperless.example")

    env = agent_module._build_mcp_env("token")

    assert "LANG" not in env
    assert "LC_ALL" not in env
    assert "TMPDIR" not in env


# --- MCP server descriptor --------------------------------------------------


def test_build_mcp_server_invokes_pinned_binary_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://paperless.example")
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/paperless-mcp" if cmd == "paperless-mcp" else None
    )

    server = agent_module.build_mcp_server("this-users-token")

    assert server.name == "paperless-ngx"
    assert server.command == "paperless-mcp"
    assert server.args == []
    assert server.env is not None
    assert server.env["PAPERLESS_API_TOKEN"] == "this-users-token"


def test_build_mcp_server_raises_clear_error_when_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda cmd: None)

    with pytest.raises(RuntimeError, match="paperless-mcp"):
        agent_module.build_mcp_server("token")


# --- response cleaning ------------------------------------------------------


def test_clean_agent_response_strips_labeled_file_links() -> None:
    text = "See [My Passport](file:///tmp/x.pdf) for details."
    assert agent_module._clean_agent_response(text) == "See My Passport for details."


def test_clean_agent_response_strips_bare_file_urls() -> None:
    text = "Saved to file:///tmp/report.pdf done"
    assert "file://" not in agent_module._clean_agent_response(text)


def test_clean_agent_response_leaves_plain_text_untouched() -> None:
    text = "John Doe Passport (15.03.1993)"
    assert agent_module._clean_agent_response(text) == text


# --- prompt contracts -------------------------------------------------------
# The system prompts are the most behavior-critical strings in the project;
# these lock in the invariants downstream code and #18 depend on.


def test_archive_prompt_uses_dynamic_tag_discovery() -> None:
    assert "list_tags" in agent_module.ARCHIVE_INSTRUCTIONS
    assert "never guess IDs and never create new tags" in agent_module.ARCHIVE_INSTRUCTIONS


def test_archive_prompt_forbids_markdown_and_links() -> None:
    assert "Do NOT use markdown links" in agent_module.ARCHIVE_INSTRUCTIONS
    assert "file://" in agent_module.ARCHIVE_INSTRUCTIONS


def test_search_prompt_requires_id_marker_format() -> None:
    assert "[#ID]" in agent_module.SEARCH_INSTRUCTIONS
    assert "same language the user writes in" in agent_module.SEARCH_INSTRUCTIONS


# --- run_agent loop ---------------------------------------------------------


class _FakeAgent:
    """Stand-in for antigravity's Agent that streams canned tokens."""

    tokens: tuple[str, ...] = ()

    def __init__(self, config: object) -> None:
        self.config = config

    async def __aenter__(self) -> _FakeAgent:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def chat(self, prompt: str) -> AsyncIterator[str]:
        async def stream() -> AsyncIterator[str]:
            for token in self.tokens:
                yield token

        return stream()


async def test_run_agent_accumulates_stream_and_cleans(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://paperless.example")
    monkeypatch.setattr(shutil, "which", lambda cmd: "/usr/bin/paperless-mcp")
    _FakeAgent.tokens = ("Found ", "[Passport](file:///tmp/x.pdf)", " for you")
    monkeypatch.setattr(agent_module, "Agent", _FakeAgent)

    result = await agent_module.run_agent("system", "find the passport", "user-token")

    # Tokens are concatenated and the internal file:// link is stripped to its label.
    assert result == "Found Passport for you"
