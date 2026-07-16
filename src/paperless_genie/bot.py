"""Telegram bot handlers and the Paperless-ngx archiving agent."""

import logging
import os
import re
from collections import defaultdict
from datetime import UTC, datetime

from telebot.async_telebot import AsyncTeleBot
from telebot.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from paperless_genie.agent import ARCHIVE_INSTRUCTIONS, SEARCH_INSTRUCTIONS, run_agent
from paperless_genie.config import Config
from paperless_genie.conversation import ConversationHistory
from paperless_genie.paperless import DuplicateDocumentError, PaperlessClient

logger = logging.getLogger(__name__)

# File extensions accepted for archiving (Paperless-ngx supports all of these)
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".jpg", ".jpeg", ".png", ".gif", ".tiff", ".tif", ".webp", ".bmp"}
)

# Telegram caps messages at 4096 characters; 4000 leaves margin for edits/ellipsis.
_TELEGRAM_MESSAGE_LIMIT = 4000

# Regex to find document ID tags that the agent embeds, e.g. [#42]
_DOC_TAG_RE = re.compile(r"\[#(\d+)\]")


def _extract_doc_ids(text: str) -> list[int]:
    """Returns unique document IDs from [#ID] markers, in order of first appearance.

    Args:
        text: Agent response text, possibly containing [#ID] markers.

    Returns:
        Deduplicated document IDs, ordered by where they first appear.
    """
    seen: set[int] = set()
    doc_ids: list[int] = []
    for m in _DOC_TAG_RE.finditer(text):
        doc_id = int(m.group(1))
        if doc_id not in seen:
            seen.add(doc_id)
            doc_ids.append(doc_id)
    return doc_ids


def _chunk_text(text: str, limit: int = _TELEGRAM_MESSAGE_LIMIT) -> list[str]:
    """Splits text into limit-sized chunks for Telegram delivery.

    Args:
        text: The text to split.
        limit: Maximum characters per chunk.

    Returns:
        At least one chunk; text at or under the limit (including empty text)
        comes back as a single chunk.
    """
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


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
    If the text exceeds the Telegram message limit it is split into chunks; buttons are
    attached only to the last chunk.

    Args:
        chat_id: The Telegram chat to send to.
        text: Agent response text, possibly containing [#ID] markers.
    """
    doc_ids = _extract_doc_ids(text)
    # Strip [#ID] markers from the visible text
    clean_text = _DOC_TAG_RE.sub("", text).strip()
    keyboard = _build_doc_keyboard(doc_ids)

    chunks = _chunk_text(clean_text)
    for chunk in chunks[:-1]:
        await bot.send_message(chat_id, chunk)
    # Attach buttons only to the last chunk
    await bot.send_message(chat_id, chunks[-1], reply_markup=keyboard)


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
        client = PaperlessClient(Config.PAPERLESS_URL, user_token)

        # 1. Get document metadata (title + filename)
        info = await client.fetch_document_info(doc_id)
        if info is None:
            await bot.edit_message_text(
                f"❌ Document #{doc_id} not found in the archive.",
                chat_id=status_message.chat.id,
                message_id=status_message.message_id,
            )
            return

        title = info.title or f"document_{doc_id}"
        original_name = info.original_file_name or f"{doc_id}.pdf"
        created_date = info.created_date or ""
        caption = f"📄 {title}"
        if created_date:
            caption += f"\n📅 {created_date}"

        # 2. Download the PDF bytes
        await bot.edit_message_text(
            f"⬇️ Downloading {title}...",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )
        pdf_bytes = await client.download_pdf(doc_id)

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
    """Uploads, polls for OCR, and archives a file using the AI agent.

    This helper is shared by the document and photo handlers so that the
    archiving workflow is defined in a single place.

    Args:
        file_bytes: Raw bytes of the file to archive.
        file_name: Original filename.
        user_token: Paperless-ngx API token for the requesting user.
        chat_id: Telegram chat to send status and report messages to.
        status_message_id: ID of the 'processing…' status message to edit.
    """
    client = PaperlessClient(Config.PAPERLESS_URL, user_token)

    async def _report(status: str) -> None:
        await bot.edit_message_text(status, chat_id=chat_id, message_id=status_message_id)

    try:
        # 1. Upload to Paperless-ngx and wait for OCR; progress goes to the
        # status message via the _report callback.
        doc_id = await client.upload_and_wait_for_ocr(
            file_bytes=file_bytes,
            file_name=file_name,
            on_status=_report,
        )

        await _report("🧠 Analyzing the document with AI...")

        prompt = (
            f"We have a new document to archive in Paperless-ngx.\n"
            f"Document ID: {doc_id}\n"
            f"Original Filename: {file_name}\n\n"
            f"Please retrieve this document using `get_document` with ID {doc_id}, "
            f"analyze its content, assign metadata and tags, write a structured note, "
            f"and output a final report."
        )
        agent_report = await run_agent(ARCHIVE_INSTRUCTIONS, prompt, user_token)

        await bot.edit_message_text(
            "✅ Processing completed!",
            chat_id=chat_id,
            message_id=status_message_id,
        )

        for chunk in _chunk_text(agent_report):
            await bot.send_message(chat_id, chunk)

    except DuplicateDocumentError as e:
        logger.info("Duplicate document detected for file %s: ID %d", file_name, e.doc_id)
        try:
            info = await client.fetch_document_info(e.doc_id)
            if info:
                title = info.title or "Untitled"
                created = info.created or info.created_date or ""

                msg = (
                    f"⚠️ This document already exists in the archive as #{e.doc_id}:\n\n📄 {title}"
                )
                if created:
                    msg += f"\n📅 {created}"

                keyboard = _build_doc_keyboard([e.doc_id])
                await bot.edit_message_text(
                    msg,
                    chat_id=chat_id,
                    message_id=status_message_id,
                    reply_markup=keyboard,
                )
                return
        except Exception:
            logger.exception("Error fetching details for duplicate document %d", e.doc_id)

        await bot.edit_message_text(
            f"⚠️ This document already exists in the archive as #{e.doc_id}.",
            chat_id=chat_id,
            message_id=status_message_id,
        )

    except Exception as e:
        logger.exception("Error processing document")
        await bot.edit_message_text(
            f"❌ An error occurred during processing: {e}",
            chat_id=chat_id,
            message_id=status_message_id,
        )


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

    # Narrow types: both fields are guaranteed non-None for real button presses
    if not call.data or not call.message or not hasattr(call.message, "chat"):
        await bot.answer_callback_query(call.id, "⚠️ Invalid callback data.")
        return

    chat_id = call.message.chat.id
    doc_id = int(call.data.split(":", 1)[1])
    await bot.answer_callback_query(call.id, f"⬇️ Fetching document #{doc_id}…")

    try:
        user_token = Config.get_token_for_user(call.from_user.id)
        client = PaperlessClient(Config.PAPERLESS_URL, user_token)

        info = await client.fetch_document_info(doc_id)
        if info is None:
            await bot.send_message(
                chat_id,
                f"❌ Document #{doc_id} not found in the archive.",
            )
            return

        title = info.title or f"document_{doc_id}"
        original_name = info.original_file_name or f"{doc_id}.pdf"
        created_date = info.created_date or ""
        caption = f"📄 {title}"
        if created_date:
            caption += f"\n📅 {created_date}"

        pdf_bytes = await client.download_pdf(doc_id)

        await bot.send_document(
            chat_id,
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
            chat_id,
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

        history = _user_histories[message.from_user.id]
        prompt = history.build_context(message.text)

        agent_report = await run_agent(SEARCH_INSTRUCTIONS, prompt, user_token)

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
