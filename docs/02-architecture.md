# 02 — System Architecture

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Component Map](#2-component-map)
3. [Container Architecture](#3-container-architecture)
4. [Network Architecture](#4-network-architecture)
5. [Data Architecture](#5-data-architecture)
6. [Application Architecture](#6-application-architecture)
7. [AI/Agent Architecture](#7-aiagent-architecture)
8. [Security Architecture](#8-security-architecture)
9. [Key Design Decisions](#9-key-design-decisions)

---

## 1. Architecture Overview

The NLQ Chatbot follows a **three-tier architecture** running entirely on a single
machine via Docker Compose:

```
┌─────────────────────────────────────────────────────────────────────┐
│  TIER 1 — PRESENTATION                                              │
│  User's browser → Chainlit Web UI (http://localhost:8000)           │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ WebSocket
┌───────────────────────────▼─────────────────────────────────────────┐
│  TIER 2 — APPLICATION                                               │
│  app container (Python)                                             │
│  ├── Chainlit server (request handling, session management)         │
│  ├── app.py  (routing, guard, history)                              │
│  ├── chain.py (LangChain agent, Groq LLM connection)                │
│  └── guard.py (SQL safety validation)                               │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ psycopg2 / SQLAlchemy (TCP 5432)
┌───────────────────────────▼─────────────────────────────────────────┐
│  TIER 3 — DATA                                                      │
│  postgres container (PostgreSQL 16)                                 │
│  └── retaildb: customers, products, orders, order_items             │
└─────────────────────────────────────────────────────────────────────┘
                            │
                    ┌───────▼──────┐
                    │  EXTERNAL    │
                    │  Groq API    │
                    │  (HTTPS 443) │
                    └──────────────┘
```

---

## 2. Component Map

| Component | Technology | Responsibility |
|---|---|---|
| Chat UI | Chainlit | Render chat interface, handle WebSocket connections |
| Message Router | `app.py` | Route messages, apply guard, manage history |
| SQL Guard | `guard.py` | Validate input SQL is read-only |
| LLM Agent | `chain.py` + LangChain | Translate NL → SQL → answer |
| Language Model | Groq API / Llama 3.3 70B | Generate SQL and plain-English answers |
| Database Driver | psycopg2 | Execute SQL against PostgreSQL |
| Database | PostgreSQL 16 | Store and query retail data |
| Orchestrator | Docker Compose | Start, network, and manage all containers |

---

## 3. Container Architecture

### Why Containers?

A **container** packages an application with all its dependencies — the runtime,
libraries, configuration — into an isolated, portable unit. Unlike a traditional
install, a container:

- Runs identically on any machine with Docker installed
- Does not interfere with other software on the host
- Can be started, stopped, and rebuilt in seconds
- Is defined entirely by a `Dockerfile` — version-controlled infrastructure

### Our Containers

**Container 1: `postgres`**

```dockerfile
FROM postgres:16-alpine          # Official PostgreSQL image, Alpine = small
COPY init.sql /docker-entrypoint-initdb.d/
# PostgreSQL auto-runs all .sql files in this directory on first startup
```

- Runs PostgreSQL 16
- Seeds the demo schema and data on first start via `init.sql`
- Exposes port 5432 for both the app container and local tools (DBeaver, psql)
- Data persists in a named Docker volume (`postgres_data`) across restarts

**Container 2: `app`**

```dockerfile
FROM python:3.11-slim            # Small Python base
COPY --from=ghcr.io/astral-sh/uv:0.4.29 /uv /usr/local/bin/uv
# Install uv from its official image — copy just the binary

WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt
# Layer caching: this only re-runs if dependencies change

COPY app.py chain.py guard.py ./
CMD ["chainlit", "run", "app.py", "--host", "0.0.0.0", "--port", "8000"]
```

- Runs the Chainlit web server on port 8000
- All Python dependencies pre-installed in the image
- Waits for PostgreSQL to be healthy before starting (via `depends_on`)

### Docker Layer Caching — Why It Matters

Docker builds images in layers. Each instruction (`FROM`, `COPY`, `RUN`) creates
one layer. Layers are cached — if nothing changed, Docker reuses the cached layer.

```
Layer 1: FROM python:3.11-slim          ← rarely changes → almost always cached
Layer 2: COPY uv binary                 ← rarely changes → almost always cached
Layer 3: COPY pyproject.toml            ← changes when deps change
Layer 4: RUN uv pip install ...         ← depends on Layer 3 → cached unless deps change
Layer 5: COPY app.py chain.py guard.py  ← changes with code
```

**Key insight:** We copy dependency files first, then code. A code-only change
(fixing a bug in `app.py`) only invalidates Layer 5. Layers 1–4 are reused.
Build time: ~2 seconds instead of ~60 seconds.

---

## 4. Network Architecture

### Docker's Internal Network

When Docker Compose starts, it creates a private virtual network for all services
defined in `docker-compose.yml`. Services can reach each other by service name.

```
Host Machine
└── Docker Network: nlq-chatbot_default
    ├── postgres (internal IP: 172.x.x.x, hostname: "postgres")
    │   └── exposed to host on port 5432
    └── app (internal IP: 172.x.x.x, hostname: "app")
        └── exposed to host on port 8000
```

**This is why `POSTGRES_HOST=postgres`** in the app's environment. Inside the Docker
network, the database is reachable at hostname `postgres` — the service name — not
`localhost` (which would refer to the app container itself).

```yaml
# docker-compose.yml
app:
  environment:
    POSTGRES_HOST: postgres    # ← Docker service name, not localhost
```

**On the host machine**, you access:
- The chat UI at `http://localhost:8000`
- The database at `localhost:5432` (for local tools like DBeaver)

### Port Mapping

```yaml
ports:
  - "8000:8000"    # host_port:container_port
  - "5432:5432"    # host_port:container_port
```

`"8000:8000"` means: forward traffic from host port 8000 into container port 8000.

---

## 5. Data Architecture

### Storage

Data is stored in a PostgreSQL named volume:

```yaml
volumes:
  postgres_data:    # declared at root of docker-compose.yml

postgres:
  volumes:
    - postgres_data:/var/lib/postgresql/data
```

A **named volume** is managed by Docker, stored on the host filesystem, and persists
when containers stop or are removed. Only `docker compose down -v` deletes it.

### Schema

Four tables in a classic retail schema:

```
customers          orders              order_items         products
─────────          ──────              ───────────         ────────
id (PK)            id (PK)             id (PK)             id (PK)
name               customer_id (FK)    order_id (FK)       name
email              status              product_id (FK)     category
region             ordered_at          quantity            price
created_at                             unit_price
```

See `docs/06-postgresql-and-data.md` for the full data modelling deep dive.

---

## 6. Application Architecture

### Session Management

Chainlit uses **server-side sessions**. Each browser tab gets its own isolated session
with its own state. `cl.user_session` is a per-session key-value store.

```python
# Set in on_chat_start — per-session
cl.user_session.set("agent", agent)      # the SQL agent
cl.user_session.set("history", [])       # conversation turns

# Retrieve in on_message — always from the same session
agent   = cl.user_session.get("agent")
history = cl.user_session.get("history")
```

Two users opening the chatbot simultaneously get **completely separate sessions** —
their agents, histories, and conversations are isolated.

### Request Processing Pipeline

```
User message
     │
     ▼
1. strip() — remove leading/trailing whitespace
     │
     ▼
2. _looks_like_sql()? — check if first word is SQL keyword
     │
     ├── YES → guard.py:is_safe()
     │              ├── UNSAFE → block, return error message
     │              └── SAFE → continue
     │
     └── NO → continue (plain English passes through)
     │
     ▼
3. _build_prompt_with_history()
     Prepends last N Q&A turns as context
     │
     ▼
4. agent.invoke({"input": enriched_prompt})
     LangChain + Groq handles everything
     │
     ▼
5. Extract answer from result["output"]
     │
     ▼
6. history.append({question, answer})
     cl.user_session.set("history", history)
     │
     ▼
7. cl.Message(content=answer).send()
     Rendered in browser
```

---

## 7. AI/Agent Architecture

### The Agent Loop

The SQL agent uses a **tool-calling** approach. The LLM is given a set of tools
(functions it can call) and iterates until it has a final answer:

```
┌─────────────────────────────────────────────────────────────┐
│                    AGENT LOOP                               │
│                                                             │
│  Input: enriched question prompt                            │
│     │                                                       │
│     ▼                                                       │
│  LLM: "I need to see what tables exist"                     │
│     │                                                       │
│     ▼ calls tool                                            │
│  sql_db_list_tables → "customers, orders, products, ..."    │
│     │                                                       │
│     ▼                                                       │
│  LLM: "I need the schema for orders and products"           │
│     │                                                       │
│     ▼ calls tool                                            │
│  sql_db_schema → CREATE TABLE orders (...), ...             │
│     │                                                       │
│     ▼                                                       │
│  LLM: generates SQL query                                   │
│     │                                                       │
│     ▼ calls tool                                            │
│  sql_db_query → [(row1), (row2), ...]                       │
│     │                                                       │
│     ▼                                                       │
│  LLM: formats rows into English answer                      │
│     │                                                       │
│     ▼                                                       │
│  Output: "The top 5 products were..."                       │
└─────────────────────────────────────────────────────────────┘
```

### Prompt Structure

Every call to Groq carries this structured prompt:

```
┌─────────────────────────────────────────────────┐
│  SYSTEM MESSAGE (AGENT_PREFIX)                  │
│  = _BUSINESS_RULES + SQL_PREFIX                 │
│                                                 │
│  _BUSINESS_RULES:                               │
│  - Never count cancelled orders                 │
│  - Date term definitions                        │
│  - Aggregation conventions                      │
│                                                 │
│  SQL_PREFIX (from LangChain):                   │
│  - You are an agent designed for SQL databases  │
│  - Always limit to {top_k} results              │
│  - Use {dialect} SQL syntax                     │
│  - Double-check queries before executing        │
├─────────────────────────────────────────────────┤
│  TOOL RESULTS (injected by LangChain)           │
│  - Schema info fetched in previous turns        │
├─────────────────────────────────────────────────┤
│  CONVERSATION HISTORY (injected by app.py)      │
│  Previous conversation:                         │
│    User: [previous question]                    │
│    Assistant: [previous answer]                 │
│  ...up to last 5 turns                          │
├─────────────────────────────────────────────────┤
│  CURRENT QUESTION                               │
│  Current question: [user's message]             │
└─────────────────────────────────────────────────┘
```

---

## 8. Security Architecture

### SQL Injection Prevention

**Layer 1 — LLM prompt**
The system prompt explicitly prohibits DML/DDL:
> "DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.)"

**Layer 2 — guard.py**
If user types raw SQL directly, `guard.py` validates it:
- Strips SQL comments (avoids `/* bypass */ DROP TABLE` tricks)
- Blocks any statement starting with a destructive keyword
- Requires the statement to be a SELECT (or CTE → SELECT)

**Layer 3 — PostgreSQL user permissions**
In a production deployment, the DB user should only have `SELECT` permissions.
The demo uses a full-permission user for simplicity.

### Secret Management

**What we avoid:**
```python
# NEVER do this
llm = ChatGroq(api_key="gsk_abc123...")  # hardcoded in code = checked into git
```

**What we do:**
```python
# Read from environment at runtime
api_key = SecretStr(os.environ["GROQ_API_KEY"])
```

The `.env` file:
- Lives only on the developer's machine
- Is listed in `.gitignore` — never committed
- `.env.example` shows structure without real values

`SecretStr` from pydantic:
- Wraps the string in an opaque type
- Prevents it from appearing in logs (`print(key)` → `**********`)
- Prevents accidental serialisation to JSON

---

## 9. Key Design Decisions

### Decision 1: Two containers instead of one

We could have run PostgreSQL and Chainlit in the same container. We didn't because:

- **Single responsibility:** each container does one thing
- **Independent lifecycle:** rebuild the app without touching the database
- **Data persistence:** the DB volume survives app rebuilds
- **Real-world patterns:** production deployments always separate app and DB

### Decision 2: tool-calling agent over ReAct

The default LangChain SQL agent type is `zero-shot-react-description` (ReAct).
We switched to `tool-calling`. Reasons:

| ReAct | tool-calling |
|---|---|
| Text-based: `Thought: ... Action: ...` | JSON function calls |
| Brittle text parser — fails if LLM deviates | Structured — no parsing needed |
| Llama models occasionally mis-format | Llama has native function-calling support |
| "Observation missing" errors in production | Reliable with Groq/Llama |

### Decision 3: Business rules in prompt, not in schema

We could have prevented cancelled-order counting by creating a database view.
We rejected this because:

- Views are schema-level solutions for a semantic problem
- Every new business rule would require a schema change and DB rebuild
- The prompt is the right place for "how to interpret this data"
- Prompts can be updated without touching the database at all

### Decision 4: uv over pip

`uv` is 10–100x faster than pip. For Docker builds, this matters — a clean install
of all dependencies takes ~7 seconds with `uv` vs ~90 seconds with pip. The Docker
layer caching means this only happens when `requirements.txt` changes, but the first
build (and any CI run) is significantly faster.

### Decision 5: History as plain text, not LangChain memory

LangChain has built-in memory classes (e.g. `ConversationBufferMemory`). We chose
not to use them:

- They add complexity and another abstraction layer
- They work differently across agent types
- Plain text prepended to the prompt is transparent and debuggable
- We control exactly how history is formatted and how much is included
