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
