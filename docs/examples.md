# Example Queries

The bot understands natural language — there is no query syntax to learn, and
you can ask in any language (it answers in the language you write in). Below
are the kinds of requests it handles, from simple lookups to analytics.

## Finding documents

* *"Where is my passport?"*
* *"Find the 2024 apartment insurance policy."*
* *"List all contracts with Acme Corp signed before 2020."*
* *"Show the vet invoices from last spring."*

Every document the bot mentions comes with a 📥 button to download the
original PDF right in the chat.

## Reading a document's content

The agent can open a found document and answer from its text:

* *"When does my passport expire?"*
* *"What's the notice period in my rental agreement?"*
* *"Which IBAN is on the January electricity invoice?"*

## Totals, comparisons & analytics

Because an AI agent (not a keyword index) processes your query, it can fetch a
set of documents and reason over them:

* *"How much did we spend on utilities in 2025?"*
* *"How did the electricity bills change compared to last year?"*
* *"Sum all pharmacy receipts from March."*
* *"Which month had the highest heating bill?"*

> **A note on accuracy.** These answers are computed by the language model
> from the text of the documents it retrieves — they depend on your archive's
> OCR quality and on the model itself. Treat totals as a smart assistant's
> summary rather than accounting-grade aggregation, and spot-check important
> figures against the source documents via the 📥 buttons.

## Follow-up questions

The bot keeps a short per-user conversation history, so you can refine
without repeating yourself:

* *"How much did we spend on utilities in 2025?"* → *"And compared to 2024?"*
* *"Find my lease agreements."* → *"Only the ones from Riga."*

Use `/clear` to start a fresh topic when you switch context.

## Archiving documents

Send a **PDF or photo** straight into the chat. The bot uploads it to
Paperless-ngx, waits for OCR, and the agent then sets the title, date,
correspondent, type and tags, and writes a structured note — reporting back in
the document's own language. Duplicates are detected and linked instead of
re-uploaded. For photos, the caption (if any) becomes the filename.

## Commands

| Command | What it does |
| --- | --- |
| `/start`, `/help` | Show the welcome message with capabilities. |
| `/get <id>` | Download a document by its Paperless ID. |
| `/clear` | Reset the conversation history for a fresh topic. |
