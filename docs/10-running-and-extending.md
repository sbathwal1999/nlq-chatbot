# 10 — Running & Extending the Project

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [First-Time Setup](#2-first-time-setup)
3. [Running with Docker (Recommended)](#3-running-with-docker-recommended)
4. [Running Locally with uv](#4-running-locally-with-uv)
5. [Common Commands Reference](#5-common-commands-reference)
6. [Debugging Guide](#6-debugging-guide)
7. [Connecting a Real Database](#7-connecting-a-real-database)
8. [Adding Business Rules](#8-adding-business-rules)
9. [Extending the Project](#9-extending-the-project)
10. [Deploying to Production](#10-deploying-to-production)

---

## 1. Prerequisites

### Required Software

| Tool | Version | Purpose | Install |
|---|---|---|---|
| Docker Desktop | Latest | Runs containers | https://docker.com/get-started |
| Docker Compose | v2+ (bundled with Desktop) | Orchestrates multi-container setup | (bundled) |
| uv | Latest | Python package manager (local dev) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Git | Any | Version control | OS package manager |

### Required Accounts

| Account | Purpose | Cost |
|---|---|---|
| Groq Console | API key for LLM inference | Free tier available |

Get your Groq API key at https://console.groq.com → API Keys → Create API Key.

### Checking Your Setup

```bash
docker --version           # Should show 24.x or later
docker compose version     # Should show v2.x
uv --version               # Should show 0.4.x or later
```

---

## 2. First-Time Setup

### 1. Clone the repository

```bash
git clone <repository-url>
cd nlq-chatbot
```

### 2. Create your .env file

```bash
cp .env.example .env
```

Open `.env` and fill in your values:

```bash
GROQ_API_KEY=gsk_your_actual_key_here   # from console.groq.com
POSTGRES_USER=retailuser
POSTGRES_PASSWORD=retailpass
POSTGRES_DB=retaildb
POSTGRES_HOST=localhost                  # override by Docker Compose for containers
POSTGRES_PORT=5432
MAX_ROWS=50
```

That is all. You do not need to install Python, pip, or any libraries manually.

---

## 3. Running with Docker (Recommended)

Docker Compose starts both the PostgreSQL database and the Chainlit app in one command.

### Start the application

```bash
docker compose up --build
```

- `--build` rebuilds the app image. Required on first run and after any code change.
- Docker pulls the base images (first run only — ~1-2 minutes)
- PostgreSQL starts and runs `init.sql` to create tables and seed data
- The app container waits for PostgreSQL to be healthy, then starts Chainlit
- Open http://localhost:8000 in your browser

You should see:

```
postgres-1  | database system is ready to accept connections
app-1       | 2024-11-15 10:32:00 - Your app is available at http://0.0.0.0:8000
```

### Start without rebuilding (after the first run)

```bash
docker compose up
```

### Start in detached mode (runs in background)

```bash
docker compose up -d
docker compose logs -f    # follow logs
```

### Stop the application

```bash
docker compose down        # stops containers, preserves data volume
docker compose down -v     # stops containers AND deletes data volume (fresh start)
```

### Rebuild after code changes

```bash
docker compose up --build
```

Only the app image is rebuilt (the postgres image never needs rebuilding unless
you change `init.sql`).

### Check container status

```bash
docker compose ps
```

---

## 4. Running Locally with uv

For faster development iteration (no Docker build step), you can run the app
directly on your machine. You still need Docker for PostgreSQL.

### 1. Start only the database

```bash
docker compose up postgres -d
```

### 2. Install dependencies

```bash
cd app
uv sync
```

`uv sync` reads `pyproject.toml` and installs all dependencies into a virtual
environment in `.venv/`.

### 3. Run the app

```bash
uv run --env-file ../.env chainlit run app.py --host 0.0.0.0 --port 8000
```

- `--env-file ../.env` loads the `.env` file from the project root
- Changes to `app.py`, `chain.py`, or `guard.py` take effect immediately
  (Chainlit auto-reloads on file change)

### 4. Make a code change and test

Edit any Python file. Chainlit detects the change and restarts automatically.
No rebuild needed.

### Local vs Docker — Key Difference

When running locally, `POSTGRES_HOST=localhost` connects to the PostgreSQL container
whose port 5432 is mapped to the host. When running in Docker, `POSTGRES_HOST=postgres`
uses the Docker internal network hostname. The `.env` file sets `localhost`; Docker
Compose overrides it to `postgres` via the `environment:` block.

---

## 5. Common Commands Reference

### Docker Compose

```bash
# Start everything (rebuild app image)
docker compose up --build

# Start everything (no rebuild)
docker compose up

# Start in background
docker compose up -d

# Stop everything (keep data)
docker compose down

# Stop everything (delete data volume — fresh database)
docker compose down -v

# View live logs
docker compose logs -f

# View logs for one service
docker compose logs -f app
docker compose logs -f postgres

# Rebuild and restart just the app (after code changes)
docker compose up --build app

# Open a shell inside the app container
docker compose exec app bash

# Open a PostgreSQL shell
docker compose exec postgres psql -U retailuser -d retaildb

# Check container status
docker compose ps
```

### PostgreSQL Queries (inside psql)

```sql
-- List all tables
\dt

-- Describe a table
\d customers
\d orders

-- Count rows
SELECT COUNT(*) FROM customers;
SELECT COUNT(*) FROM orders WHERE status = 'cancelled';

-- Check seed data
SELECT * FROM products;

-- Verify business rule — cancelled orders
SELECT o.status, p.name, oi.quantity
FROM order_items oi
JOIN orders o ON oi.order_id = o.id
JOIN products p ON oi.product_id = p.id
WHERE o.status = 'cancelled';

-- Exit psql
\q
```

### uv Commands

```bash
# Sync dependencies from pyproject.toml
uv sync

# Add a new dependency
uv add some-package

# Run with env file
uv run --env-file ../.env python script.py

# Run Chainlit
uv run --env-file ../.env chainlit run app.py --host 0.0.0.0 --port 8000
```

---

## 6. Debugging Guide

### Problem: Container won't start

```bash
docker compose logs app
```

Common causes:
- `GROQ_API_KEY` not set → `KeyError: 'GROQ_API_KEY'`
- `POSTGRES_PASSWORD` not set → `KeyError: 'POSTGRES_PASSWORD'`
- Port 8000 already in use → change the port in docker-compose.yml

### Problem: "Connection refused" to PostgreSQL

```bash
docker compose ps        # is postgres running?
docker compose logs postgres
```

Common causes:
- PostgreSQL still starting (wait a few seconds — healthcheck handles this)
- Wrong `POSTGRES_HOST` — must be `postgres` in Docker, `localhost` locally
- Wrong `POSTGRES_PORT` — default is 5432

### Problem: "Invalid API Key" (401 from Groq)

- Check the key in `.env` starts with `gsk_`
- After editing `.env`, recreate the container: `docker compose up --build app`
  (`docker compose restart` does NOT reload `.env`)
- Verify the key at https://console.groq.com

### Problem: Wrong answers (cancelled orders counted)

Enable verbose agent logging to see exactly what SQL is generated:

```python
# chain.py
agent = create_sql_agent(
    ...
    verbose=True,   # ← temporarily enable
)
```

Rebuild and check the logs:

```bash
docker compose up --build
docker compose logs -f app
```

Look for the SQL query in the logs. Verify it has `WHERE orders.status != 'cancelled'`.

### Problem: "observation from last action is missing"

This is a ReAct parsing error. Ensure `agent_type="tool-calling"` in `chain.py`.
The default agent type is `zero-shot-react-description` which is unreliable with Llama.

### Problem: Model not found (404 from Groq)

Groq periodically removes old models. Check the current model list at
https://console.groq.com/docs/models. Update `GROQ_MODEL` in `.env` and restart:

```bash
docker compose up --build app
```

### Inspecting the Database Directly

```bash
# Connect to PostgreSQL from the host (requires port 5432 to be mapped)
psql -h localhost -U retailuser -d retaildb
# or
docker compose exec postgres psql -U retailuser -d retaildb
```

Use DBeaver, TablePlus, or any SQL client with:
- Host: `localhost`
- Port: `5432`
- User: `retailuser`
- Password: `retailpass`
- Database: `retaildb`

---

## 7. Connecting a Real Database

The demo uses a toy retail schema. To connect to a real PostgreSQL database:

### Step 1 — Update environment variables

```bash
# .env
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_db_password
POSTGRES_DB=your_database_name
POSTGRES_HOST=your-db-host.example.com
POSTGRES_PORT=5432
```

### Step 2 — Remove or replace init.sql

The `postgres/init.sql` is only used for the demo database container. If you are
connecting to an external database, the `postgres` container is not needed at all.

Update `docker-compose.yml` to remove the postgres service and its dependency:

```yaml
# docker-compose.yml — simplified for external DB
services:
  app:
    build: ./app
    ports:
      - "8000:8000"
    env_file:
      - .env
```

### Step 3 — Update business rules

The `_BUSINESS_RULES` in `chain.py` are written for the demo schema. For a real
database, rewrite them to reflect your actual business logic:

```python
_BUSINESS_RULES = """You are a helpful data analyst for Acme Corp.

Business rules:
- Fiscal year runs from April 1 to March 31 (not calendar year).
- 'revenue' means net_revenue, not gross_revenue.
- Exclude test accounts (accounts with is_test = true).
- 'active customers' means last_login within the past 90 days.
"""
```

### Step 4 — Consider schema size

If your database has many tables and columns, the schema tool may return too much
context for the LLM. You can limit which tables the agent can see:

```python
db = SQLDatabase.from_uri(db_url, include_tables=["sales", "customers", "products"])
```

This restricts the agent to only those tables, reducing context size and improving
accuracy.

---

## 8. Adding Business Rules

Business rules are the most common customisation. They live in `chain.py`:

```python
_BUSINESS_RULES = """You are a helpful data analyst assistant for a retail company.

Business rules — apply these to EVERY query without exception:
- NEVER include orders with status = 'cancelled' when calculating sales...
"""
```

### Examples of Rules to Add

**New date definition:**
```python
- "YTD" means from January 1 of the current year to today.
  Use: WHERE ordered_at >= DATE_TRUNC('year', NOW())
```

**New status filter:**
```python
- "active products" means products with stock_quantity > 0.
  Always add: WHERE stock_quantity > 0 unless asked about all products.
```

**Metric definition:**
```python
- "conversion rate" means orders / sessions * 100 (as percentage).
  Query from the web_events table joined with orders on session_id.
```

**Naming clarification:**
```python
- The "North" region in the database is stored as 'north' (lowercase).
  Always use lowercase for region filters.
```

### After Adding Rules

Rebuild the container to apply the new rules:

```bash
docker compose up --build app
```

The business rules are baked into the system prompt at startup, not at query time.

---

## 9. Extending the Project

### Add a New Table

1. Add the table to `postgres/init.sql`:

```sql
CREATE TABLE returns (
    id          SERIAL PRIMARY KEY,
    order_id    INTEGER NOT NULL REFERENCES orders(id),
    reason      TEXT NOT NULL,
    returned_at TIMESTAMP NOT NULL DEFAULT NOW()
);

INSERT INTO returns (order_id, reason, returned_at) VALUES
    (1, 'defective', NOW() - INTERVAL '5 days'),
    (3, 'wrong item', NOW() - INTERVAL '2 days');
```

2. Rebuild the database volume:

```bash
docker compose down -v    # ← deletes data, triggers re-seed
docker compose up --build
```

3. Add a business rule for the new table if needed:

```python
- "return rate" means the number of returns divided by total delivered orders.
  Join the returns table on order_id.
```

The agent discovers new tables automatically via `sql_db_list_tables` — no code
changes needed beyond the schema update and any new business rules.

### Add Streaming Responses

By default, the agent returns the complete answer at once. For a better UX on long
answers, you can stream tokens as they are generated:

```python
# chain.py — switch to streaming
llm = ChatGroq(model=model, temperature=0, api_key=SecretStr(...), streaming=True)
```

```python
# app.py — use cl.Message with streaming
msg = cl.Message(content="")
await msg.send()
async for chunk in agent.astream({"input": prompt}):
    if "output" in chunk:
        await msg.stream_token(chunk["output"])
await msg.update()
```

Note: streaming with LangChain agents requires using `astream()` instead of `invoke()`,
and Chainlit's `stream_token()` API.

### Add a New LLM Provider

To switch from Groq to OpenAI:

```bash
# Add the package
uv add langchain-openai
```

```python
# chain.py
from langchain_openai import ChatOpenAI  # replaces ChatGroq

llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    api_key=SecretStr(os.environ["OPENAI_API_KEY"]),
)
```

Update `.env`:
```bash
OPENAI_API_KEY=sk-your-key-here
```

The rest of the code is unchanged — LangChain's `create_sql_agent` works with any
`ChatModel`-compatible LLM.

### Add Query History Persistence

Currently, conversation history is lost on page refresh. To persist it across
sessions, store it in the database:

```sql
-- Add to init.sql
CREATE TABLE conversation_history (
    id         SERIAL PRIMARY KEY,
    session_id TEXT NOT NULL,
    question   TEXT NOT NULL,
    answer     TEXT NOT NULL,
    asked_at   TIMESTAMP DEFAULT NOW()
);
```

```python
# app.py — save and load history from PostgreSQL
# (requires adding a db connection to app.py or a separate service)
```

This is a non-trivial extension that requires a separate database connection in
`app.py` and a session identifier. Chainlit's `cl.context.session.id` provides
a stable session ID per connection.

---

## 10. Deploying to Production

The demo runs on localhost. For a real internal deployment, additional steps are needed.

### Minimum Production Changes

1. **Read-only database user**
```sql
CREATE USER chatbot_readonly WITH PASSWORD 'secure_random_password';
GRANT CONNECT ON DATABASE retaildb TO chatbot_readonly;
GRANT USAGE ON SCHEMA public TO chatbot_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO chatbot_readonly;
```

2. **Remove public PostgreSQL port**
```yaml
# docker-compose.yml — remove this for production
# ports:
#   - "5432:5432"   ← never expose DB publicly
```

3. **Add HTTPS**

Deploy behind a reverse proxy (nginx, Traefik, Caddy) with TLS certificates.
Chainlit itself can serve HTTPS with `--ssl-certfile` and `--ssl-keyfile` flags.

4. **Add authentication**

Chainlit supports password-based auth and OAuth. Example with password auth:

```python
# app.py
@cl.password_auth_callback
def auth_callback(username: str, password: str) -> cl.User | None:
    if username == "admin" and password == os.environ["ADMIN_PASSWORD"]:
        return cl.User(identifier="admin")
    return None
```

5. **Use a secrets manager**

Instead of `.env` files, use AWS Secrets Manager, HashiCorp Vault, or Kubernetes
secrets to inject credentials into the container at runtime.

### Cloud Deployment Options

| Platform | Approach |
|---|---|
| AWS EC2 | Run docker-compose on a VM, put behind ALB |
| AWS ECS | Run as ECS task, use RDS for PostgreSQL |
| Railway.app | Push to GitHub, Railway builds and deploys automatically |
| Render.com | Deploy as Docker service, managed PostgreSQL available |
| Fly.io | `flyctl deploy` — good free tier for small internal tools |

For an internal tool serving <50 users, a single small VM (2 CPU, 2GB RAM) running
Docker Compose is sufficient and simple to operate.
