# Architecture

Paperless Genie is a small, single-process async application. A Telegram message
comes in, and depending on its type it either runs a **search** query or an
**archiving** workflow against your Paperless-ngx instance, driven by an AI agent
that calls Paperless through the Model Context Protocol (MCP).

## High-level flow

```mermaid
flowchart LR
    user([You]) -->|message / document| tg[Telegram]
    tg <-->|long polling| bot["bot.py<br/>handlers + create_bot()"]

    bot -->|per-user token| pc["paperless.py<br/>PaperlessClient"]
    bot -->|run_agent| ag["agent.py<br/>prompts + run loop"]
    bot -.->|per-user history| conv["conversation.py"]

    ag -->|spawns| mcp["paperless-mcp<br/>(Node subprocess)"]
    pc -->|REST| paperless[("Paperless-ngx")]
    mcp -->|REST| paperless
    ag -->|LLM| gemini{{"Gemini<br/>(Antigravity SDK)"}}
```

Every module has one job:

| Module | Responsibility |
| --- | --- |
| `config.py` | Load and validate environment configuration; map Telegram user IDs → Paperless tokens. |
| `bot.py` | Telegram handlers and the `create_bot()` factory; authorization; response formatting (chunking, download buttons). |
| `paperless.py` | `PaperlessClient` — all Paperless-ngx REST calls and the upload/OCR polling state machine. No Telegram dependency. |
| `agent.py` | System prompts, MCP server wiring, and the shared `run_agent()` loop. No Telegram dependency. |
| `conversation.py` | Bounded per-user chat history for search context. |

The split matters for two reasons: **security** — the MCP subprocess receives only
an allowlisted environment plus the requesting user's own token, never the bot
token, the Gemini key, or other users' tokens; and **testability** — `paperless.py`
and `agent.py` have no Telegram dependency, so the polling state machine and the
prompt contracts are unit-tested directly.

## Search query

A plain text message is treated as a natural-language query. The agent uses the
Paperless MCP tools to find documents and answers in the user's own language;
the bot turns any `[#ID]` markers in the reply into inline download buttons.

```mermaid
sequenceDiagram
    autonumber
    participant U as You
    participant B as bot.py
    participant A as agent.py
    participant M as paperless-mcp
    participant P as Paperless-ngx

    U->>B: "What contracts do we have from 1993?"
    B->>B: authorize + build prompt with chat history
    B->>A: run_agent(SEARCH_INSTRUCTIONS, prompt, token)
    A->>M: spawn MCP server (user-scoped env)
    A->>M: search / fetch documents
    M->>P: REST queries
    P-->>M: matching documents
    M-->>A: results
    A-->>B: answer with [#ID] markers
    B->>U: reply + 📥 download buttons
```

## Document archiving

Sending a PDF or photo triggers the archiving workflow. The upload and OCR wait
happen in Python (`PaperlessClient`), with live status edits in the chat; only
once the document exists does the agent enrich it.

```mermaid
sequenceDiagram
    autonumber
    participant U as You
    participant B as bot.py
    participant C as PaperlessClient
    participant P as Paperless-ngx
    participant A as agent.py
    participant M as paperless-mcp

    U->>B: upload document
    B->>C: upload_and_wait_for_ocr(on_status=…)
    C->>P: POST /api/documents/post_document/
    P-->>C: task id
    loop until SUCCESS / FAILED / timeout
        C->>P: GET /api/tasks/?task_id=…
        C-->>B: on_status("⚙️ Waiting for OCR…")
        B-->>U: status edit
    end
    alt duplicate
        C-->>B: DuplicateDocumentError(existing id)
        B->>U: "already exists as #N" + button
    else new document
        C-->>B: new document id
        B->>A: run_agent(ARCHIVE_INSTRUCTIONS, …)
        A->>M: read content, set metadata, tags, note
        M->>P: REST
        A-->>B: report (document's own language)
        B->>U: "✅ Processing completed" + report
    end
```

## Deployment shape

The bot ships as a single Docker image (published to GHCR) that bundles Python
and Node.js — Node is needed because the Paperless MCP server is a Node package,
pinned and pre-installed into the image so message handling never fetches code at
runtime. It runs as an unprivileged user, holds no database of its own, and keeps
state only in memory (conversation history) for the lifetime of the process. See
the [Deployment Guide](deployment.md) for running it via Docker Compose or systemd.
