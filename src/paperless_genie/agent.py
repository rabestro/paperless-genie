"""AI agent wiring: system prompts, MCP server setup, and the shared run loop.

This module isolates everything about driving the Google Antigravity agent
against the Paperless-ngx MCP tools, so the bot handlers only need to pick a
prompt and call run_agent().
"""

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
from google.antigravity.types import McpStdioServer

from paperless_genie.config import Config

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"

# Regex to strip markdown links containing file:// URLs, e.g. [Title](file:///path)
_FILE_LINK_RE = re.compile(r"\[([^\]]+)\]\(file://[^)]+\)")
# Regex to strip bare file:// URLs
_BARE_FILE_URL_RE = re.compile(r"file://\S+")

# Process plumbing forwarded to the MCP subprocess in addition to the
# user-scoped Paperless credentials. Deliberately excludes bot-level secrets
# (TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, PAPERLESS_USER_TOKENS) so the child
# process never sees the Telegram bot token, the Gemini key, or other users'
# Paperless tokens.
_MCP_ENV_PASSTHROUGH: tuple[str, ...] = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    # Proxy/TLS plumbing so the subprocess can reach Paperless-ngx (and, today,
    # the npm registry for `npx`) from behind a proxy or with a self-signed /
    # internal CA certificate — common in self-hosted Paperless-ngx setups.
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "no_proxy",
    "NODE_EXTRA_CA_CERTS",
)

_MCP_BINARY = "paperless-mcp"


def _load_prompt(custom_path: str, default_filename: str) -> str:
    """Loads system instructions from a custom path if set, otherwise from package defaults.

    Args:
        custom_path: Optional file path to override the prompt instructions.
        default_filename: Name of the default markdown file in the prompts directory.

    Returns:
        The instructions text content.
    """
    if custom_path:
        path = Path(custom_path)
        try:
            if path.is_file():
                return path.read_text(encoding="utf-8").strip()
            logger.warning(
                "Custom prompt path '%s' is not a file. Falling back to default '%s'.",
                custom_path,
                default_filename,
            )
        except (OSError, UnicodeError) as err:
            logger.warning(
                "Could not load custom prompt file '%s': %s. Falling back to default '%s'.",
                custom_path,
                err,
                default_filename,
            )

    default_path = PROMPTS_DIR / default_filename
    return default_path.read_text(encoding="utf-8").strip()


def get_archive_instructions() -> str:
    """Returns system instructions for the archiving agent."""
    return _load_prompt(Config.PROMPT_ARCHIVE_PATH, "archive_instructions.md")


def get_search_instructions() -> str:
    """Returns system instructions for the search/query agent."""
    return _load_prompt(Config.PROMPT_SEARCH_PATH, "search_instructions.md")


def _clean_agent_response(text: str) -> str:
    """Removes internal file:// links from the agent response.

    The Antigravity agent sometimes appends file:// URLs that point to
    temporary internal files. These links are meaningless in Telegram and
    are stripped out here, keeping only the link label text.

    Args:
        text: The raw agent response text.

    Returns:
        Cleaned text suitable for sending to Telegram.
    """
    # Replace [Label](file://...) → Label
    text = _FILE_LINK_RE.sub(r"\1", text)
    # Remove any remaining bare file:// URLs
    text = _BARE_FILE_URL_RE.sub("", text)
    return text.strip()


def _build_mcp_env(user_token: str) -> dict[str, str]:
    """Builds the environment for the Paperless MCP subprocess.

    Only an explicit allowlist of process plumbing is forwarded from the
    bot's own environment; everything else — including secrets unrelated to
    this request — is left out.

    Args:
        user_token: Paperless-ngx API token of the requesting user.

    Returns:
        Environment mapping to pass to the MCP subprocess.
    """
    env: dict[str, str] = {}
    for key in _MCP_ENV_PASSTHROUGH:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    env["PAPERLESS_URL"] = Config.PAPERLESS_URL
    env["PAPERLESS_API_TOKEN"] = user_token
    env["PAPERLESS_API_KEY"] = user_token
    if Config.PAPERLESS_API_VERSION:
        env["PAPERLESS_API_VERSION"] = Config.PAPERLESS_API_VERSION
    return env


def build_mcp_server(user_token: str) -> McpStdioServer:
    """Builds the stdio MCP server descriptor for the Paperless-ngx MCP tools.

    Invokes the `paperless-mcp` binary directly rather than through `npx`.
    The image pre-installs an exact pinned version of the package (see the
    Dockerfile's PAPERLESS_MCP_VERSION build arg) so this never resolves a
    package over the network at request time — `npx <pkg>@<version>` cannot
    guarantee that: once any same-named binary is already on PATH, npx runs
    it without checking whether it actually matches the requested version.

    Args:
        user_token: Paperless-ngx API token of the requesting user.

    Returns:
        Configured McpStdioServer ready to pass to LocalAgentConfig.

    Raises:
        RuntimeError: If the `paperless-mcp` binary isn't on PATH — expected
            in local development when the pinned package hasn't been
            installed yet (see README.md's local setup section).
    """
    if shutil.which(_MCP_BINARY) is None:
        raise RuntimeError(
            f"'{_MCP_BINARY}' was not found on PATH. Install Node.js 24+ and run "
            f"'npm install -g @baruchiro/paperless-mcp@<version>' — see README.md's "
            f"local setup section for the exact pinned version."
        )

    return McpStdioServer(
        name="paperless-ngx",
        command=_MCP_BINARY,
        args=[],
        env=_build_mcp_env(user_token),
    )


async def run_agent(instructions: str, prompt: str, user_token: str) -> str:
    """Runs the Antigravity agent against the Paperless MCP tools.

    Wires up the MCP server, runs the agent to completion accumulating its
    streamed reply, and cleans internal links out of the result.

    Args:
        instructions: The system prompt (ARCHIVE_INSTRUCTIONS or
            SEARCH_INSTRUCTIONS).
        prompt: The user-facing task/query prompt.
        user_token: Paperless-ngx API token of the requesting user.

    Returns:
        The agent's cleaned, Telegram-ready response text.

    Raises:
        RuntimeError: If the MCP binary isn't available (see build_mcp_server).
    """
    mcp_server = build_mcp_server(user_token)

    with tempfile.TemporaryDirectory() as temp_dir:
        agent_config = LocalAgentConfig(
            system_instructions=instructions,
            mcp_servers=[mcp_server],
            capabilities=CapabilitiesConfig(allow_file_write=False, allow_command_execution=False),
            save_dir=temp_dir,
            model=Config.GEMINI_MODEL,
        )

        async with Agent(agent_config) as agent:
            response = await agent.chat(prompt)
            report = ""
            async for token in response:
                report += token

    return _clean_agent_response(report)
