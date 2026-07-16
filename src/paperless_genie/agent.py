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

from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
from google.antigravity.types import McpStdioServer

from paperless_genie.config import Config

logger = logging.getLogger(__name__)

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

# System prompt for the archiving agent (document upload → metadata + note).
ARCHIVE_INSTRUCTIONS = (
    "You are an expert archiving assistant for the personal archive in Paperless-ngx. "
    "You are processing a document that has already been successfully uploaded. "
    "Its ID is provided in the prompt.\n"
    "Adhere to these rules when updating this document:\n"
    "1. Call `get_document` with the given ID to fetch its text content and properties.\n"
    "2. Based on the document's text, determine the correct metadata "
    "(Title, Created Date, Correspondent, Document Type).\n"
    "3. Call `update_document` to update the document's Title, "
    "Created (in YYYY-MM-DD), Correspondent, and Document Type.\n"
    "4. Call `list_tags` to see every tag that exists in this archive "
    "(their names and IDs). Decide which existing tags match the document's "
    "content, judging by tag names.\n"
    "5. Update the document's tags via `update_document`, passing the complete "
    "final list of tag IDs: the current tags worth keeping, plus the matching "
    "tags from step 4, excluding any auto-assigned inbox tag (a tag whose name "
    "contains 'inbox', case-insensitive). Use only tag IDs returned by "
    "`list_tags` — never guess IDs and never create new tags. If no existing "
    "tag matches, keep the current tags (minus the inbox tag).\n"
    "6. Call `create_document_note` to add a structured note "
    "describing the document, owner, key details, and historical context.\n"
    "7. Output a final report describing what actions were done.\n"
    "IMPORTANT LANGUAGE RULE:\n"
    "- Detect the language of the document's content and write the note "
    "and report in that same language.\n"
    "IMPORTANT FORMATTING RULES:\n"
    "- The response will be sent as a Telegram message. "
    "Do NOT use markdown links with URLs. "
    "Do NOT include any file:// or http:// links in the response.\n"
    "- Refer to documents only by their title and date, for example: "
    "'John Doe Passport (15.03.1993)'.\n"
    "- Use plain text and emoji for formatting. "
    "Avoid Markdown syntax like **bold** or [text](url)."
)

# System prompt for the search/query agent (natural-language archive queries).
SEARCH_INSTRUCTIONS = (
    "You are a helpful assistant for a personal document archive in Paperless-ngx. "
    "Use the Paperless-ngx MCP tools to search and retrieve documents to answer "
    "user queries. Always base your replies on the retrieved documents.\n"
    "IMPORTANT LANGUAGE RULE:\n"
    "- Always respond in the same language the user writes in. "
    "If the user writes in English, reply in English. "
    "If the user writes in Latvian, reply in Latvian. "
    "Auto-detect and match the user's language precisely.\n"
    "IMPORTANT FORMATTING RULES:\n"
    "- The response will be sent as a Telegram message. "
    "Do NOT use markdown links with URLs. "
    "Do NOT include any file:// or http:// links in the response.\n"
    "- After every document title or description, append its Paperless ID "
    "in the format [#ID], for example: "
    "'John Doe Passport (15.03.1993) [#42]'. "
    "This tag is used by the bot to build download buttons automatically.\n"
    "- Use plain text, numbered lists, and emoji. "
    "Avoid Markdown syntax like **bold** or [text](url)."
)


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
