import logging
import os
import tempfile

from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
from google.antigravity.types import McpStdioServer
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message

from paperless_genie.config import Config

logger = logging.getLogger(__name__)

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
        "**Features:**\n"
        "1. **Archive documents:** Send me a PDF file, and I will check the database, "
        "upload it, set proper metadata (title, correspondent, tags, type), and "
        "add a detailed note.\n"
        "2. **Search and Query:** Ask me any questions about your documents "
        "(e.g., 'Find John Doe's passport' or 'List all contracts from 1993').\n\n"
        "All actions are executed using your personal credentials and permissions.",
        parse_mode="Markdown",
    )


@bot.message_handler(content_types=["document"])
async def handle_document(message: Message) -> None:
    """Processes document uploads by downloading them, running the AI agent,
    and posting to Paperless.

    Args:
        message: The received Telegram message.
    """
    if not is_allowed(message):
        return

    if not message.document or not message.from_user:
        return

    file_name = message.document.file_name
    if not file_name or not file_name.lower().endswith(".pdf"):
        await bot.reply_to(message, "❌ Only PDF files are supported.")
        return

    status_message = await bot.reply_to(
        message, "📥 Downloading document and initializing agent..."
    )

    try:
        # Get the user-specific Paperless API token
        user_token = Config.get_token_for_user(message.from_user.id)

        # Download the document to a temporary directory
        file_info = await bot.get_file(message.document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)

        with tempfile.TemporaryDirectory() as temp_dir:
            local_file_path = os.path.join(temp_dir, file_name)
            with open(local_file_path, "wb") as f:
                f.write(downloaded_file)

            logger.info("Saved temporary file to %s", local_file_path)
            await bot.edit_message_text(
                "🧠 Analyzing the document with AI...",
                chat_id=status_message.chat.id,
                message_id=status_message.message_id,
            )

            # Build environment variables for the MCP server
            mcp_env = {
                "PAPERLESS_URL": Config.PAPERLESS_URL,
                "PAPERLESS_API_TOKEN": user_token,
                "PAPERLESS_API_KEY": user_token,
            }
            # Inherit host env to ensure Node/npm/etc. can be found
            for k, v in os.environ.items():
                if k not in mcp_env:
                    mcp_env[k] = v

            # Configure dynamic MCP server
            mcp_server = McpStdioServer(
                name="paperless-ngx",
                command="npx",
                args=["-y", "@baruchiro/paperless-mcp"],
                env=mcp_env,
            )

            # Archiving instructions for the agent
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
                "7. Add a structured Russian note describing the document, "
                "owner, and key details.\n"
                "8. Output a final report in Russian describing what actions were done."
            )

            agent_config = LocalAgentConfig(
                system_instructions=system_instructions,
                mcp_servers=[mcp_server],
                capabilities=CapabilitiesConfig(
                    allow_file_write=True, allow_command_execution=True
                ),
                save_dir=temp_dir,
            )

            # Formulate the prompt for the agent
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

            await bot.edit_message_text(
                "✅ Processing completed!",
                chat_id=status_message.chat.id,
                message_id=status_message.message_id,
            )

            if len(agent_report) > 4000:
                for i in range(0, len(agent_report), 4000):
                    await bot.send_message(message.chat.id, agent_report[i : i + 4000])
            else:
                await bot.send_message(message.chat.id, agent_report)

    except Exception as e:
        logger.exception("Error processing document")
        await bot.edit_message_text(
            f"❌ An error occurred during processing: {e}",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
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
            "You are a helpful assistant for a family document archive in Paperless-ngx. "
            "Use the Paperless-ngx MCP tools to search and retrieve documents to answer "
            "user queries. Provide accurate answers in Russian. Always base your replies "
            "on the retrieved documents."
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            agent_config = LocalAgentConfig(
                system_instructions=system_instructions,
                mcp_servers=[mcp_server],
                capabilities=CapabilitiesConfig(
                    allow_file_write=False, allow_command_execution=False
                ),
                save_dir=temp_dir,
            )

            prompt = (
                f"The user asks: '{message.text}'\nSearch the archive and reply to their question."
            )

            async with Agent(agent_config) as agent:
                response = await agent.chat(prompt)
                agent_report = ""
                async for token in response:
                    agent_report += token

            await bot.delete_message(
                chat_id=status_message.chat.id, message_id=status_message.message_id
            )

            if len(agent_report) > 4000:
                for i in range(0, len(agent_report), 4000):
                    await bot.send_message(message.chat.id, agent_report[i : i + 4000])
            else:
                await bot.send_message(message.chat.id, agent_report)

    except Exception as e:
        logger.exception("Error processing text query")
        await bot.edit_message_text(
            f"❌ An error occurred during search: {e}",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )
