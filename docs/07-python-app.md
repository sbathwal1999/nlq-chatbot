# 07 — Python Application Layer

## Table of Contents

1. [Project Structure](#1-project-structure)
2. [Chainlit — The Chat Framework](#2-chainlit--the-chat-framework)
3. [app.py — Message Routing & Session Management](#3-apppy--message-routing--session-management)
4. [chain.py — LangChain Agent Setup](#4-chainpy--langchain-agent-setup)
5. [guard.py — SQL Safety Validation](#5-guardpy--sql-safety-validation)
6. [Async Python in Chainlit](#6-async-python-in-chainlit)
7. [Session Isolation](#7-session-isolation)
8. [Error Handling Strategy](#8-error-handling-strategy)
9. [Logging](#9-logging)

---

## 1. Project Structure

```
app/
├── app.py          ← Chainlit entrypoint, message routing, session management
├── chain.py        ← LangChain SQL agent construction
├── guard.py        ← SQL safety validation
├── pyproject.toml  ← Project metadata and dependencies (uv/pip)
├── requirements.txt← Pinned dependency list (Docker build)
└── Dockerfile      ← Container build instructions
```

Each file has a single, clear responsibility. This makes the codebase easy to navigate
and easy to test in isolation.

---

## 2. Chainlit — The Chat Framework

### What is Chainlit?

Chainlit is a Python framework purpose-built for LLM chat applications. It provides:

- A ready-made web chat UI (no HTML/CSS/JS required)
- WebSocket handling between browser and Python server
- Session management per browser tab
- Streaming support for token-by-token output
- A decorator-based API for handling chat events

Without Chainlit, building a chat interface would require:
- A web server (FastAPI, Flask)
- WebSocket handling
- A frontend (React, Vue, or raw HTML)
- Session state management
- Deployment configuration

Chainlit handles all of this so we can focus on the AI logic.

### The Decorator Pattern

Chainlit uses Python decorators to register event handlers:

```python
import chainlit as cl

@cl.on_chat_start
async def on_chat_start() -> None:
    """Called once when a user opens a new chat session."""
    pass

@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Called every time the user sends a message."""
    pass
```

A **decorator** (`@cl.on_chat_start`) is Python syntax for wrapping a function.
`@cl.on_chat_start` tells Chainlit: "register this function as the handler for
the chat-start event". When a user opens the chatbot, Chainlit calls `on_chat_start`.
When they send a message, Chainlit calls `on_message`.

### Starting the Server

```bash
chainlit run app.py --host 0.0.0.0 --port 8000
```

- `run app.py` — which Python file is the entrypoint
- `--host 0.0.0.0` — listen on all network interfaces (required inside Docker)
- `--port 8000` — which port to serve on

In Docker, `0.0.0.0` means "accept connections from anywhere", not just localhost.
Without this, the container would listen only on its own loopback and be unreachable
from the host machine.

### Sending Messages

```python
await cl.Message(content="Hello, how can I help?").send()
```

`cl.Message` creates a chat message. `.send()` pushes it to the user's browser over
the WebSocket connection. The `await` is required because `.send()` is an async
operation — it waits for the WebSocket write to complete before continuing.

### Steps — Showing Progress

```python
async with cl.Step(name="Querying database..."):
    result = await cl.make_async(agent.invoke)({"input": prompt})
```

`cl.Step` displays a collapsible progress indicator in the UI while the database
query runs. Users see "Querying database..." while they wait, rather than a blank
screen. The step automatically closes when the `async with` block exits.

---

## 3. app.py — Message Routing & Session Management

### Full File

```python
import logging
from typing import Any

import chainlit as cl

from chain import build_chain
from guard import is_safe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

_SQL_FIRST_WORDS = {
    "SELECT", "WITH", "DROP", "DELETE", "UPDATE",
    "INSERT", "ALTER", "TRUNCATE", "CREATE",
}
_HISTORY_WINDOW = 5


def _looks_like_sql(text: str) -> bool:
    """Return True if the first token of text is a SQL keyword."""
    tokens = text.split()
    return bool(tokens) and tokens[0].upper() in _SQL_FIRST_WORDS


def _build_prompt_with_history(
    question: str, history: list[dict[str, str]]
) -> str:
    """Prepend the recent conversation history to the current question."""
    if not history:
        return question
    lines = ["Previous conversation:"]
    for turn in history:
        lines.append(f"  User: {turn['question']}")
        lines.append(f"  Assistant: {turn['answer']}")
    lines.append(f"\nCurrent question: {question}")
    return "\n".join(lines)


@cl.on_chat_start
async def on_chat_start() -> None:
    """Initialise per-session state when a user opens the chat."""
    agent = build_chain()
    cl.user_session.set("agent", agent)
    cl.user_session.set("history", [])


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Handle an incoming user message."""
    question = message.content.strip()

    if _looks_like_sql(question) and not is_safe(question):
        await cl.Message(
            content="Sorry, I can only answer read-only questions about the data."
        ).send()
        return

    agent: Any = cl.user_session.get("agent")
    history: list[dict[str, str]] = cl.user_session.get("history")
    prompt = _build_prompt_with_history(question, history[-_HISTORY_WINDOW:])

    async with cl.Step(name="Querying database..."):
        try:
            result = await cl.make_async(agent.invoke)({"input": prompt})
            answer = result.get("output", "I couldn't find an answer to that.")
        except Exception as exc:
            logger.exception("Agent error: %s", exc)
            answer = f"Something went wrong while querying the database: {exc}"

    history.append({"question": question, "answer": answer})
    cl.user_session.set("history", history)
    await cl.Message(content=answer).send()
```

### Walking Through on_chat_start

```python
@cl.on_chat_start
async def on_chat_start() -> None:
    agent = build_chain()              # Build a fresh LangChain agent
    cl.user_session.set("agent", agent)   # Store it in this session
    cl.user_session.set("history", [])    # Start with empty history
```

`build_chain()` creates a new SQL agent — including a database connection. This runs
once per session, not per message. Creating a database connection is expensive; we
reuse it for the lifetime of the session.

### Walking Through on_message

**Step 1 — Sanitise input**
```python
question = message.content.strip()
```
Remove leading/trailing whitespace. A user accidentally hitting space before typing
should not cause failures.

**Step 2 — Guard check**
```python
if _looks_like_sql(question) and not is_safe(question):
    await cl.Message(content="Sorry...").send()
    return
```
Only check guard if input looks like SQL (starts with a SQL keyword). Natural language
always passes through — `is_safe()` is not called for "What were sales last month?".

**Step 3 — Build prompt with history**
```python
prompt = _build_prompt_with_history(question, history[-_HISTORY_WINDOW:])
```
Take the last 5 turns of history and prepend them to the current question. This gives
the LLM context for follow-up questions like "What about last week?".

**Step 4 — Invoke the agent**
```python
async with cl.Step(name="Querying database..."):
    result = await cl.make_async(agent.invoke)({"input": prompt})
```
`agent.invoke()` is synchronous. `cl.make_async()` wraps it so it runs in a thread
pool, allowing the async event loop to remain responsive while the database query runs.

**Step 5 — Store history and send answer**
```python
history.append({"question": question, "answer": answer})
cl.user_session.set("history", history)
await cl.Message(content=answer).send()
```
The raw question (not the enriched prompt) is saved to history. This keeps history
clean — we don't want to nest history-within-history on the next turn.

---

## 4. chain.py — LangChain Agent Setup

### Full File

```python
import logging
import os

from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.prompt import SQL_PREFIX
from langchain_community.utilities import SQLDatabase
from langchain_groq import ChatGroq
from pydantic import SecretStr

logger = logging.getLogger(__name__)

_BUSINESS_RULES = """You are a helpful data analyst assistant for a retail company.

Business rules — apply these to EVERY query without exception:
- NEVER include orders with status = 'cancelled' when calculating sales, quantities, or revenue.
- "sold", "top products", "best sellers", "revenue" always mean non-cancelled orders only.
  Always add the filter: WHERE orders.status != 'cancelled'
- Valid order statuses are: pending, shipped, delivered, cancelled.
- "last month" means the past 30 days from today (use NOW() - INTERVAL '30 days').
- "yesterday" means the previous calendar day (use CURRENT_DATE - 1).
- "this week" means the past 7 days (use NOW() - INTERVAL '7 days').
- For sales volume questions, SUM(order_items.quantity) grouped by product.
- For revenue questions, SUM(order_items.quantity * order_items.unit_price).
"""

AGENT_PREFIX = _BUSINESS_RULES + SQL_PREFIX


def build_chain() -> object:
    """Construct and return a LangChain SQL agent connected to PostgreSQL."""
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    llm = ChatGroq(
        model=model,
        temperature=0,
        api_key=SecretStr(os.environ["GROQ_API_KEY"]),
    )
    db_url = (
        f"postgresql+psycopg2://"
        f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'localhost')}"
        f":{os.environ.get('POSTGRES_PORT', '5432')}"
        f"/{os.environ['POSTGRES_DB']}"
    )
    db = SQLDatabase.from_uri(db_url)
    top_k = int(os.environ.get("MAX_ROWS", 50))
    agent = create_sql_agent(
        llm=llm,
        db=db,
        agent_type="tool-calling",
        top_k=top_k,
        prefix=AGENT_PREFIX,
        verbose=False,
        agent_executor_kwargs={"handle_parsing_errors": True},
    )
    return agent
```

### Key Decisions in chain.py

**`temperature=0`** — Deterministic output. For SQL generation, creativity is
harmful. We want the most likely correct query, not a creative interpretation.

**`AGENT_PREFIX = _BUSINESS_RULES + SQL_PREFIX`** — Business rules come first.
The LLM gives more weight to instructions near the beginning of the system prompt.

**`agent_type="tool-calling"`** — Uses JSON function calling instead of text-based
ReAct. More reliable with Llama models. See doc 05 for the full comparison.

**`handle_parsing_errors=True`** — If the LLM produces malformed output, the error
text is fed back to the LLM as a tool observation rather than crashing.

**`POSTGRES_HOST` with default `localhost`** — Inside Docker, the hostname is
`postgres` (the service name). When running locally with `uv run`, the hostname is
`localhost`. The default handles the local case; Docker Compose overrides it.

---

## 5. guard.py — SQL Safety Validation

### Full File

```python
import logging
import re

logger = logging.getLogger(__name__)

_BLOCKED_PATTERN = re.compile(
    r"^\s*(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)
_CTE_PREFIX = re.compile(r"^WITH\s+\w+.*?\)\s*", re.DOTALL | re.IGNORECASE)


def is_safe(sql: str) -> bool:
    """Return True if sql is a read-only SELECT (or CTE → SELECT) statement."""
    clean = re.sub(r"--.*$", "", sql, flags=re.MULTILINE).strip()
    clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL).strip()

    if not clean:
        return False
    if _BLOCKED_PATTERN.match(clean):
        return False

    body = _CTE_PREFIX.sub("", clean).strip()
    if not body.upper().startswith("SELECT"):
        return False

    return True
```

### Why Comment Stripping Matters

```sql
-- A naive guard might miss this:
/* DROP TABLE */ SELECT * FROM customers;

-- After stripping comments:
SELECT * FROM customers;  ← safe
```

Without stripping comments, an attacker could embed dangerous keywords inside
comments to confuse keyword-based detection.

### The Two-Stage Check

1. **Blocked pattern** — immediately reject any statement starting with a destructive
   keyword (DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, CREATE, REPLACE, MERGE)

2. **CTE prefix strip** — a valid CTE looks like `WITH name AS (...) SELECT ...`.
   After removing the CTE prefix, the remainder must start with SELECT.

This handles:
```sql
-- Simple SELECT ✓
SELECT * FROM customers

-- CTE → SELECT ✓
WITH top_customers AS (SELECT ...) SELECT * FROM top_customers

-- DELETE blocked ✗
DELETE FROM customers

-- Obfuscated via CTE: blocked because body isn't SELECT ✗
WITH x AS (SELECT 1) DELETE FROM customers
```

### What guard.py Does NOT Do

guard.py only runs when the user types raw SQL directly. It does not validate the
SQL the LLM generates — that is handled by the LLM's own prompt constraints and
by the read-only database user (in production).

The guard is a defence against a user deliberately trying to bypass the chatbot
by typing destructive SQL commands directly into the input box.

---

## 6. Async Python in Chainlit

### Why Async?

Chainlit is an async framework built on Starlette/asyncio. Async Python allows a
single process to handle many concurrent connections without blocking.

**Synchronous problem:**
```
User A sends message
  → handler starts, blocks waiting for database (3 seconds)
  → meanwhile User B's message sits in queue
  → User B waits 3 seconds just for their request to start
```

**Async solution:**
```
User A sends message
  → handler starts, awaits database (non-blocking)
  → while waiting, User B's message is handled
  → both queries run concurrently
```

### The `async def` / `await` Pattern

```python
async def on_message(message: cl.Message) -> None:
    # This is an async function — it can await
    result = await cl.make_async(agent.invoke)({"input": prompt})
    await cl.Message(content=answer).send()
```

- `async def` declares the function as a coroutine
- `await` suspends the current coroutine and yields control to the event loop
- Other coroutines can run while we wait

### The Problem: Synchronous Agent

LangChain's `agent.invoke()` is synchronous. It blocks the thread it runs on.
If we called it directly in an async handler, it would block the event loop —
preventing Chainlit from handling other users' messages.

```python
# BAD — blocks the event loop
result = agent.invoke({"input": prompt})

# GOOD — runs in a thread pool, event loop stays free
result = await cl.make_async(agent.invoke)({"input": prompt})
```

`cl.make_async()` wraps a synchronous function and runs it in a thread pool executor.
The event loop delegates the blocking work to a separate thread and can keep running
other coroutines while it waits.

---

## 7. Session Isolation

### What is cl.user_session?

`cl.user_session` is a per-connection dictionary managed by Chainlit. Each browser
tab that connects to the chatbot gets its own isolated session.

```python
# Store a value — scoped to THIS session only
cl.user_session.set("agent", agent)
cl.user_session.set("history", [])

# Retrieve — always from THIS session
agent   = cl.user_session.get("agent")
history = cl.user_session.get("history")
```

### Why Isolation Matters

Without session isolation, two users talking simultaneously would share state:

```
User A asks: "Top 5 products?"
  → agent stores history: [{"question": "Top 5 products?", "answer": "..."}]

User B asks: "What about last week?"
  → agent reads history: sees User A's question as context!
  → gives User B a confusing, wrong answer
```

With `cl.user_session`, each user has their own history list. Their conversations
are completely independent.

### Session Lifecycle

```
Browser tab opens
    │
    ▼
on_chat_start() called
    │   agent = build_chain()
    │   cl.user_session.set("agent", agent)
    │   cl.user_session.set("history", [])
    │
    ▼
User sends messages
    │   on_message() called for each message
    │   history grows with each turn
    │
    ▼
Browser tab closes or page refresh
    └── session destroyed, agent and history garbage collected
```

There is no persistence across sessions. Refreshing the browser starts fresh.

---

## 8. Error Handling Strategy

### Catch-All in on_message

```python
try:
    result = await cl.make_async(agent.invoke)({"input": prompt})
    answer = result.get("output", "I couldn't find an answer to that.")
except Exception as exc:
    logger.exception("Agent error: %s", exc)
    answer = f"Something went wrong while querying the database: {exc}"
```

We catch all exceptions at the top level and:
1. Log the full traceback via `logger.exception()`
2. Return a human-readable error message to the user
3. Continue — the session is not destroyed, the user can try again

This is the right boundary for error handling. Errors inside `agent.invoke()` are
either:
- LangChain parsing errors (caught by `handle_parsing_errors=True`)
- Database connection failures
- Groq API errors (rate limits, network issues)
- Unexpected LLM output

All of these are unrecoverable at the agent level but recoverable at the session
level — the user can ask again.

### The Fallback Answer

```python
answer = result.get("output", "I couldn't find an answer to that.")
```

`result` is always a dict from LangChain. It should always contain `"output"`, but
`.get()` with a default handles the case where the key is missing (e.g. the agent
reached `max_iterations` without producing a final answer).

---

## 9. Logging

### Configuration

```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)
```

`__name__` is a Python built-in that resolves to the module's fully-qualified name
(`app`, `chain`, `guard`). This means log lines identify which module they came from:

```
2024-11-15 10:32:05 [INFO] app: Starting session
2024-11-15 10:32:07 [ERROR] app: Agent error: Connection refused
2024-11-15 10:32:07 [INFO] guard: Blocked unsafe SQL: DROP TABLE customers
```

### Log Levels

| Level | When to use |
|---|---|
| `DEBUG` | Detailed diagnostic info (disabled in production) |
| `INFO` | Normal operational messages |
| `WARNING` | Something unexpected but handled |
| `ERROR` | A specific operation failed |
| `CRITICAL` | System-level failure |

We use `INFO` as the default level. `logger.exception()` logs at ERROR level and
automatically includes the full stack trace.

### What We Log

- Agent errors (with full traceback via `logger.exception`)
- Blocked SQL attempts in `guard.py`

We deliberately do not log user questions or answers — these may contain sensitive
business data.
