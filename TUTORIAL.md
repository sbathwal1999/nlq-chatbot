# NLQ Chatbot — Complete Tutorial

A step-by-step learning guide covering business context, architecture, AI/ML concepts,
every tool used, and how all the components fit together.

---

## Table of Contents

1. [Business Understanding](#1-business-understanding)
2. [The Problem We Are Solving](#2-the-problem-we-are-solving)
3. [The Solution](#3-the-solution)
4. [Prerequisites](#4-prerequisites)
5. [Tools & Technologies](#5-tools--technologies)
6. [Architecture Deep Dive](#6-architecture-deep-dive)
7. [Data Science & AI Concepts](#7-data-science--ai-concepts)
8. [Component Walkthrough](#8-component-walkthrough)
9. [The Data Model](#9-the-data-model)
10. [End-to-End Request Flow](#10-end-to-end-request-flow)
11. [Configuration Reference](#11-configuration-reference)
12. [Running the Project](#12-running-the-project)
13. [Extending the Project](#13-extending-the-project)

---

## 1. Business Understanding

### The Scenario

Imagine you work at a retail company. The business generates data every day — orders
placed, products sold, customers returning, shipments dispatched. All of this data
lives in a PostgreSQL database managed by the engineering team.

Now imagine you are a **business analyst**. You have questions:

- *Which products sold the most last month?*
- *How many orders are still pending in the North region?*
- *Which customers haven't bought anything in the last 90 days?*

These are perfectly reasonable business questions. But to answer them, you currently
have to:

1. Write a support ticket to the data engineering team
2. Wait 1–2 business days for someone to find time
3. Receive a CSV file via email
4. Open it in Excel and try to make sense of it

This process is slow, creates a bottleneck on the data team, and means decisions are
made with stale data.

### The Opportunity

The data already exists. The answers are in the database. The only barrier is that
the business analyst **doesn't know SQL** — the language needed to talk to the database.

What if the analyst could just *ask the question in plain English* and get the answer
immediately?

That is exactly what this project builds.

---

## 2. The Problem We Are Solving

### The Technical Gap

```
Business Analyst                    Database
      │                                 │
      │  "Top 5 products last month?"   │
      │  ──────────────────────────►   │
      │                                 │
      │  ◄──────────────────────────   │
      │  ??? (need SQL)                 │
```

The database only understands SQL:

```sql
SELECT p.name, SUM(oi.quantity) AS units_sold
FROM order_items oi
JOIN orders o ON oi.order_id = o.id
JOIN products p ON oi.product_id = p.id
WHERE o.ordered_at >= NOW() - INTERVAL '30 days'
  AND o.status != 'cancelled'
GROUP BY p.name
ORDER BY units_sold DESC
LIMIT 5;
```

A business analyst cannot be expected to write this. So we need a **bridge** — something
that can translate natural language into SQL automatically.

### Why Not Just Train Everyone on SQL?

- SQL takes weeks to learn properly
- Complex joins, aggregations, and date logic take months to master
- Business analysts should focus on analysing outcomes, not writing queries
- Staff turnover means constant retraining

### Why Not Just Use a Dashboard?

- Dashboards answer *predetermined* questions (the ones whoever built it thought to ask)
- Any new question requires a developer to update the dashboard
- The bottleneck still exists — it just moved

---

## 3. The Solution

We build a **Natural Language Query (NLQ) chatbot** that:

1. Accepts plain English questions in a chat interface
2. Uses an AI language model to translate the question into SQL
3. Executes the SQL against the real database
4. Returns the answer as a human-readable sentence

```
Business Analyst                    NLQ Chatbot                    Database
      │                                 │                               │
      │  "Top 5 products last month?"   │                               │
      │ ─────────────────────────────► │                               │
      │                                 │  SELECT p.name, SUM(...)      │
      │                                 │ ─────────────────────────────►│
      │                                 │                               │
      │                                 │ ◄─────────────────────────────│
      │                                 │  [(Wireless Mouse, 6), ...]   │
      │  "The top 5 products were..."   │                               │
      │ ◄─────────────────────────────  │                               │
```

Everything runs locally in Docker — no cloud account needed, no data leaves your
infrastructure.

---

## 4. Prerequisites

Before you can run this project, you need the following installed on your machine.

### 4.1 Docker Desktop

Docker is a containerisation platform. It packages software and all its dependencies
into isolated units called **containers**. You don't need to install Python, PostgreSQL,
or any libraries manually — Docker handles all of that.

- **Install:** https://www.docker.com/products/docker-desktop
- **Verify:** `docker --version` should print a version number
- **Why we need it:** Every service in this project runs as a Docker container

### 4.2 Docker Compose

Docker Compose is a tool for defining and running multi-container applications using
a single configuration file (`docker-compose.yml`).

- Usually bundled with Docker Desktop
- **Verify:** `docker compose version`
- **Why we need it:** We have two containers (app + database) that need to talk to each
  other. Compose wires them together.

### 4.3 A Groq API Key (Free)

Groq is a cloud service that provides fast, free-tier access to open-source AI models.
We use it to run the Llama 3.3 language model.

- **Sign up:** https://console.groq.com
- Click **"Create API Key"** — it starts with `gsk_`
- **Why Groq:** It's free, fast (sub-second inference), and provides excellent
  open-source models. No credit card required for the free tier.

### 4.4 Git (optional but recommended)

To clone the repository.

- **Install:** https://git-scm.com
- **Verify:** `git --version`

### Knowledge Prerequisites

| Topic | Level needed | Why |
|---|---|---|
| Command line basics | Beginner | Running Docker commands |
| What a database is | Beginner | Understanding the data layer |
| What an API is | Beginner | Understanding how services communicate |
| SQL | None required | That's the whole point of this project |
| Python | None required to run; helpful to extend | App code is Python |
| AI/ML | None required | Concepts explained in Section 7 |

---

## 5. Tools & Technologies

### 5.1 Chainlit

**What it is:** A Python framework for building chat interfaces for AI applications.

**What it does in this project:** Serves the web-based chat UI at `http://localhost:8000`.
You write a single Python file (`app.py`) with decorated functions and Chainlit handles
all the HTML, WebSockets, and streaming — no frontend code needed.

**Key concepts:**
- `@cl.on_chat_start` — runs once when a user opens a new chat session
- `@cl.on_message` — runs every time the user sends a message
- `cl.user_session` — stores data per browser session (like our agent and history)
- `cl.Message` — sends a message back to the UI

**Why Chainlit over alternatives (Streamlit, Gradio):**
Chainlit is purpose-built for LLM chat apps. It has native support for streaming,
multi-turn conversations, and tool-use step display — all things we use.

---

### 5.2 LangChain

**What it is:** A Python framework for building applications powered by language models.

**What it does in this project:** Provides `create_sql_agent` — a pre-built agent that
connects an LLM to a SQL database, handles schema injection, SQL execution, and
answer generation.

**Key LangChain concepts used:**

| Concept | What it means |
|---|---|
| `SQLDatabase` | A wrapper around a SQLAlchemy database connection that exposes schema info to the LLM |
| `create_sql_agent` | Builds an agent that can call SQL tools in a loop |
| `SQL_PREFIX` | The default system prompt template for the SQL agent |
| `agent_type="tool-calling"` | Uses native function-calling rather than text-based ReAct parsing |

**Why LangChain:** It handles the complex parts of NLQ — schema injection, prompt
construction, tool orchestration, and result parsing — without us having to build
any of that from scratch.

---

### 5.3 Groq API + Llama 3.3 70B

**What Groq is:** A cloud inference platform. Groq builds specialised hardware (LPUs —
Language Processing Units) optimised for running AI models extremely fast.

**What Llama 3.3 70B is:** An open-source large language model (LLM) built by Meta.
"70B" means 70 billion parameters — a measure of model size and capability.
"Versatile" means this variant is optimised for instruction following across diverse tasks.

**Why this model for SQL generation:**
- Large enough (70B params) to understand complex queries and schema relationships
- Strong instruction-following — it reliably follows the business rules we inject
- Fast on Groq's hardware — typically < 2 seconds for SQL generation
- Free tier is sufficient for development and demos

**Alternative models available on Groq** (can be set via `GROQ_MODEL` env var):
- `llama-3.1-8b-instant` — much faster, lower quality SQL
- `llama-3.3-70b-versatile` — our default, best balance
- `meta-llama/llama-4-scout-17b-16e-inst` — newer, worth experimenting with

---

### 5.4 PostgreSQL

**What it is:** The world's most advanced open-source relational database.

**What it does in this project:** Stores the retail data (customers, products, orders,
order items) and executes the SQL queries the agent generates.

**Why PostgreSQL:**
- Industry standard — most real companies use it
- LangChain has native `postgresql+psycopg2` dialect support
- Rich SQL features: `NOW()`, `INTERVAL`, `ILIKE`, window functions, CTEs
- The LLM generates better SQL for PostgreSQL because it has seen so much of it in
  training data

---

### 5.5 Docker + Docker Compose

**What Docker is:** A platform that packages applications into containers — isolated
environments with their own filesystem, dependencies, and runtime.

**What Docker Compose is:** A tool to define multi-container applications in a single
YAML file and start them all with one command.

**How we use it:**

```
docker-compose.yml
    │
    ├── postgres service  →  builds from postgres/Dockerfile
    │                        runs PostgreSQL with init.sql seeded
    │
    └── app service       →  builds from app/Dockerfile
                             installs Python deps, runs Chainlit
```

The two containers communicate over Docker's internal network — the app container
reaches the database at hostname `postgres` (the service name), not `localhost`.

---

### 5.6 uv (Package Manager)

**What it is:** A modern, extremely fast Python package manager written in Rust,
built by Astral (the same team behind Ruff).

**Why not pip:** `uv` is 10–100x faster than pip for dependency resolution and
installation. It's increasingly the standard for new Python projects.

**How we use it:**

```bash
# Install dependencies from requirements.txt
uv pip install -r requirements.txt

# Run the app with env vars loaded from .env
uv run --env-file .env chainlit run app.py
```

Inside Docker, `uv` is copied from its official image and used to install packages
into the container's system Python.

---

### 5.7 SQLAlchemy

**What it is:** Python's most popular SQL toolkit and ORM (Object-Relational Mapper).

**What it does in this project:** We use it purely as a database connection layer —
LangChain's `SQLDatabase` wraps it to build the connection URL and introspect the schema.

**The connection URL format:**
```
postgresql+psycopg2://user:password@host:port/database
    │           │
    │           └── Python driver (psycopg2)
    └── Database engine (postgresql)
```

---

### 5.8 pydantic

**What it is:** A Python data validation library. Also the backbone of FastAPI and
many modern Python frameworks.

**What it does in this project:** We use `SecretStr` — a special string type that
prevents the API key from being accidentally logged or printed.

```python
# Without SecretStr — key appears in logs
api_key = "gsk_abc123..."
print(api_key)  # gsk_abc123...  ← dangerous

# With SecretStr — key is masked
api_key = SecretStr("gsk_abc123...")
print(api_key)  # **********  ← safe
```

---

## 6. Architecture Deep Dive

### 6.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        User's Browser                           │
│                   http://localhost:8000                         │
└──────────────────────────────┬──────────────────────────────────┘
                               │ WebSocket (real-time chat)
┌──────────────────────────────▼──────────────────────────────────┐
│                     Docker Network                              │
│                                                                 │
│  ┌─────────────────────────────────┐                           │
│  │        app container            │                           │
│  │        (port 8000)              │                           │
│  │                                 │                           │
│  │  Chainlit (Web UI + Server)     │                           │
│  │       │                         │                           │
│  │  app.py (message routing)       │                           │
│  │       │                         │                           │
│  │  guard.py (SQL safety check)    │                           │
│  │       │                         │                           │
│  │  chain.py (LangChain agent)─────┼──► Groq API (external)   │
│  │                         │       │    llama-3.3-70b          │
│  │                         │       │                           │
│  └─────────────────────────┼───────┘                           │
│                             │ psycopg2 / SQLAlchemy             │
│  ┌──────────────────────────▼───────┐                           │
│  │      postgres container          │                           │
│  │      (port 5432)                 │                           │
│  │                                  │                           │
│  │  PostgreSQL 16                   │                           │
│  │  Database: retaildb              │                           │
│  │  Tables: customers, products,    │                           │
│  │          orders, order_items     │                           │
│  └──────────────────────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

### 6.2 Container Architecture

**Why two containers?**

Each container does one thing. This follows the **single responsibility principle**
for infrastructure. Benefits:

- You can rebuild just the app container without touching the database
- The database persists data in a named volume even if the app restarts
- Each container can be scaled, replaced, or upgraded independently
- Mirrors how real production deployments work

**Health checks and startup order:**

The `app` container must NOT start until PostgreSQL is ready to accept connections.
We enforce this with:

```yaml
depends_on:
  postgres:
    condition: service_healthy   # waits for pg_isready to pass
```

If the app started first, it would crash trying to connect to a database that isn't
ready yet.

### 6.3 Data Flow

```
1. User types question
        │
        ▼
2. app.py: on_message()
        │
        ├── _looks_like_sql()?
        │       └── YES → guard.py: is_safe()?
        │               └── NO  → block, return error
        │               └── YES → continue
        │       └── NO  → continue (plain English)
        │
        ├── _build_prompt_with_history()
        │       Prepends last 5 Q&A turns to the question
        │
        ▼
3. chain.py: agent.invoke({"input": prompt})
        │
        ├── LangChain sends schema info + question to Groq
        │       System message: AGENT_PREFIX (business rules + SQL instructions)
        │       User message: the question
        │
        ├── Groq returns a tool call (JSON): sql_db_list_tables
        │
        ├── LangChain calls sql_db_schema with relevant tables
        │
        ├── Groq returns a tool call (JSON): sql_db_query with SELECT ...
        │
        ├── LangChain executes the SQL on PostgreSQL
        │
        ├── LangChain sends rows back to Groq as a tool result
        │
        └── Groq returns: plain English answer
                │
                ▼
4. app.py: history updated, answer sent to Chainlit UI
```

---

## 7. Data Science & AI Concepts

This section explains the AI and data science ideas behind the project — no prior
knowledge assumed.

### 7.1 What is a Large Language Model (LLM)?

A Large Language Model is a type of AI model trained on vast amounts of text
(books, websites, code, research papers). Through training, it learns patterns
in language — grammar, facts, reasoning, and even code.

The model works by **predicting the next token** (roughly: the next word or
subword). Given enough examples, this simple objective leads to models that can:

- Answer questions
- Write code
- Translate languages
- Generate SQL from natural language descriptions

**Llama 3.3 70B** is one such model. It was trained by Meta on trillions of tokens
and has 70 billion internal parameters (numbers that encode what it has "learned").

### 7.2 What is a Prompt?

A **prompt** is the text input you send to an LLM. The quality of the output
depends heavily on how you structure the prompt — this is called **prompt engineering**.

In this project we construct a carefully structured prompt for every query:

```
┌─────────────────────────────────────────┐
│  SYSTEM MESSAGE (AGENT_PREFIX)          │  ← Business rules + SQL instructions
│  - Business rules (no cancelled orders) │     Set once at agent creation
│  - Date conventions                     │
│  - PostgreSQL dialect instructions      │
│  - Standard LangChain SQL agent prompt  │
├─────────────────────────────────────────┤
│  TOOL RESULTS                           │  ← Schema info fetched from DB
│  - Table names                          │     Injected automatically by LangChain
│  - Column names and types               │
│  - Sample rows                          │
├─────────────────────────────────────────┤
│  CONVERSATION HISTORY                   │  ← Last 5 Q&A turns
│  - Previous questions                   │     Prepended in app.py
│  - Previous answers                     │
├─────────────────────────────────────────┤
│  USER QUESTION                          │  ← What the user typed
│  "What were the top 5 products..."      │
└─────────────────────────────────────────┘
```

### 7.3 What is a SQL Agent?

A **SQL agent** is an LLM + a set of tools + a loop that decides which tools to call.

The tools available to our SQL agent:

| Tool | What it does |
|---|---|
| `sql_db_list_tables` | Lists all tables in the database |
| `sql_db_schema` | Gets the CREATE TABLE statement + sample rows for given tables |
| `sql_db_query` | Executes a SQL query and returns results |
| `sql_db_query_checker` | Asks the LLM to double-check SQL before executing |

The agent loop:

```
Question received
      │
      ▼
LLM thinks: "I need to know what tables exist"
      │
      ▼
Calls: sql_db_list_tables → ["customers", "products", "orders", "order_items"]
      │
      ▼
LLM thinks: "I need the schema for orders and order_items"
      │
      ▼
Calls: sql_db_schema → CREATE TABLE orders (...), CREATE TABLE order_items (...)
      │
      ▼
LLM thinks: "Now I can write the SQL"
      │
      ▼
Calls: sql_db_query → SELECT p.name, SUM(oi.quantity)...
      │
      ▼
Gets results → formats into plain English → returns answer
```

### 7.4 Tool-Calling vs ReAct

There are two major patterns for building agents:

**ReAct (Reason + Act)** — legacy approach:
- The LLM outputs structured text: `Thought: ... Action: ... Action Input: ...`
- A text parser extracts the action and calls the tool
- The result is appended as `Observation: ...`
- Repeat until the LLM outputs `Final Answer:`
- **Problem:** Strict text formatting. If the LLM outputs anything unexpected
  (which Llama sometimes does), the parser fails with "observation missing" errors

**Tool-Calling** — modern approach (what we use):
- The LLM has a list of available functions with JSON schemas
- When it needs a tool, it returns a structured JSON function call (not text)
- The framework calls the actual function and passes the result back
- Much more reliable — no brittle text parsing
- This is how OpenAI function-calling works, and Groq/Llama supports it natively

```python
agent_type="tool-calling"  # in chain.py — this is why we chose this
```

### 7.5 What is Schema Injection?

For the LLM to write correct SQL, it needs to know:
- What tables exist
- What columns each table has
- What the data types are
- How tables relate to each other (foreign keys)

This information is called the **database schema**. LangChain's `SQLDatabase` fetches
this automatically and includes it in the prompt. This is called **schema injection**.

Without schema injection, the LLM would have to guess table and column names —
leading to SQL errors on every query.

### 7.6 What is Conversation History?

LLMs are **stateless** — each call is independent. When you ask a follow-up question
like "What about yesterday?", the model has no memory of what "the previous question"
was unless you tell it.

We solve this by maintaining a list of recent Q&A turns per session and prepending
them to every new question:

```
Previous conversation:
  User: What were the top 5 products sold last month?
  Assistant: The top 5 products were Wireless Mouse (6 units), ...

Current question: What about yesterday?
```

With this context, the LLM understands that "What about yesterday?" refers to
"top 5 products sold" — and generates the correct SQL.

We keep only the last 5 turns (`_HISTORY_WINDOW = 5`) to avoid making the prompt
too long, which would slow down the LLM and cost more tokens.

### 7.7 What is Temperature?

**Temperature** is a parameter that controls how creative/random the LLM's output is:

| Temperature | Behaviour | Use case |
|---|---|---|
| 0.0 | Deterministic — always picks the most likely next token | SQL generation, factual answers |
| 0.7 | Some randomness — varied, creative output | Creative writing, brainstorming |
| 1.0+ | High randomness — unpredictable output | Exploration, poetry |

We set `temperature=0` because SQL must be **exact**. A creative SQL query is a
broken SQL query.

### 7.8 What is top_k (Row Limiting)?

The `top_k` parameter in `create_sql_agent` automatically adds a `LIMIT N` clause
to generated SQL queries. We set it to 50.

**Why this matters:**
- A question like "Show me all orders" against a real database could return millions
  of rows
- All those rows would be stuffed into the LLM's context window (there's a max size)
- The LLM would either fail or give a garbled answer
- Response time would be extremely slow

With `top_k=50`, the agent always fetches at most 50 rows per query — enough to
answer analytical questions, not enough to overflow the context.

---

## 8. Component Walkthrough

### 8.1 `app/app.py` — The Entrypoint

This is the file Chainlit reads. It defines two event handlers:

**`on_chat_start()`**
- Called once when a user opens a new browser tab
- Builds the SQL agent by calling `build_chain()`
- Stores the agent + an empty history list in `cl.user_session`
- Sends a welcome message

**`on_message(message)`**
- Called every time the user sends a message
- Runs the SQL guard check if the input looks like raw SQL
- Enriches the question with conversation history
- Invokes the agent and streams the answer back
- Updates the history store

**`_looks_like_sql(text)`**
- Cheap pre-filter: checks if the first word is a SQL keyword
- Returns True for `"SELECT * FROM..."`, False for `"What were the top..."`
- This avoids running the full regex guard on every natural language question

**`_build_prompt_with_history(question, history)`**
- Serialises recent turns as plain text
- Returns a combined prompt string the agent can understand

---

### 8.2 `app/chain.py` — The Agent

This is where the LLM and database are connected.

**`AGENT_PREFIX`**
The custom system prompt. Built by prepending `_BUSINESS_RULES` to the default
`SQL_PREFIX` from LangChain. The business rules ensure:
- Cancelled orders are never counted in sales metrics
- Date terms ("last month", "yesterday") map to consistent SQL expressions
- Aggregation patterns (SUM by product for sales, SUM of quantity × price for revenue)

**`build_chain()`**
Constructs the agent in three steps:

1. **LLM** — `ChatGroq` with `temperature=0` and the model name from `GROQ_MODEL` env var
2. **Database** — `SQLDatabase.from_uri()` connects to PostgreSQL and exposes schema
3. **Agent** — `create_sql_agent` with `agent_type="tool-calling"` and our custom prefix

The function logs each step so startup issues are immediately visible in logs.

---

### 8.3 `app/guard.py` — The Safety Filter

Prevents destructive SQL from reaching the database.

**Why this exists:**
The SQL agent is designed to only generate SELECT statements. But users can also type
raw SQL directly into the chat. Without a guard, someone could type `DROP TABLE orders`
and execute it.

**How it works:**

```python
def is_safe(sql: str) -> bool:
    # 1. Strip SQL comments (-- and /* */)
    #    Prevents tricks like: /* ignore above */ DROP TABLE orders
    
    # 2. Check for blocked keywords at start of statement
    #    Catches: DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, CREATE, REPLACE, MERGE
    
    # 3. Strip leading CTEs (WITH ... AS (...))
    #    Ensures WITH cte AS (...) DELETE ... is also blocked
    
    # 4. Require the remaining statement to start with SELECT
```

Only called from `app.py` when `_looks_like_sql()` returns True — so plain English
questions never hit this code path.

---

### 8.4 `postgres/init.sql` — The Demo Data

Automatically executed by PostgreSQL on first container startup.

**Schema design:**

```
customers ──┐
            │ (one customer has many orders)
orders ─────┤
            │ (one order has many items)
order_items ┤
            │ (each item references one product)
products ───┘
```

**Why this schema:**
It mirrors a real retail database closely enough to generate interesting analytical
queries — top products, regional analysis, customer activity — without being so
complex that it confuses the LLM.

**The cancelled order:**
Order 6 (Frank Lee) is deliberately seeded as `cancelled` with 5x Ballpoint Pens.
This tests that the business rules (never count cancelled orders) are working
correctly. If the chatbot includes these 5 pens in "top products" results, the
business rules are being ignored.

---

### 8.5 `docker-compose.yml` — The Orchestrator

Defines both services and their relationships.

**Key patterns:**

```yaml
healthcheck:                          # PostgreSQL readiness check
  test: ["CMD-SHELL", "pg_isready"]
  interval: 5s
  retries: 10

depends_on:
  postgres:
    condition: service_healthy        # App waits for DB to be ready

volumes:
  postgres_data:                      # Named volume persists data across restarts

environment:
  MAX_ROWS: ${MAX_ROWS:-50}          # ${VAR:-default} syntax: use .env value or fallback
```

**The `${VAR:-default}` pattern:**
Docker Compose reads your `.env` file automatically. `${MAX_ROWS:-50}` means: use
the value of `MAX_ROWS` from `.env` if set, otherwise use `50`. This gives you
sensible defaults without requiring every variable to be present in `.env`.

---

### 8.6 `app/Dockerfile` — The App Container

```dockerfile
FROM python:3.11-slim                           # Small base image

COPY --from=ghcr.io/astral-sh/uv:0.4.29 /uv   # Copy uv binary from its official image
     /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml requirements.txt ./         # Copy deps FIRST (Docker layer caching)
RUN uv pip install --system --no-cache \        # Install deps (cached if unchanged)
    -r requirements.txt

COPY app.py chain.py guard.py ./                # Copy code LAST (changes frequently)

CMD ["chainlit", "run", "app.py",               # Start Chainlit
     "--host", "0.0.0.0", "--port", "8000"]
```

**Why copy dependencies before code?**

Docker builds images in layers. Each `COPY` or `RUN` instruction creates a new layer.
Layers are cached — if a layer hasn't changed, Docker reuses the cached version.

Dependencies change rarely. Code changes constantly. By copying and installing
dependencies first, a code-only change (fixing a typo in `app.py`) reuses the
dependency layer — the install step is skipped. Build time goes from ~60s to ~2s.

---

## 9. The Data Model

### Tables

**`customers`**
```
id          — unique identifier
name        — full name
email       — unique email address
region      — North | South | East | West
created_at  — when they signed up
```

**`products`**
```
id          — unique identifier
name        — product name
category    — Electronics | Office | Stationery
price       — current price (NUMERIC for precision, never use FLOAT for money)
```

**`orders`**
```
id          — unique identifier
customer_id — which customer placed it (FK → customers)
status      — pending | shipped | delivered | cancelled
ordered_at  — timestamp of order placement
```

**`order_items`**
```
id          — unique identifier
order_id    — which order this belongs to (FK → orders)
product_id  — which product (FK → products)
quantity    — how many units
unit_price  — price at time of order (snapshot — products.price may change later)
```

### Why `unit_price` is a snapshot?

If you want to calculate the revenue from an order placed 6 months ago, you need
to know what the price was at that time — not the current price. Storing
`unit_price` in `order_items` at the time of ordering solves this.

### Entity Relationship Diagram

```
customers          orders             order_items        products
─────────          ──────             ───────────        ────────
id (PK)  ◄───┐    id (PK)    ┌──►   id (PK)            id (PK)
name          └── customer_id │       order_id (FK)─┘   name
email             status      │       product_id (FK)──► category
region            ordered_at  │       quantity            price
created_at                    └────── unit_price
```

---

## 10. End-to-End Request Flow

Let's trace exactly what happens when a user types:
**"What were the top 5 products sold last month?"**

### Step 1 — User Input (Browser → Chainlit)
The browser sends the message over a WebSocket connection to the Chainlit server
running in the app container.

### Step 2 — `on_message()` in `app.py`
```python
question = "What were the top 5 products sold last month?"
```
- `_looks_like_sql("What...")` → `False` (doesn't start with SQL keyword)
- Guard check skipped
- History is empty (first message), so prompt = question as-is

### Step 3 — Agent invoked in `chain.py`
`agent.invoke({"input": "What were the top 5 products sold last month?"})`

### Step 4 — LangChain sends to Groq
The full message to Groq looks like:

```
[System]: You are a helpful data analyst assistant for a retail company.
Business rules — apply these to EVERY query without exception:
- NEVER include orders with status = 'cancelled'...
- "last month" means the past 30 days...
[+ standard LangChain SQL agent instructions]

[Human]: What were the top 5 products sold last month?
```

### Step 5 — Groq returns a tool call
```json
{
  "tool": "sql_db_list_tables",
  "arguments": {}
}
```

### Step 6 — LangChain executes the tool
Queries PostgreSQL: `SELECT table_name FROM information_schema.tables...`
Returns: `"customers, order_items, orders, products"`

### Step 7 — Groq returns another tool call
```json
{
  "tool": "sql_db_schema",
  "arguments": {"table_names": "orders, order_items, products"}
}
```

### Step 8 — LangChain fetches schema
Returns the CREATE TABLE statements + 3 sample rows from each table.

### Step 9 — Groq generates the SQL query tool call
```json
{
  "tool": "sql_db_query",
  "arguments": {
    "query": "SELECT p.name, SUM(oi.quantity) AS units_sold FROM order_items oi JOIN orders o ON oi.order_id = o.id JOIN products p ON oi.product_id = p.id WHERE o.ordered_at >= NOW() - INTERVAL '30 days' AND o.status != 'cancelled' GROUP BY p.name ORDER BY units_sold DESC LIMIT 5"
  }
}
```

Note how the business rule (`AND o.status != 'cancelled'`) was applied automatically.

### Step 10 — LangChain executes the SQL
PostgreSQL returns:
```
[("Wireless Mouse", 6), ("Notebook (A5)", 3), ("Mechanical Keyboard", 3), ...]
```

### Step 11 — Groq formats the answer
Groq receives the raw rows and returns a plain English sentence:
> "The top 5 products sold last month were: 1. Wireless Mouse (6 units)..."

### Step 12 — Answer returned to UI
`app.py` receives the answer, updates the session history, and sends it to
Chainlit which renders it in the browser.

**Total time:** approximately 2–5 seconds.

---

## 11. Configuration Reference

All configuration is done via environment variables in `.env`.

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROQ_API_KEY` | ✅ Yes | — | Your Groq API key (starts with `gsk_`) |
| `POSTGRES_USER` | ✅ Yes | — | PostgreSQL username |
| `POSTGRES_PASSWORD` | ✅ Yes | — | PostgreSQL password |
| `POSTGRES_DB` | ✅ Yes | — | Database name |
| `POSTGRES_HOST` | No | `postgres` | DB hostname (Docker service name) |
| `POSTGRES_PORT` | No | `5432` | DB port |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Groq model ID to use |
| `MAX_ROWS` | No | `50` | Max rows returned per SQL query |

**Switching models without rebuilding:**
```bash
# In .env
GROQ_MODEL=llama-3.1-8b-instant   # faster, less accurate

# Then recreate the container (no rebuild needed — it's just an env var)
docker compose up -d app
```

---

## 12. Running the Project

### First time setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd nlq-chatbot

# 2. Create your .env file
cp .env.example .env

# 3. Edit .env — add your Groq API key
#    Get one free at https://console.groq.com
nano .env   # or open in any editor

# 4. Build and start everything
docker compose up --build

# 5. Open the chat UI
open http://localhost:8000
```

### Day-to-day usage

```bash
# Start (without rebuilding — much faster)
docker compose up -d

# Stop
docker compose down

# View logs
docker compose logs -f app       # app logs (LLM calls, errors)
docker compose logs -f postgres  # database logs

# Rebuild after code changes
docker compose up -d --build app
```

### Resetting the database

The database volume persists across restarts. To reset to the seed data:

```bash
docker compose down -v        # -v removes volumes
docker compose up --build     # fresh start, init.sql runs again
```

### Local development (no Docker)

```bash
cd app
uv pip install -r requirements.txt

# Start a local PostgreSQL however you prefer, then:
uv run --env-file ../.env chainlit run app.py
```

---

## 13. Extending the Project

### Connect your own database

1. Update `.env` with your real DB credentials
2. Remove the `postgres` service from `docker-compose.yml` (or keep it for testing)
3. Update `POSTGRES_HOST` to point to your real database
4. Update `_BUSINESS_RULES` in `chain.py` with your domain's rules

### Add more business rules

Edit `_BUSINESS_RULES` in `app/chain.py`:

```python
_BUSINESS_RULES = """
...existing rules...
- "active customer" means ordered within the last 180 days.
- Revenue calculations should exclude the 'internal' region.
"""
```

Rebuild: `docker compose up -d --build app`

### Increase conversation history

Edit `_HISTORY_WINDOW` in `app/app.py`:

```python
_HISTORY_WINDOW = 10   # remember last 10 turns instead of 5
```

Trade-off: more context = better follow-ups but slower responses and more tokens used.

### Try a different model

```bash
# In .env
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-inst

# Recreate container
docker compose up -d app
```

No code change or rebuild needed.

### Add authentication

Chainlit has built-in auth support. See the Chainlit docs for:
- Password-based auth
- OAuth (GitHub, Google)
- Custom auth callbacks

---

*This tutorial covers the full learning arc — from the business problem through to the
running system. Every design decision has a reason, and every tool was chosen for
a specific purpose. The best way to deepen your understanding is to run the project,
ask it questions, read the logs, and experiment with the configuration.*
