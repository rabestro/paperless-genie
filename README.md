# Telegram Archiver Bot for Paperless-ngx

Бот для автоматического импорта, распознавания (OCR) и каталогизации семейных документов в Paperless-ngx с использованием **Google Antigravity SDK** (`google-antigravity`).

## 🚀 Описание работы
1. Вы отправляете боту PDF-документ.
2. Бот сохраняет файл локально в структуру папок вашего Obsidian-архива (разбивая по годам на основе имени файла).
3. Бот запускает автономного агента Antigravity, передавая ему путь к новому файлу.
4. Агент руководствуется правилами из `.agents/AGENTS.md` (в вашем воркспейсе):
   - Ищет дубликаты в Paperless-ngx через MCP.
   - Загружает новые документы.
   - Корректно расставляет метаданные (Title, Created Date, Correspondent, Document Type).
   - Задает семейные теги и удаляет автоматический тег `📥 Inbox`.
   - Добавляет структурированную заметку с описанием.
   - Переносит локальный файл в директорию `paperless/`.
5. По завершении агент возвращает боту отчет, и бот пересылает его вам в Telegram.

## 🛠️ Установка и запуск на Linux-сервере

### 1. Требования
* Установленный Python 3.10+
* Установленный и запущенный Paperless-ngx с настроенным MCP-сервером.
* Установленная утилита `google-antigravity`.

### 2. Клонирование репозитория и установка зависимостей
```bash
git clone https://github.com/rabestro/latvia-archiver-bot.git
cd latvia-archiver-bot
pip install -r requirements.txt
```

### 3. Переменные окружения
Создайте файл `.env` в корневой папке проекта:
```ini
TELEGRAM_BOT_TOKEN="ваш_токен_телеграм_бота"
ALLOWED_USER_IDS="ваш_telegram_id"
WORKSPACE_PATH="/path/to/your/Obsidian/Latvia"
GEMINI_API_KEY="ваш_api_ключ_google_ai_pro"
```

### 4. Настройка автозапуска (systemd)
Создайте конфигурационный файл службы `/etc/systemd/system/latvia-bot.service`:
```ini
[Unit]
Description=Latvia Archiving Telegram Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/latvia-archiver-bot
EnvironmentFile=/path/to/latvia-archiver-bot/.env
ExecStart=/usr/bin/python3 bot.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Запустите и включите службу:
```bash
sudo systemctl daemon-reload
sudo systemctl start latvia-bot.service
sudo systemctl enable latvia-bot.service
```
