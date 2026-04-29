# 09 — End-to-End Request Flow

## Table of Contents

1. [Overview](#1-overview)
2. [Full Flow Diagram](#2-full-flow-diagram)
3. [Step-by-Step Trace](#3-step-by-step-trace)
4. [The Agent Sub-Loop](#4-the-agent-sub-loop)
5. [Follow-Up Question Flow](#5-follow-up-question-flow)
6. [Error Paths](#6-error-paths)
7. [Timing Breakdown](#7-timing-breakdown)

---

## 1. Overview

This document traces a complete user request from the moment a user types a question
to the moment they see an answer. Every component, function call, and network hop is
covered.

**Example question we will trace:**
> "What were the top 5 products by revenue last month?"

---

## 2. Full Flow Diagram

```
User's browser
     │
     │  [1] User types question, presses Enter
     │
     ▼  WebSocket message
Chainlit server (port 8000)
     │
     │  [2] on_message() called
     │
     ▼
app.py: strip whitespace
     │
     ▼
app.py: _looks_like_sql()?
     │  → "What were..." starts with "What" — NOT a SQL keyword
     │  → skip guard entirely
     │
     ▼
app.py: _build_prompt_with_history()
     │  → no history yet (first question)
     │  → prompt = original question unchanged
     │
     ▼
cl.Step("Querying database...") shown in browser
     │
     ▼
cl.make_async(agent.invoke)({"input": prompt})
     │  runs in thread pool (non-blocking)
     │
     ▼  ┌──────────────────────────────────────────────┐
        │         LANGCHAIN AGENT LOOP                 │
        │                                              │
        │  Iteration 1:                                │
        │    LLM → call sql_db_list_tables             │
        │    Tool → "customers,order_items,orders,     │
        │            products"                         │
        │                                              │
        │  Iteration 2:                                │
        │    LLM → call sql_db_schema                  │
        │    Input: "order_items, orders, products"    │
        │    Tool → CREATE TABLE orders (...),         │
        │           CREATE TABLE order_items (...),    │
        │           CREATE TABLE products (...)        │
        │           + 3 sample rows each               │
        │                                              │
        │  Iteration 3:                                │
        │    LLM → call sql_db_query                   │
        │    Input: SELECT p.name,                     │
        │             SUM(oi.quantity*oi.unit_price)   │
        │             AS revenue                       │
        │           FROM order_items oi                │
        │           JOIN orders o ON ...               │
        │           JOIN products p ON ...             │
        │           WHERE o.status != 'cancelled'      │
        │             AND o.ordered_at >= NOW()        │
        │                  - INTERVAL '30 days'        │
        │           GROUP BY p.name                    │
        │           ORDER BY revenue DESC              │
        │           LIMIT 5                            │
        │    Tool → [("Laptop Pro", 4500.00), ...]     │
        │                                              │
        │  Iteration 4:                                │
        │    LLM → final answer                        │
        │    Output: "The top 5 products by revenue    │
        │             last month were:                 │
        │             1. Laptop Pro — £4,500..."       │
        │                                              │
        └──────────────────────────────────────────────┘
     │
     ▼
app.py: extract result["output"]
     │
     ▼
app.py: history.append({question, answer})
     │
     ▼
cl.Message(content=answer).send()
     │
     ▼  WebSocket message
User's browser renders answer
```

---

## 3. Step-by-Step Trace

### Step 1 — Browser sends message

The user types "What were the top 5 products by revenue last month?" and presses Enter.

The browser sends a WebSocket frame to the Chainlit server at `ws://localhost:8000`.
WebSocket is a persistent, full-duplex connection — unlike HTTP, it stays open for
the duration of the session. This allows instant message delivery in both directions.

### Step 2 — Chainlit receives message

Chainlit's server receives the WebSocket frame and calls:

```python
@cl.on_message
async def on_message(message: cl.Message) -> None:
    question = message.content.strip()
```

`message.content` is the raw text. `.strip()` removes any accidental leading or
trailing whitespace.

At this point: `question = "What were the top 5 products by revenue last month?"`

### Step 3 — Guard check

```python
if _looks_like_sql(question) and not is_safe(question):
    ...
```

`_looks_like_sql("What were the top 5...")`:
- Split on whitespace: `["What", "were", "the", ...]`
- First token: `"What"`
- Is `"WHAT"` in `_SQL_FIRST_WORDS`? No.
- Returns `False`

Because `_looks_like_sql()` returned `False`, `is_safe()` is never called.
We continue.

### Step 4 — History check

```python
history: list[dict[str, str]] = cl.user_session.get("history")
prompt = _build_prompt_with_history(question, history[-_HISTORY_WINDOW:])
```

`history` is `[]` (first message in this session).

`_build_prompt_with_history("What were...", [])`:
- `if not history:` → True
- Returns the question unchanged

`prompt = "What were the top 5 products by revenue last month?"`

### Step 5 — Show progress step

```python
async with cl.Step(name="Querying database..."):
```

The browser immediately shows a "Querying database..." indicator. The user knows
something is happening. This is important for UX — database queries can take 3-8
seconds.

### Step 6 — Invoke the agent

```python
result = await cl.make_async(agent.invoke)({"input": prompt})
```

`cl.make_async()` wraps `agent.invoke` (synchronous) and schedules it on a thread
pool. The `await` suspends this coroutine until the thread pool finishes. The event
loop remains free to handle other users' messages.

This call crosses into the LangChain agent loop (detailed in Section 4 below).

When it returns: `result = {"input": "...", "output": "The top 5 products were..."}`

### Step 7 — Extract answer

```python
answer = result.get("output", "I couldn't find an answer to that.")
```

`result["output"]` is the LLM's final answer in plain English.

### Step 8 — Update history

```python
history.append({"question": question, "answer": answer})
cl.user_session.set("history", history)
```

We save the original question (not the enriched prompt) and the answer. On the next
message, this turn will be prepended as context.

### Step 9 — Send answer to browser

```python
await cl.Message(content=answer).send()
```

Chainlit sends a WebSocket frame to the user's browser. The browser renders the
answer in the chat interface. The `cl.Step` closes automatically.

**Total elapsed time:** ~3-8 seconds (dominated by Groq API latency and DB query).

---

## 4. The Agent Sub-Loop

Inside `agent.invoke()`, LangChain runs its agent loop. Here is what happens
for each iteration.

### Iteration 1 — Discover Tables

The LLM receives:
```
[system: AGENT_PREFIX — business rules + SQL instructions for postgresql, top_k=50]
[user: "What were the top 5 products by revenue last month?"]
```

The LLM outputs (in JSON tool-calling format):
```json
{
  "name": "sql_db_list_tables",
  "arguments": {}
}
```

LangChain calls `sql_db_list_tables()`.

The tool queries `information_schema.tables` and returns:
```
customers, order_items, orders, products
```

This result is appended to the conversation as a tool observation.

### Iteration 2 — Get Schema

The LLM now sees the table list. It knows `order_items`, `orders`, and `products`
are relevant for a revenue query. It outputs:

```json
{
  "name": "sql_db_schema",
  "arguments": {"table_names": "order_items, orders, products"}
}
```

LangChain calls `sql_db_schema()`. The tool returns:

```sql
CREATE TABLE orders (
  id INTEGER NOT NULL,
  customer_id INTEGER,
  status VARCHAR,
  ordered_at TIMESTAMP WITHOUT TIME ZONE,
  PRIMARY KEY (id)
)
/*
3 rows from orders table:
id    customer_id    status      ordered_at
1     3              delivered   2024-11-15 10:32:00
2     7              pending     2024-11-28 14:05:00
5     2              cancelled   2024-11-20 09:15:00
*/

CREATE TABLE order_items (...)
CREATE TABLE products (...)
```

The sample rows are critical — they show the LLM that:
- `status` values include `'cancelled'` (reinforcing the business rule)
- `ordered_at` is a TIMESTAMP (so NOW() - INTERVAL works)
- The date format in use

### Iteration 3 — Execute Query

The LLM now has everything it needs. It generates the SQL:

```json
{
  "name": "sql_db_query",
  "arguments": {
    "query": "SELECT p.name, SUM(oi.quantity * oi.unit_price) AS revenue FROM order_items oi JOIN orders o ON oi.order_id = o.id JOIN products p ON oi.product_id = p.id WHERE o.status != 'cancelled' AND o.ordered_at >= NOW() - INTERVAL '30 days' GROUP BY p.name ORDER BY revenue DESC LIMIT 5"
  }
}
```

LangChain calls `sql_db_query()`. The tool:
1. Passes the SQL to `db.run(query)` — which calls psycopg2
2. psycopg2 sends the SQL over TCP to the PostgreSQL container
3. PostgreSQL executes the query, returns rows
4. psycopg2 receives the rows, returns them to LangChain
5. LangChain formats the rows as a string

Tool returns:
```
[('Laptop Pro', Decimal('4500.00')), ('USB Hub', Decimal('3200.00')), ...]
```

### Iteration 4 — Format Answer

The LLM sees the raw query results and formats them into a human-readable answer:

```
The top 5 products by revenue last month were:

1. Laptop Pro — £4,500.00
2. USB Hub — £3,200.00
3. Wireless Mouse — £2,100.00
4. Mechanical Keyboard — £1,800.00
5. Monitor Stand — £950.00
```

The LLM signals a final answer (rather than another tool call). LangChain exits
the loop and returns this as `result["output"]`.

---

## 5. Follow-Up Question Flow

Suppose the user now asks: "What about by units instead of revenue?"

### What Changes

**Step 4 — History check (different now)**

`history` is now:
```python
[{
    "question": "What were the top 5 products by revenue last month?",
    "answer": "The top 5 products by revenue last month were: 1. Laptop Pro..."
}]
```

`_build_prompt_with_history()` builds:
```
Previous conversation:
  User: What were the top 5 products by revenue last month?
  Assistant: The top 5 products by revenue last month were: 1. Laptop Pro...

Current question: What about by units instead of revenue?
```

**The Agent Now Has Context**

The LLM receives this enriched prompt. It understands:
- "What about" refers to the previous question (top 5 products last month)
- "units" means `SUM(quantity)` instead of `SUM(quantity * unit_price)`
- The time filter and other constraints should remain the same

It generates an appropriate query without being asked to specify "last month" again.

**Why This Works**

The LLM was not told "remember the previous question". The context is injected
as plain text at the start of the current prompt. The LLM sees it as part of the
current request and uses it naturally.

---

## 6. Error Paths

### Path A — Blocked SQL Input

User types: `DROP TABLE customers`

```
question = "DROP TABLE customers"

_looks_like_sql("DROP TABLE customers")
  → first token: "DROP"
  → "DROP" in _SQL_FIRST_WORDS → True

is_safe("DROP TABLE customers")
  → strips comments → "DROP TABLE customers"
  → _BLOCKED_PATTERN.match("DROP TABLE customers") → match found
  → returns False

→ cl.Message("Sorry, I can only answer read-only questions...").send()
→ return (agent never called)
```

### Path B — Agent Error (DB Connection Failure)

```
agent.invoke({"input": prompt})
  → psycopg2 cannot connect to PostgreSQL
  → raises OperationalError

except Exception as exc:
  logger.exception("Agent error: %s", exc)
  answer = f"Something went wrong while querying the database: {exc}"

→ cl.Message(content=answer).send()
→ session continues (user can try again)
```

### Path C — Groq API Error (Rate Limit)

```
agent.invoke({"input": prompt})
  → ChatGroq makes HTTP request to Groq API
  → Groq returns 429 Too Many Requests
  → raises RateLimitError

except Exception as exc:
  logger.exception("Agent error: %s", exc)
  answer = f"Something went wrong while querying the database: RateLimitError..."

→ cl.Message(content=answer).send()
```

### Path D — Agent Reaches Max Iterations

```
agent.invoke({"input": prompt})
  → agent runs 15 iterations without producing a final answer
  → returns {"input": "...", "output": "Agent stopped due to..."}

result.get("output", "I couldn't find an answer.")
  → returns the max-iterations message or default fallback
```

---

## 7. Timing Breakdown

For a typical question, here is where the time goes:

```
Component                  Typical latency
─────────────────────────────────────────────────────────
WebSocket receive           < 1ms
strip + guard check         < 1ms
build_prompt_with_history   < 1ms
─────────────────────────────────────────────────────────
Agent Iteration 1 (list tables)
  LLM call (Groq)           300-800ms
  sql_db_list_tables         5-20ms
─────────────────────────────────────────────────────────
Agent Iteration 2 (schema)
  LLM call (Groq)           300-800ms
  sql_db_schema              5-20ms
─────────────────────────────────────────────────────────
Agent Iteration 3 (query)
  LLM call (Groq)           500-1500ms  ← SQL generation is the longest LLM call
  sql_db_query               10-100ms   (depends on query complexity)
─────────────────────────────────────────────────────────
Agent Iteration 4 (format)
  LLM call (Groq)           300-800ms
─────────────────────────────────────────────────────────
WebSocket send              < 1ms
─────────────────────────────────────────────────────────
TOTAL                       ~2-4 seconds (typical)
                            ~5-8 seconds (complex queries)
```

**The bottleneck is Groq API latency** — 4 LLM calls per request, each taking
300-1500ms. Local database queries are fast in comparison.

Groq runs Llama models on custom inference hardware (Language Processing Units),
which makes it significantly faster than most cloud LLM providers. For the same
model on OpenAI-equivalent infrastructure, latencies would be 2-3x higher.
