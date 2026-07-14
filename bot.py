import os
import asyncio
import logging
from telebot.async_telebot import AsyncTeleBot
from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig

# Настройка логирования
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Инициализация бота
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_IDS = [int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x]
WORKSPACE_PATH = os.environ.get("WORKSPACE_PATH", "/data/Latvia")

if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set!")

bot = AsyncTeleBot(BOT_TOKEN)

# Проверка прав доступа
def is_allowed(message):
    return message.from_user.id in ALLOWED_USER_IDS

@bot.message_handler(commands=['start', 'help'])
async def send_welcome(message):
    if not is_allowed(message):
        return
    await bot.reply_to(message, 
        "Привет! Отправь мне PDF-документ семейного архива (например, в папку 1993 года).\n"
        "Я запущу агента Antigravity, который автоматически проверит документ, "
        "загрузит его в Paperless, настроит метаданные по правилам проекта и переместит локально."
    )

@bot.message_handler(content_types=['document'])
async def handle_document(message):
    if not is_allowed(message):
        return

    # Проверяем, что это PDF
    file_name = message.document.file_name
    if not file_name.lower().endswith('.pdf'):
        await bot.reply_to(message, "❌ Пожалуйста, отправьте документ в формате PDF.")
        return

    status_message = await bot.reply_to(message, "📥 Получаю файл и запускаю агента Antigravity...")

    try:
        # 1. Скачиваем файл во временную директорию
        file_info = await bot.get_file(message.document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        
        # Определяем год из имени файла (например, "1993-01-18_MO.pdf" -> "1993")
        year = "unknown"
        if len(file_name) >= 4 and file_name[:4].isdigit():
            year = file_name[:4]
            
        target_dir = os.path.join(WORKSPACE_PATH, "documents", year)
        os.makedirs(target_dir, exist_ok=True)
        
        local_file_path = os.path.join(target_dir, file_name)
        with open(local_file_path, 'wb') as f:
            f.write(downloaded_file)
            
        logger.info(f"Файл сохранен локально: {local_file_path}")
        await bot.edit_message_text("🧠 Файл сохранен. Агент начинает анализ и обработку...", 
                                    chat_id=status_message.chat.id, 
                                    message_id=status_message.message_id)

        # 2. Формулируем задачу для агента Antigravity
        prompt = f"""
У нас есть новый документ в рабочем пространстве:
Путь: {local_file_path}

Пожалуйста, выполни следующие шаги строго по правилам архивации из .agents/AGENTS.md:
1. Проверь по базе Paperless-ngx (через MCP-инструменты), нет ли уже этого документа в системе.
2. Если он уже загружен, перемести локальный файл в соответствующую папку paperless/{year}/{file_name}.
3. Если документа нет:
   - Загрузи его в Paperless (post_document).
   - Дождись завершения OCR.
   - Установи корректные метаданные (Title, Created Date, Correspondent, Document Type).
   - Присвой теги согласно правилам (👥 Family, имя человека, 🏛️ History и т.д.) и удали мусорные теги (📥 Inbox).
   - Добавь к документу структурированную заметку с описанием на русском языке.
   - Перемести локальный файл в paperless/{year}/{file_name}.
4. Подготовь краткий markdown-отчет о выполненной работе для пользователя Telegram.
"""

        # 3. Конфигурируем и запускаем агента Antigravity
        agent_config = LocalAgentConfig(
            system_instructions="Ты — эксперт по архивации документов в Латвии. Всегда следуй правилам в .agents/AGENTS.md.",
            capabilities=CapabilitiesConfig(
                allow_file_write=True,
                allow_command_execution=True
            ),
            workspace_dir=WORKSPACE_PATH
        )

        async with Agent(agent_config) as agent:
            response = await agent.chat(prompt)
            agent_report = ""
            async for token in response:
                agent_report += token
                
        # 4. Отправляем отчет пользователю
        await bot.edit_message_text("✅ Обработка завершена!", 
                                    chat_id=status_message.chat.id, 
                                    message_id=status_message.message_id)
        
        if len(agent_report) > 4000:
            for i in range(0, len(agent_report), 4000):
                await bot.send_message(message.chat.id, agent_report[i:i+4000])
        else:
            await bot.send_message(message.chat.id, agent_report)

    except Exception as e:
        logger.exception("Ошибка при обработке документа")
        await bot.edit_message_text(f"❌ Произошла ошибка при обработке: {str(e)}", 
                                    chat_id=status_message.chat.id, 
                                    message_id=status_message.message_id)

async def main():
    logger.info("Запуск Telegram-бота...")
    await bot.polling(non_stop=True)

if __name__ == "__main__":
    asyncio.run(main())
