import logging
import os
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import ClassVar

import httpx
from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
from google.antigravity.types import McpStdioServer
from telebot.async_telebot import AsyncTeleBot
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from paperless_genie.config import Config

logger = logging.getLogger(__name__)

# File extensions accepted for archiving (Paperless-ngx supports all of these)
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".tiff", ".tif", ".webp", ".bmp"}
)

# Regex to strip markdown links containing file:// URLs, e.g. [Title](file:///path)
_FILE_LINK_RE = re.compile(r"\[([^\]]+)\]\(file://[^)]+\)")
# Regex to strip bare file:// URLs
_BARE_FILE_URL_RE = re.compile(r"file://\S+")
# Regex to find document ID tags that the agent embeds, e.g. [#42]
_DOC_TAG_RE = re.compile(r"\[#(\d+)\]")


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


def _build_doc_keyboard(
    doc_ids: list[int],
) -> InlineKeyboardMarkup | None:
    """Builds an InlineKeyboardMarkup with one download button per document.

    Buttons are arranged in rows of three.

    Args:
        doc_ids: Ordered list of unique Paperless document IDs found in the text.

    Returns:
        InlineKeyboardMarkup ready to attach to a message, or None if no IDs.
    """
    if not doc_ids:
        return None
    keyboard = InlineKeyboardMarkup(row_width=3)
    buttons = [
        InlineKeyboardButton(text=f"📥 #{doc_id}", callback_data=f"get_doc:{doc_id}")
        for doc_id in doc_ids
    ]
    keyboard.add(*buttons)
    return keyboard


async def _send_with_doc_buttons(
    chat_id: int,
    text: str,
) -> None:
    """Sends a text message and attaches download buttons for any [#ID] tags.

    The [#ID] markers are stripped from the visible text before sending.
    If the text exceeds 4000 characters it is split into chunks; buttons are
    attached only to the last chunk.

    Args:
        chat_id: The Telegram chat to send to.
        text: Agent response text, possibly containing [#ID] markers.
    """
    # Extract unique doc IDs preserving order of first appearance
    seen: set[int] = set()
    doc_ids: list[int] = []
    for m in _DOC_TAG_RE.finditer(text):
        doc_id = int(m.group(1))
        if doc_id not in seen:
            seen.add(doc_id)
            doc_ids.append(doc_id)

    # Strip [#ID] markers from the visible text
    clean_text = _DOC_TAG_RE.sub("", text).strip()

    keyboard = _build_doc_keyboard(doc_ids)

    if len(clean_text) > 4000:  # noqa: PLR2004
        chunks = [clean_text[i : i + 4000] for i in range(0, len(clean_text), 4000)]
        for chunk in chunks[:-1]:
            await bot.send_message(chat_id, chunk)
        # Attach buttons only to the last chunk
        await bot.send_message(chat_id, chunks[-1], reply_markup=keyboard)
    else:
        await bot.send_message(chat_id, clean_text, reply_markup=keyboard)


@dataclass
class ConversationHistory:
    """Stores the recent conversation turns for a single user.

    Each turn is a (user_message, bot_reply) pair. Older turns are dropped
    once *max_turns* is exceeded so token usage stays bounded.
    """

    MAX_TURNS: ClassVar[int] = 10

    turns: list[tuple[str, str]] = field(default_factory=list)

    def add(self, user_msg: str, bot_reply: str) -> None:
        """Appends a new turn and trims the oldest if needed."""
        self.turns.append((user_msg, bot_reply))
        if len(self.turns) > self.MAX_TURNS:
            self.turns.pop(0)

    def build_context(self, current_user_msg: str) -> str:
        """Returns a prompt string that includes history + the current message.

        Args:
            current_user_msg: The latest message from the user.

        Returns:
            Full prompt text with prior conversation context prepended.
        """
        if not self.turns:
            return f"User: {current_user_msg}"

        lines: list[str] = ["Below is the conversation history (oldest first):"]
        for user, bot in self.turns:
            lines.append(f"User: {user}")
            lines.append(f"Assistant: {bot}")
        lines.append("")
        lines.append(f"User: {current_user_msg}")
        lines.append(
            "Now answer the last User message, taking the conversation history into account."
        )
        return "\n".join(lines)

    def clear(self) -> None:
        """Resets the conversation history."""
        self.turns.clear()


# Per-user conversation history (lives as long as the bot process is running)
_user_histories: dict[int, ConversationHistory] = defaultdict(ConversationHistory)


# Initialize the Telegram Bot
bot = AsyncTeleBot(Config.TELEGRAM_BOT_TOKEN)


def is_allowed(message: Message) -> bool:
    """Checks if the sender of the message is authorized to use the bot.

    Args:
        message: The received Telegram message.

    Returns:
        True if the user is authorized, False otherwise.
    """
    return message.from_user is not None and message.from_user.id in Config.USER_TOKENS


