# Gemini API Key Guide

`paperless-genie` uses the **Google Antigravity SDK**, which requires a Google Gemini API Key to run its AI-powered document analysis and chat functions.

---

## 🔑 How to Get a Gemini API Key

1. **Visit Google AI Studio**: Go to **[Google AI Studio](https://aistudio.google.com/)** and sign in with your Google account.
2. **Access API Keys Page**: Click on the **Get API key** button in the left sidebar (or navigate directly to the [API Keys page](https://aistudio.google.com/app/apikey)).
3. **Create Key**:
   * Click the blue **Create API key** button.
   * Choose **Create API key in new project** (this creates an isolated Google Cloud project for your key).
4. **Copy Key**: Copy the generated API key (it begins with `AIzaSy...`). Keep it secure!

---

## 🆓 Why Choose the Free Tier?

When you create a new key, by default it starts on the **Free tier**. We recommend keeping it on the Free tier because:

* **Zero Cost**: Google does not charge anything for API usage on the Free tier.
* **Generous Limits**: The Free tier provides highly generous rate limits (e.g., 15 Requests Per Minute and 1,500 Requests Per Day for Gemini 1.5 Flash). This is more than enough for personal or family archiving needs.
* **Safe from Accidental Costs**: Since billing is not set up, you never have to worry about receiving unexpected bills for API usage.

> [!NOTE]
> Consumer subscriptions like **Google One AI Premium** apply to the Gemini Advanced web interface (`gemini.google.com`), not to Google AI Studio API usage. However, the Free tier is open to everyone and works perfectly for the bot.
