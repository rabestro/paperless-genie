# Deployment Guide

`paperless-genie` can be deployed in production using **Docker Compose** or as a **systemd service** on a Linux server.

---

## 🐳 Option 1: Docker Compose (Recommended)

Running the bot inside Docker is the easiest method. The Docker image automatically installs Node.js, ensuring that Node-based MCP servers (like Paperless-ngx) work out of the box.

### 1. Build and Start Container

Ensure your `.env` file is configured in the root directory:

```bash
docker compose up -d --build
```

### 2. Check Logs

```bash
docker compose logs -f
```

---

## 📋 Option 2: systemd Service (Bare Metal)

If you prefer to run the bot directly on your host machine, you can register it as a systemd service.

### 1. Prepare Environment

Install project dependencies using `uv` and `mise`:

```bash
# Install tools
mise install

# Sync runtime dependencies (dev tooling is not needed on a server)
uv sync --no-dev
```

### 2. Create Service File

Create the systemd configuration file at `/etc/systemd/system/paperless-genie.service` (replace `your-username` and directories as needed):

```ini
[Unit]
Description=Paperless Genie Telegram Bot
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/Repositories/paperless-genie
ExecStart=/home/your-username/Repositories/paperless-genie/.venv/bin/python -m paperless_genie
Restart=always
RestartSec=10
EnvironmentFile=/home/your-username/Repositories/paperless-genie/.env

[Install]
WantedBy=multi-user.target
```

### 3. Start the Service

```bash
# Reload systemd manager configuration
sudo systemctl daemon-reload

# Start service immediately
sudo systemctl start paperless-genie

# Enable service to run on boot
sudo systemctl enable paperless-genie
```

### 4. Monitor Logs

```bash
journalctl -u paperless-genie -f
```
