# NLQ Chatbot — Study Guide Index

A comprehensive learning resource covering every concept, tool, and decision
behind the NLQ Chatbot project. Each document is self-contained and written
to be read independently or as part of the full series.

---

## Documents

| # | Document | What you will learn |
|---|---|---|
| 01 | [Business Context & Problem Statement](01-business-context.md) | Why this project exists, the business problem, the solution approach |
| 02 | [System Architecture](02-architecture.md) | Full architecture, component relationships, design decisions |
| 03 | [Docker & Containerisation](03-docker.md) | What Docker is, containers, images, Docker Compose, networking, volumes |
| 04 | [Large Language Models & Prompting](04-llms-and-prompting.md) | LLMs, how they work, prompt engineering, all prompting techniques |
| 05 | [LangChain & SQL Agents](05-langchain-and-agents.md) | LangChain framework, agents, tool-calling, chains vs agents |
| 06 | [PostgreSQL & Data Modelling](06-postgresql-and-data.md) | Relational databases, schema design, SQL fundamentals, the retail data model |
| 07 | [Python Application Layer](07-python-app.md) | Chainlit, app structure, session management, async Python |
| 08 | [Configuration & Security](08-configuration-and-security.md) | Environment variables, secrets management, SQL injection prevention |
| 09 | [End-to-End Request Flow](09-request-flow.md) | Step-by-step trace of every user message through the full stack |
| 10 | [Running & Extending the Project](10-running-and-extending.md) | Setup, commands, debugging, how to extend for real use |
| 11 | [Advanced NLQ — Research & Production](11-advanced-nlq.md) | Research benchmarks, 7 improvement techniques, production DB guide, improvement roadmap |

---

## How to Use This Guide

**If you are new to everything:** Read documents 01 → 10 in order.

**If you know some parts:** Jump to the document that covers the unfamiliar topic.
Each document explains concepts from scratch.

**If you are building something similar:** Focus on 02 (architecture), 04 (LLMs),
05 (LangChain), and 10 (extending).

**If you want to improve accuracy or go to production:** Read document 11 (Advanced NLQ)
for research-backed techniques, production database guidance, and a prioritised roadmap.

---

## Project Structure Reference

```
nlq-chatbot/
├── app/
│   ├── app.py              ← Covered in doc 07
│   ├── chain.py            ← Covered in doc 05
│   ├── guard.py            ← Covered in doc 08
│   ├── pyproject.toml      ← Covered in doc 10
│   ├── requirements.txt    ← Covered in doc 10
│   └── Dockerfile          ← Covered in doc 03
├── postgres/
│   ├── init.sql            ← Covered in doc 06
│   └── Dockerfile          ← Covered in doc 03
├── docker-compose.yml      ← Covered in doc 03
├── .env.example            ← Covered in doc 08
├── docs/                   ← You are here
├── TUTORIAL.md             ← Concise end-to-end overview
└── REQUIREMENTS.md         ← Project specification
```