@bot.message_handler(commands=["start", "help"])
async def send_welcome(message: Message) -> None:
    """Sends a welcome message explaining the bot capabilities.

    Args:
        message: The received Telegram message.
    """
    if not is_allowed(message):
        return
    await bot.reply_to(
        message,
        "🧞 Welcome! I am your AI assistant for Paperless-ngx.\n\n"
        "Features:\n"
        "1. Archive documents: Send me a PDF file, and I will check the "
        "database, upload it, set proper metadata, and add a detailed note.\n"
        "2. Search and Query: Ask me any questions about your documents "
        "(e.g., 'Find John Doe passport' or 'List all contracts from 1993').\n"
        "3. Download a document: /get <id> — sends the PDF from the archive.\n\n"
        "I remember our conversation — use /clear to start a new topic.",
    )


@bot.message_handler(commands=["clear"])
async def handle_clear(message: Message) -> None:
    """Clears the conversation history for the current user.

    Args:
        message: The received Telegram message.
    """
    if not is_allowed(message) or not message.from_user:
        return
    _user_histories[message.from_user.id].clear()
    await bot.reply_to(message, "🗑 Conversation history cleared. Starting fresh!")


async def _fetch_document_info(doc_id: int, api_token: str) -> dict[str, object] | None:
    """Fetches document metadata from the Paperless-ngx REST API.

    Args:
        doc_id: The Paperless document ID.
        api_token: The user's Paperless API token.

    Returns:
        Parsed JSON dict on success, or None if the document was not found.
    """
    url = f"{Config.PAPERLESS_URL.rstrip('/')}/api/documents/{doc_id}/"
    headers = {"Authorization": f"Token {api_token}"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        result: dict[str, object] = resp.json()
        return result


async def _download_document_pdf(doc_id: int, api_token: str) -> bytes:
    """Downloads the original PDF of a document from Paperless-ngx.

    Args:
        doc_id: The Paperless document ID.
        api_token: The user's Paperless API token.

    Returns:
        Raw PDF bytes.

    Raises:
        httpx.HTTPStatusError: If the download request fails.
    """
    url = f"{Config.PAPERLESS_URL.rstrip('/')}/api/documents/{doc_id}/download/"
    headers = {"Authorization": f"Token {api_token}"}
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        pdf_bytes: bytes = resp.content
        return pdf_bytes


@bot.message_handler(commands=["get"])
async def handle_get(message: Message) -> None:
    """Downloads a document by its Paperless ID and sends it as a PDF file.

    Usage: /get <document_id>

    Args:
        message: The received Telegram message.
    """
    if not is_allowed(message) or not message.from_user:
        return

    parts = (message.text or "").strip().split()
    if len(parts) != 2 or not parts[1].isdigit():  # noqa: PLR2004
        await bot.reply_to(
            message,
            "⚠️ Usage: /get <document_id>\nExample: /get 42",
        )
        return

    doc_id = int(parts[1])
    status_message = await bot.reply_to(message, f"📄 Fetching document #{doc_id}...")

    try:
        user_token = Config.get_token_for_user(message.from_user.id)

        # 1. Get document metadata (title + filename)
        info = await _fetch_document_info(doc_id, user_token)
        if info is None:
            await bot.edit_message_text(
                f"❌ Document #{doc_id} not found in the archive.",
                chat_id=status_message.chat.id,
                message_id=status_message.message_id,
            )
            return

        title = str(info.get("title") or f"document_{doc_id}")
        original_name = str(info.get("original_file_name") or f"{doc_id}.pdf")
        created_date = str(info.get("created_date") or "")
        caption = f"📄 {title}"
        if created_date:
            caption += f"\n📅 {created_date}"

        # 2. Download the PDF bytes
        await bot.edit_message_text(
            f"⬇️ Downloading {title}...",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )
        pdf_bytes = await _download_document_pdf(doc_id, user_token)

        # 3. Send the PDF to the chat
        await bot.delete_message(
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )
        await bot.send_document(
            message.chat.id,
            document=(original_name, pdf_bytes),
            caption=caption,
        )
        logger.info(
            "Sent document #%d (%s) to user %d", doc_id, original_name, message.from_user.id
        )

    except KeyError:
        await bot.edit_message_text(
            "❌ You are not authorized to use this bot.",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )
    except Exception as e:
        logger.exception("Error fetching document #%d", doc_id)
        await bot.edit_message_text(
            f"❌ Failed to fetch document #{doc_id}: {e}",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )


async def _archive_file(
    *,
    file_bytes: bytes,
    file_name: str,
    user_token: str,
    chat_id: int,
    status_message_id: int,
) -> None:
    """Downloads, saves, and archives a file using the AI agent.

    This helper is shared by the document and photo handlers so that the
    archiving workflow is defined in a single place.

    Args:
        file_bytes: Raw bytes of the file to archive.
        file_name: Original filename (used to save the temp file).
        user_token: Paperless-ngx API token for the requesting user.
        chat_id: Telegram chat to send status and report messages to.
        status_message_id: ID of the 'processing…' status message to edit.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        local_file_path = os.path.join(temp_dir, file_name)
        with open(local_file_path, "wb") as fh:
            fh.write(file_bytes)

        logger.info("Saved temporary file to %s", local_file_path)
        await bot.edit_message_text(
            "🧠 Analyzing the document with AI…",
            chat_id=chat_id,
            message_id=status_message_id,
        )

        mcp_env = {
            "PAPERLESS_URL": Config.PAPERLESS_URL,
            "PAPERLESS_API_TOKEN": user_token,
            "PAPERLESS_API_KEY": user_token,
        }
        for k, v in os.environ.items():
            if k not in mcp_env:
                mcp_env[k] = v

        mcp_server = McpStdioServer(
            name="paperless-ngx",
            command="npx",
            args=["-y", "@baruchiro/paperless-mcp"],
            env=mcp_env,
        )

        system_instructions = (
            "You are an expert archiving assistant for the family archive in Paperless-ngx. "
            "Always adhere to these rules when archiving documents:\n"
            "1. Search the database to check if a document already exists "
            "(by content or metadata).\n"
            "2. If it exists, notify the user and stop.\n"
            "3. If it does not exist, upload it using post_document.\n"
            "4. Wait for OCR to complete, then update its metadata "
            "(Title, Created Date, Correspondent, Document Type).\n"
            "5. Assign tags: '👥 Family' (ID 11) for family documents, "
            "'Jane' (ID 12) for Jane Doe, "
            "'🏛️ History' (ID 5) for historical documents, "
            "'🎓 Education' (ID 18) for certificates/diplomas.\n"
            "6. Remove any auto-assigned tags like '📥 Inbox' (ID 3).\n"
            "7. Add a structured note describing the document, owner, and key details.\n"
            "8. Output a final report describing what actions were done.\n"
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

        agent_config = LocalAgentConfig(
            system_instructions=system_instructions,
            mcp_servers=[mcp_server],
            capabilities=CapabilitiesConfig(allow_file_write=True, allow_command_execution=True),
            save_dir=temp_dir,
            model=Config.GEMINI_MODEL,
        )

        prompt = (
            f"We have a new document to archive:\n"
            f"Path: {local_file_path}\n"
            f"Original Filename: {file_name}\n\n"
            f"Please analyze, upload and categorize this document according to the guidelines."
        )

        async with Agent(agent_config) as agent:
            response = await agent.chat(prompt)
            agent_report = ""
            async for token in response:
                agent_report += token

        agent_report = _clean_agent_response(agent_report)

        await bot.edit_message_text(
            "✅ Processing completed!",
            chat_id=chat_id,
            message_id=status_message_id,
        )

        if len(agent_report) > 4000:  # noqa: PLR2004
            for i in range(0, len(agent_report), 4000):
                await bot.send_message(chat_id, agent_report[i : i + 4000])
        else:
            await bot.send_message(chat_id, agent_report)


@bot.message_handler(content_types=["document"])
async def handle_document(message: Message) -> None:
    """Processes document uploads (PDF, JPG, PNG, etc.) and archives them.

    Args:
        message: The received Telegram message.
    """
    if not is_allowed(message):
        return

    if not message.document or not message.from_user:
        return

    file_name = message.document.file_name or ""
    ext = os.path.splitext(file_name)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        await bot.reply_to(
            message,
            f"❌ Unsupported file type '{ext}'.\n"
            f"Accepted formats: PDF, JPG, PNG, GIF, TIFF, WEBP, BMP.",
        )
        return

    status_message = await bot.reply_to(
        message, "📥 Downloading document and initializing agent..."
    )
    try:
        user_token = Config.get_token_for_user(message.from_user.id)
        file_info = await bot.get_file(message.document.file_id)
        file_bytes = await bot.download_file(file_info.file_path)
        await _archive_file(
            file_bytes=file_bytes,
            file_name=file_name,
            user_token=user_token,
            chat_id=message.chat.id,
            status_message_id=status_message.message_id,
        )
    except Exception as e:
        logger.exception("Error processing document upload")
        await bot.edit_message_text(
            f"❌ An error occurred during processing: {e}",
            chat_id=message.chat.id,
            message_id=status_message.message_id,
        )


@bot.message_handler(content_types=["photo"])
async def handle_photo(message: Message) -> None:
    """Processes photos sent directly to the chat (Telegram compresses them as JPEG).

    Telegram compresses direct photo messages to JPEG. The highest-resolution
    version is downloaded and forwarded to the archiving agent.

    Args:
        message: The received Telegram message.
    """
    if not is_allowed(message):
        return

    if not message.photo or not message.from_user:
        return

    status_message = await bot.reply_to(message, "📥 Downloading photo and initializing agent...")
    try:
        user_token = Config.get_token_for_user(message.from_user.id)
        # Take the highest-resolution version (last in the list)
        best = message.photo[-1]
        file_info = await bot.get_file(best.file_id)
        file_bytes = await bot.download_file(file_info.file_path)
        # Build a sensible filename from the caption or timestamp
        caption_slug = (
            message.caption.strip().replace(" ", "_")[:40]
            if message.caption
            else datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")
        )
        file_name = f"{caption_slug}.jpg"
        await _archive_file(
            file_bytes=file_bytes,
            file_name=file_name,
            user_token=user_token,
            chat_id=message.chat.id,
            status_message_id=status_message.message_id,
        )
    except Exception as e:
        logger.exception("Error processing photo upload")
        await bot.edit_message_text(
            f"❌ An error occurred during processing: {e}",
            chat_id=message.chat.id,
            message_id=status_message.message_id,
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith("get_doc:"))
async def handle_doc_button(call: CallbackQuery) -> None:
    """Handles inline button presses that request a document download.

    The callback_data format is ``get_doc:<document_id>``.

    Args:
        call: The incoming callback query from Telegram.
    """
    if not call.from_user or call.from_user.id not in Config.USER_TOKENS:
        await bot.answer_callback_query(call.id, "⛔ Not authorized.")
        return

    doc_id = int(call.data.split(":", 1)[1])
    await bot.answer_callback_query(call.id, f"⬇️ Fetching document #{doc_id}…")

    try:
        user_token = Config.get_token_for_user(call.from_user.id)

        info = await _fetch_document_info(doc_id, user_token)
        if info is None:
            await bot.send_message(
                call.message.chat.id,
                f"❌ Document #{doc_id} not found in the archive.",
            )
            return

        title = str(info.get("title") or f"document_{doc_id}")
        original_name = str(info.get("original_file_name") or f"{doc_id}.pdf")
        created_date = str(info.get("created_date") or "")
        caption = f"📄 {title}"
        if created_date:
            caption += f"\n📅 {created_date}"

        pdf_bytes = await _download_document_pdf(doc_id, user_token)

        await bot.send_document(
            call.message.chat.id,
            document=(original_name, pdf_bytes),
            caption=caption,
        )
        logger.info(
            "Sent document #%d (%s) via inline button to user %d",
            doc_id,
            original_name,
            call.from_user.id,
        )

    except Exception as e:
        logger.exception("Error fetching document #%d via inline button", doc_id)
        await bot.send_message(
            call.message.chat.id,
            f"❌ Failed to fetch document #{doc_id}: {e}",
        )


@bot.message_handler(content_types=["text"])
async def handle_text_query(message: Message) -> None:
    """Processes search and informational text queries using the AI agent.

    Args:
        message: The received Telegram message.
    """
    if not is_allowed(message):
        return

    if not message.text or message.text.startswith("/") or not message.from_user:
        return

    status_message = await bot.reply_to(message, "🧠 Querying document archive...")

    try:
        user_token = Config.get_token_for_user(message.from_user.id)

        mcp_env = {
            "PAPERLESS_URL": Config.PAPERLESS_URL,
            "PAPERLESS_API_TOKEN": user_token,
            "PAPERLESS_API_KEY": user_token,
        }
        for k, v in os.environ.items():
            if k not in mcp_env:
                mcp_env[k] = v

        mcp_server = McpStdioServer(
            name="paperless-ngx",
            command="npx",
            args=["-y", "@baruchiro/paperless-mcp"],
            env=mcp_env,
        )

        system_instructions = (
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

        with tempfile.TemporaryDirectory() as temp_dir:
            agent_config = LocalAgentConfig(
                system_instructions=system_instructions,
                mcp_servers=[mcp_server],
                capabilities=CapabilitiesConfig(
                    allow_file_write=False, allow_command_execution=False
                ),
                save_dir=temp_dir,
                model=Config.GEMINI_MODEL,
            )

            history = _user_histories[message.from_user.id]
            prompt = history.build_context(message.text)

            async with Agent(agent_config) as agent:
                response = await agent.chat(prompt)
                agent_report = ""
                async for token in response:
                    agent_report += token

            agent_report = _clean_agent_response(agent_report)

            # Persist the turn so the next message can reference it
            history.add(message.text, agent_report)

            await bot.delete_message(
                chat_id=status_message.chat.id, message_id=status_message.message_id
            )

            await _send_with_doc_buttons(message.chat.id, agent_report)

    except Exception as e:
        logger.exception("Error processing text query")
        await bot.edit_message_text(
            f"❌ An error occurred during search: {e}",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )
