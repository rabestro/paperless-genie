import logging
import os

from google.antigravity import Agent, CapabilitiesConfig, LocalAgentConfig
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message

from paperless_genie.config import Config

logger = logging.getLogger(__name__)

# Инициализируем бота
bot = AsyncTeleBot(Config.TELEGRAM_BOT_TOKEN)


def is_allowed(message: Message) -> bool:
    return message.from_user is not None and message.from_user.id in Config.ALLOWED_USER_IDS


@bot.message_handler(commands=["start", "help"])
async def send_welcome(message: Message) -> None:
    if not is_allowed(message):
        return
    await bot.reply_to(
        message,
        "🧠 Привет! Я ваш персональный помощник по архиву документов Paperless-ngx.\n\n"
        "**Что я умею:**\n"
        "1. **Обработка документов:** Отправьте мне PDF-файл, и я автоматически "
        "проверю его по базе, загружу в Paperless, настрою метаданные и сохраню на диске.\n"
        "2. **Поиск и вопросы:** Вы можете спросить меня о любых архивных документах "
        "(например: 'Найди паспорт Свирского' или 'Какие договоры за 1993 год у нас есть?').\n\n"
        "Отправьте мне файл или задайте вопрос!",
        parse_mode="Markdown",
    )


@bot.message_handler(content_types=["document"])
async def handle_document(message: Message) -> None:
    if not is_allowed(message):
        return

    if not message.document:
        return

    file_name = message.document.file_name
    if not file_name or not file_name.lower().endswith(".pdf"):
        await bot.reply_to(message, "❌ Пожалуйста, отправьте документ в формате PDF.")
        return

    status_message = await bot.reply_to(
        message, "📥 Получаю файл и запускаю агента Antigravity..."
    )

    try:
        # Скачиваем файл во временную директорию
        file_info = await bot.get_file(message.document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)

        # Выделяем год из имени файла (например, "1993-01-18_MO.pdf" -> "1993")
        year = "unknown"
        if len(file_name) >= 4 and file_name[:4].isdigit():
            year = file_name[:4]

        target_dir = os.path.join(Config.WORKSPACE_PATH, "documents", year)
        os.makedirs(target_dir, exist_ok=True)

        local_file_path = os.path.join(target_dir, file_name)
        with open(local_file_path, "wb") as f:
            f.write(downloaded_file)

        logger.info(f"Файл сохранен локально: {local_file_path}")
        await bot.edit_message_text(
            "🧠 Файл сохранен. Агент начинает анализ и обработку...",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )

        # Формулируем задачу для агента
        prompt = f"""
У нас есть новый документ в рабочем пространстве:
Путь: {local_file_path}

Пожалуйста, выполни следующие шаги строго по правилам архивации из .agents/AGENTS.md:
1. Проверь по базе Paperless-ngx (через MCP-инструменты), нет ли уже этого документа.
2. Если он уже загружен, перемести локальный файл в соответствующую папку
   paperless/{year}/{file_name}.
3. Если документа нет:
   - Загрузи его в Paperless (post_document).
   - Дождись завершения OCR.
   - Установи корректные метаданные (Title, Created Date, Correspondent, Document Type).
   - Присвой теги по правилам (👥 Family, имя человека, 🏛️ History и т.д.)
     и удали мусорные теги (📥 Inbox).
   - Добавь к документу структурированную заметку с описанием на русском языке.
   - Перемести локальный файл в paperless/{year}/{file_name}.
4. Подготовь краткий markdown-отчет о выполненной работе для пользователя Telegram.
"""

        agent_config = LocalAgentConfig(
            system_instructions=(
                "Ты — эксперт по архивации документов в Латвии. "
                "Всегда следуй правилам в .agents/AGENTS.md."
            ),
            capabilities=CapabilitiesConfig(allow_file_write=True, allow_command_execution=True),
            workspace_dir=Config.WORKSPACE_PATH,
        )

        async with Agent(agent_config) as agent:
            response = await agent.chat(prompt)
            agent_report = ""
            async for token in response:
                agent_report += token

        await bot.edit_message_text(
            "✅ Обработка завершена!",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )

        if len(agent_report) > 4000:
            for i in range(0, len(agent_report), 4000):
                await bot.send_message(message.chat.id, agent_report[i : i + 4000])
        else:
            await bot.send_message(message.chat.id, agent_report)

    except Exception as e:
        logger.exception("Ошибка при обработке документа")
        await bot.edit_message_text(
            f"❌ Произошла ошибка при обработке: {str(e)}",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )


@bot.message_handler(content_types=["text"])
async def handle_text_query(message: Message) -> None:
    if not is_allowed(message):
        return

    if not message.text or message.text.startswith("/"):
        return

    status_message = await bot.reply_to(message, "🧠 Запускаю поиск и анализ документов...")

    try:
        # Формулируем запрос для агента
        prompt = f"""
Пользователь спрашивает: "{message.text}"

Используй MCP-инструменты Paperless-ngx для поиска информации в системе.
Ответь на вопрос пользователя на русском языке.
Будь точен и опирайся на найденные документы и метаданные.
Если пользователь просит найти конкретный документ, найди его и пришли подробности.
"""

        agent_config = LocalAgentConfig(
            system_instructions=(
                "Ты — помощник по архиву документов в Латвии. "
                "Используй Paperless MCP-инструменты для ответов на вопросы пользователя."
            ),
            capabilities=CapabilitiesConfig(allow_file_write=False, allow_command_execution=False),
            workspace_dir=Config.WORKSPACE_PATH,
        )

        async with Agent(agent_config) as agent:
            response = await agent.chat(prompt)
            agent_report = ""
            async for token in response:
                agent_report += token

        await bot.delete_message(
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )

        if len(agent_report) > 4000:
            for i in range(0, len(agent_report), 4000):
                await bot.send_message(message.chat.id, agent_report[i : i + 4000])
        else:
            await bot.send_message(message.chat.id, agent_report)

    except Exception as e:
        logger.exception("Ошибка при обработке текстового запроса")
        await bot.edit_message_text(
            f"❌ Произошла ошибка при поиске: {str(e)}",
            chat_id=status_message.chat.id,
            message_id=status_message.message_id,
        )
