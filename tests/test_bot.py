import shutil

import pytest

from paperless_genie import bot as bot_module
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


def test_build_mcp_env_never_contains_bot_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:leaked-bot-token")
    monkeypatch.setenv("GEMINI_API_KEY", "leaked-gemini-key")
    monkeypatch.setenv("PAPERLESS_USER_TOKENS", '{"1": "leaked-other-users-token"}')
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "leaked-unrelated-secret")
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://paperless.example")

    env = bot_module._build_mcp_env("this-users-token")

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

    env = bot_module._build_mcp_env("token")

    assert env["PATH"] == "/usr/bin:/bin"
    assert env["HOME"] == "/home/genie"
    assert env["HTTPS_PROXY"] == "http://proxy.example:8080"
    assert env["NODE_EXTRA_CA_CERTS"] == "/etc/ssl/internal-ca.pem"


def test_build_mcp_env_omits_absent_plumbing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANG", raising=False)
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("TMPDIR", raising=False)
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://paperless.example")

    env = bot_module._build_mcp_env("token")

    assert "LANG" not in env
    assert "LC_ALL" not in env
    assert "TMPDIR" not in env


def test_build_mcp_server_invokes_pinned_binary_directly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Config, "PAPERLESS_URL", "http://paperless.example")
    monkeypatch.setattr(
        shutil, "which", lambda cmd: "/usr/bin/paperless-mcp" if cmd == "paperless-mcp" else None
    )

    server = bot_module._build_mcp_server("this-users-token")

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
        bot_module._build_mcp_server("token")


def test_clean_agent_response_strips_labeled_file_links() -> None:
    text = "See [My Passport](file:///tmp/x.pdf) for details."
    assert bot_module._clean_agent_response(text) == "See My Passport for details."


def test_clean_agent_response_strips_bare_file_urls() -> None:
    text = "Saved to file:///tmp/report.pdf done"
    # The bare URL is removed; surrounding text and spacing collapse to a strip().
    assert "file://" not in bot_module._clean_agent_response(text)


def test_clean_agent_response_leaves_plain_text_untouched() -> None:
    text = "John Doe Passport (15.03.1993)"
    assert bot_module._clean_agent_response(text) == text


def test_extract_doc_ids_deduplicates_preserving_order() -> None:
    text = "First [#42] then [#7] then [#42] again and [#7]."
    assert bot_module._extract_doc_ids(text) == [42, 7]


def test_extract_doc_ids_returns_empty_when_no_markers() -> None:
    assert bot_module._extract_doc_ids("no markers here") == []


def test_chunk_text_returns_single_chunk_at_or_under_limit() -> None:
    assert bot_module._chunk_text("", limit=10) == [""]
    assert bot_module._chunk_text("exactly10!", limit=10) == ["exactly10!"]


def test_chunk_text_splits_past_the_limit() -> None:
    assert bot_module._chunk_text("abcdefghijk", limit=10) == ["abcdefghij", "k"]
    assert bot_module._chunk_text("a" * 25, limit=10) == ["a" * 10, "a" * 10, "a" * 5]


def test_build_doc_keyboard_none_when_empty() -> None:
    assert bot_module._build_doc_keyboard([]) is None


def test_build_doc_keyboard_has_one_button_per_id() -> None:
    keyboard = bot_module._build_doc_keyboard([42, 7])
    assert keyboard is not None
    buttons = [button for row in keyboard.keyboard for button in row]
    assert [b.callback_data for b in buttons] == ["get_doc:42", "get_doc:7"]
