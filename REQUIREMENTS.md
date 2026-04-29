# NLQ Chatbot — Project Requirements

---

## 1. Objective

Build a natural language query (NLQ) chatbot that allows non-technical users to query a PostgreSQL database by typing plain English questions and get back human-readable answers — without writing any SQL.

---

## 2. Use Case

**Scenario:** A business analyst at a retail company wants to answer questions like:

- *"What were the top 5 products sold last month?"*
- *"How many orders are pending in the North region?"*
- *"Show me customers who haven't ordered in 90 days"*

Currently they raise a ticket to the data team, wait 2 days, and get a CSV. With this system, they type the question and get the answer in seconds — directly in a chat interface.

---

## 3. What We Are Building

A containerised, self-hostable chat application where:

1. User types a natural language question in a chat UI
2. The system translates it to SQL using an LLM
3. SQL is executed against a PostgreSQL database
4. The result is returned as a readable answer in chat

Everything — database, app, UI — runs via Docker Compose. One command to spin up, one command to tear down.

---

## 4. Functional Requirements

- User can type any question about the data in plain English
- System generates valid SQL from the question
- SQL is executed on the connected PostgreSQL instance
- Result is shown as a natural language answer in the chat
- Chat history is maintained within a session
- Invalid or unsafe queries (DROP, DELETE, UPDATE) are blocked before execution

---

## 5. Non-Functional Requirements

- Fully containerised — no manual environment setup
- All services declared in a single `docker-compose.yml`
- Environment-based config (no hardcoded secrets)
- Free and open-source tooling only
- Reproducible setup — clone → configure `.env` → `docker compose up`

---

## 6. Solution Architecture

```
User
 │
 ▼
Chainlit (Chat UI + App Logic)         ← Python, port 8000
 │
 ├──► Groq API (LLM, via LangChain)    ← External, free tier
 │         │
 │    tool-calling agent: inspect schema →
 │    generate + execute SQL →
 │    self-correct → plain-English answer
 │
 ├──► PostgreSQL                        ← Docker container, port 5432
 │         │
 │    Returns rows
 │
 └──► Streams answer back to user
```

---

## 7. Tools & Justification

| Layer | Tool | Why |
|---|---|---|
| Chat UI + Backend | **Chainlit** | Single Python file, no frontend code, built for LLM apps |
| NLQ → SQL | **LangChain `create_sql_agent`** | Tool-calling agent: introspects schema, generates + executes SQL, self-corrects, answers |
| LLM | **Groq API (Llama 3.3 70B Versatile)** | Free tier, fast inference, strong instruction following and SQL generation |
| Database | **PostgreSQL** | Production-grade, widely used, LangChain has native support |
| Containerisation | **Docker + Docker Compose** | Single-command deployment of all services |
| Config management | **`.env` file + `uv run --env-file`** | No hardcoded secrets, no extra dependency — `uv` injects env vars natively; Docker Compose reads `.env` directly |
| Dependency management | **`uv` + `pyproject.toml`** + `requirements.txt` | `uv` for fast installs via `pyproject.toml`; `requirements.txt` retained for compatibility |

---

## 8. Project Structure (Git Repo)

```
nlq-chatbot/
├── app/
│   ├── app.py                  # Chainlit app — main entrypoint
│   ├── chain.py                # LangChain SQL agent setup
│   ├── guard.py                # SQL safety check (blocks DDL/DML)
│   ├── pyproject.toml          # Primary dependency definition (uv)
│   └── requirements.txt        # Exported for Docker/pip compatibility
├── postgres/
│   ├── init.sql                # Schema + seed data for demo
│   └── Dockerfile
├── docker-compose.yml          # Orchestrates all services
├── .env.example                # Template for secrets
├── .gitignore                  # Excludes .env, __pycache__, etc.
└── README.md                   # Setup + usage instructions
```

---

## 9. Deployment Flow

**Docker (recommended):**
```
git clone <repo>
cp .env.example .env                  # fill in GROQ_API_KEY + DB creds
docker compose up --build             # spins up postgres + chainlit app
open http://localhost:8000            # chat UI ready
```

**Local development:**
```
cd app
uv pip install -r requirements.txt    # install dependencies
uv run --env-file ../.env chainlit run app.py
```

No Kubernetes, no cloud setup, no manual installs. Runs on any machine with Docker.

---

## 10. Out of Scope (v1)

- User authentication
- Multi-database support
- Query history persistence across sessions
- Fine-tuning the LLM
- Cloud deployment (AWS/GCP/Azure)

---