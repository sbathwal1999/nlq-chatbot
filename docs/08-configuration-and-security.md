# 08 — Configuration & Security

## Table of Contents

1. [Why Configuration Matters](#1-why-configuration-matters)
2. [Environment Variables](#2-environment-variables)
3. [The .env File Pattern](#3-the-env-file-pattern)
4. [How Variables Flow Into the App](#4-how-variables-flow-into-the-app)
5. [SecretStr — Safe Secret Handling](#5-secretstr--safe-secret-handling)
6. [SQL Injection — The Threat](#6-sql-injection--the-threat)
7. [Our Three-Layer Defence](#7-our-three-layer-defence)
8. [What We Don't Do (and Why)](#8-what-we-dont-do-and-why)
9. [Production Security Checklist](#9-production-security-checklist)

---

## 1. Why Configuration Matters

A common mistake in early-stage projects is hardcoding values that should be
configurable:

```python
# DON'T DO THIS
llm = ChatGroq(api_key="gsk_abc123xyz...")
db_url = "postgresql://admin:password@localhost:5432/mydb"
```

This approach has serious problems:

1. **Secrets in git** — the API key is visible to anyone with repo access, forever
2. **Not portable** — the database URL won't work on another developer's machine
3. **Not environment-aware** — you need different credentials for dev, staging, prod
4. **Can't rotate secrets** — changing a credential requires changing and redeploying code

The solution is to separate configuration from code.

---

## 2. Environment Variables

**Environment variables** are key-value pairs set in the process environment —
outside your code. Every process on any operating system has an environment.

```bash
# Setting environment variables in a shell
export GROQ_API_KEY=gsk_abc123
export POSTGRES_USER=retailuser

# Reading them in Python
import os
api_key = os.environ["GROQ_API_KEY"]     # raises KeyError if missing
db_user = os.environ.get("POSTGRES_USER", "retailuser")  # default if missing
```

### Why Environment Variables?

| Property | Benefit |
|---|---|
| Outside the codebase | Cannot be accidentally committed to git |
| Per-environment | Dev, staging, and prod use different values |
| Easy to rotate | Change the value without touching code |
| Standard convention | All cloud platforms and CI systems support them |
| Process-scoped | One process can't read another's env vars |

### os.environ vs os.environ.get

```python
# Raises KeyError if GROQ_API_KEY is not set — fail-fast behaviour
api_key = os.environ["GROQ_API_KEY"]

# Returns "llama-3.3-70b-versatile" if GROQ_MODEL is not set — optional config
model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
```

Use `os.environ["KEY"]` for required variables (you want the app to crash clearly
if they are missing). Use `os.environ.get("KEY", default)` for optional configuration.

---

## 3. The .env File Pattern

Typing `export GROQ_API_KEY=...` before every dev session is tedious. The `.env`
file collects all environment variables in one place for local development.

### .env (not committed to git)

```bash
# Groq API
GROQ_API_KEY=gsk_your_actual_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# PostgreSQL
POSTGRES_USER=retailuser
POSTGRES_PASSWORD=retailpass
POSTGRES_DB=retaildb
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Application
MAX_ROWS=50
```

### .env.example (committed to git)

```bash
# Groq API — get your key from https://console.groq.com
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=llama-3.3-70b-versatile

# PostgreSQL credentials
POSTGRES_USER=retailuser
POSTGRES_PASSWORD=retailpass
POSTGRES_DB=retaildb
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

# Application settings
MAX_ROWS=50
```

The `.env.example` is a template — it shows what variables are needed without
exposing real values. New developers copy it and fill in their own credentials.

### .gitignore

```gitignore
.env
```

This single line prevents `.env` from ever being committed. Git will not track it,
will not show it in `git status`, and will not include it in diffs.

### Loading .env — Two Approaches

**Approach 1: uv (local development)**
```bash
uv run --env-file .env chainlit run app.py --host 0.0.0.0 --port 8000
```
`uv run --env-file .env` loads the `.env` file into the process environment before
running the command. No Python library needed — it is handled by the runner.

**Approach 2: Docker Compose (containerised)**
```yaml
# docker-compose.yml
app:
  environment:
    POSTGRES_USER:     ${POSTGRES_USER}      # read from .env automatically
    POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    POSTGRES_HOST:     postgres              # override: Docker service name, not localhost
    GROQ_API_KEY:      ${GROQ_API_KEY}
```
Docker Compose v2 reads `.env` from the project root automatically — no `env_file:`
directive is needed. Variables are referenced with `${VAR}` syntax. Individual
`environment:` entries override `.env` values — used here to set
`POSTGRES_HOST=postgres` (the Docker service name) instead of `localhost`.

---

## 4. How Variables Flow Into the App

```
.env file
    │
    ├── uv run --env-file .env        (local dev)
    │       └── process environment
    │               └── os.environ["GROQ_API_KEY"]
    │
    └── docker-compose env_file:      (Docker)
            └── container environment
                    └── os.environ["GROQ_API_KEY"]
```

In both cases, the Python code reads from `os.environ`. The source of the variable
(`.env` via uv, or docker-compose) is irrelevant to the application code.

### Variable Reference

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `GROQ_API_KEY` | Yes | — | Groq API authentication |
| `GROQ_MODEL` | No | `llama-3.3-70b-versatile` | Which Groq model to use |
| `POSTGRES_USER` | Yes | — | Database username |
| `POSTGRES_PASSWORD` | Yes | — | Database password |
| `POSTGRES_DB` | Yes | — | Database name |
| `POSTGRES_HOST` | No | `localhost` | Database hostname |
| `POSTGRES_PORT` | No | `5432` | Database port |
| `MAX_ROWS` | No | `50` | Maximum rows per query result |

---

## 5. SecretStr — Safe Secret Handling

### The Problem with Plain Strings

API keys stored as plain Python strings are invisible to type checkers but are
easy to accidentally expose:

```python
api_key = "gsk_abc123"  # plain string

# Accidentally logged
logger.info(f"Connecting with key: {api_key}")  # → "Connecting with key: gsk_abc123"

# Accidentally serialised
config = {"model": "llama", "api_key": api_key}
print(json.dumps(config))  # → {"model": "llama", "api_key": "gsk_abc123"}
```

### SecretStr

Pydantic's `SecretStr` wraps a string in an opaque type that hides its value:

```python
from pydantic import SecretStr

api_key = SecretStr("gsk_abc123")

# Printing hides the value
print(api_key)           # → **********
print(repr(api_key))     # → SecretStr('**********')

# Logging hides the value
logger.info(f"Key: {api_key}")  # → "Key: **********"

# JSON serialisation hides the value
# (prevents accidental exposure in structured logs)

# To get the actual value (only where needed)
raw_key = api_key.get_secret_value()  # → "gsk_abc123"
```

### How We Use It

```python
from pydantic import SecretStr

llm = ChatGroq(
    model=model,
    temperature=0,
    api_key=SecretStr(os.environ["GROQ_API_KEY"]),
)
```

`ChatGroq` accepts `SecretStr` as its `api_key` parameter. It calls
`.get_secret_value()` internally when it actually needs the key for an HTTP request.

The key is never exposed as a plain string in our code after this point.

---

## 6. SQL Injection — The Threat

**SQL injection** is one of the most common and dangerous web vulnerabilities.
It occurs when user input is embedded directly into a SQL query without sanitisation.

### A Classic Example

```python
# VULNERABLE code (not ours — for illustration)
user_input = request.get("name")
query = f"SELECT * FROM customers WHERE name = '{user_input}'"
db.execute(query)
```

If `user_input` is `' OR '1'='1`, the query becomes:
```sql
SELECT * FROM customers WHERE name = '' OR '1'='1'
```
This returns ALL customers — the `OR '1'='1'` is always true.

Worse: if `user_input` is `'; DROP TABLE customers; --`:
```sql
SELECT * FROM customers WHERE name = ''; DROP TABLE customers; --'
```
This deletes the entire customers table.

### Why Our Architecture is Exposed

In a traditional web app, SQL injection attacks user-supplied string values. In our
system, the user's natural language question is converted to SQL by an LLM. The risk
is different:

1. **Direct SQL input** — a user could type raw SQL directly into the chat box
2. **Prompt injection** — a user could craft a question that manipulates the LLM into
   generating destructive SQL

Both attack surfaces require defence.

---

## 7. Our Three-Layer Defence

### Layer 1 — LLM System Prompt

The `AGENT_PREFIX` explicitly instructs the LLM:

```
(from SQL_PREFIX, which is part of AGENT_PREFIX)
"DO NOT make any DML statements (INSERT, UPDATE, DELETE, DROP etc.)
 to the database."
```

This is the first and most important layer. A well-instructed LLM will not generate
destructive SQL. However, it is not infallible — prompt injection or model confusion
could in theory bypass it.

### Layer 2 — guard.py

If a user types raw SQL directly, `guard.py` validates it before it reaches the agent:

```python
# app.py
if _looks_like_sql(question) and not is_safe(question):
    await cl.Message(content="Sorry, I can only answer read-only questions.").send()
    return
```

`_looks_like_sql()` is a cheap pre-filter. It checks if the first word is a SQL
keyword — if not, there is no need to run the full guard.

`is_safe()` in guard.py:
1. Strips SQL comments (`--` and `/* */`) to prevent comment-based bypasses
2. Rejects any statement starting with a destructive keyword
3. Requires the statement body to be a SELECT (after stripping any CTE prefix)

### Layer 3 — Database User Permissions

In a production deployment, the database user the application connects as should
only have `SELECT` privileges:

```sql
-- Production setup (not implemented in this demo)
CREATE USER chatbot_readonly WITH PASSWORD 'secure_password';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO chatbot_readonly;
```

With this in place, even if an attacker bypassed layers 1 and 2 and injected a
`DELETE` statement, the database would reject it with a permission error.

Our demo uses a full-permission user for simplicity. A real deployment must use
a read-only user.

### Why Three Layers?

**Defence in depth** — no single security control is perfect. Each layer has weaknesses:

| Layer | Weakness |
|---|---|
| Prompt instructions | LLM can be confused or manipulated |
| guard.py | Only covers direct SQL input, not LLM-generated SQL |
| DB permissions | Requires production infrastructure setup |

The layers compensate for each other's weaknesses.

---

## 8. What We Don't Do (and Why)

### No Input Sanitisation for Natural Language

We do not attempt to sanitise or validate plain English questions. This would be
counterproductive — there is no reliable way to distinguish a malicious question
from a legitimate one based on text alone. The LLM is much better at this than regex.

### No Parameterised Queries (Directly)

In traditional web apps, the gold standard against SQL injection is parameterised
queries:

```python
# Parameterised — safe
cursor.execute("SELECT * FROM users WHERE name = %s", (user_input,))
```

In our system, the SQL is generated by the LLM and executed by LangChain's
`sql_db_query` tool. We do not construct SQL from user input directly — we don't
have the opportunity to parameterise it. The LLM generates complete SQL strings.

This is why the prompt constraint and database permissions are our primary defences
for LLM-generated SQL.

### No Authentication

The demo has no user authentication. Anyone who can reach `http://localhost:8000`
can use the chatbot. For an internal deployment, this would typically be behind:
- VPN or network-level access control
- SSO via the company's identity provider
- Chainlit's built-in authentication support

---

## 9. Production Security Checklist

If deploying this system for real use, these steps are required:

```
[ ] Use a read-only database user with only SELECT privileges
[ ] Rotate all credentials before deployment (assume dev keys are compromised)
[ ] Store secrets in a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)
    rather than .env files on disk
[ ] Enable TLS/HTTPS for the web interface (Chainlit supports this)
[ ] Put the application behind authentication (VPN, SSO, or Chainlit auth)
[ ] Set MAX_ROWS to a conservative limit to prevent data exfiltration via large dumps
[ ] Monitor and log query patterns for anomaly detection
[ ] Never expose the PostgreSQL port (5432) publicly — remove the ports mapping
    from docker-compose.yml in production
[ ] Use Docker secrets or Kubernetes secrets instead of environment variables
    for credential management in orchestrated deployments
```
