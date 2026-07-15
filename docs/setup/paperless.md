# Paperless-ngx API Token Guide

`paperless-genie` interacts with Paperless-ngx using individual user API tokens. This guarantees that all search and upload requests are executed under the permission context of the corresponding family member.

---

## 🔑 How to Generate an API Token

1. **Log in**: Open your Paperless-ngx web dashboard and log in with your credentials.
2. **Access Profile Settings**: Click on your username in the top-right corner and select **My Profile** (or go to `https://your-paperless-instance.com/accounts/profile/`).
3. **API Access Tokens**: Locate the **API access tokens** section.
4. **Create Token**:
   * Click on **Add Token**.
   * Give it a descriptive name (e.g., `Telegram Bot`).
   * Click **Save** / **Generate**.
5. **Copy Token**: Copy the generated alphanumeric token. **Important: It will only be shown once!** If you lose it, you will need to delete and generate a new one.

---

## 👥 Multi-User Permissions Setup

Each family member should follow these steps using their own Paperless-ngx account.

This ensures that:
* **Private Documents**: Documents uploaded by one user that are marked private (or visible only to them/their group) will **not** be searchable or visible to other users querying the Telegram bot.
* **Traceability**: Documents uploaded via the bot will correctly display the corresponding uploader as the owner in the Paperless-ngx dashboard.
