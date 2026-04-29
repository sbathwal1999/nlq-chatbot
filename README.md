# NLQ Chatbot

Ask plain-English questions about your PostgreSQL data. No SQL required.

## Quick start

```bash
git clone <repo>
cd nlq-chatbot

cp .env.example .env
# Edit .env — add your GROQ_API_KEY and set DB credentials

docker compose up --build
```

Open **http://localhost:8000** and start asking questions.

## Example questions

- *What were the top 5 products sold last month?*
- *How many orders are pending in the North region?*
- *Show me customers who haven't ordered in 90 days*

Follow-up questions work too — the chatbot remembers the last 5 turns:

- *What about yesterday?*
- *Which of those had the highest revenue?*

## Project structure

```
nlq-chatbot/
├── app/
│   ├── app.py            # Chainlit entrypoint — chat UI + message handling
│   ├── chain.py          # LangChain SQL agent setup
│   ├── guard.py          # Blocks destructive SQL (DROP, DELETE, etc.)
│   ├── pyproject.toml    # Dependencies (uv)
│   ├── requirements.txt  # Fallback for pip
│   └── Dockerfile
├── postgres/
│   ├── init.sql          # Demo schema + seed data (retail dataset)
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── .gitignore
```

## Local development (without Docker)

```bash
cd app
uv pip install -r requirements.txt   # or: pip install -r requirements.txt

uv run --env-file ../.env chainlit run app.py
```

## Tear down

```bash
docker compose down          # stops containers
docker compose down -v       # also deletes the database volume
```
