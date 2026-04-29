# 01 — Business Context & Problem Statement

## Table of Contents

1. [The Business Environment](#1-the-business-environment)
2. [The Problem](#2-the-problem)
3. [Why Existing Solutions Fall Short](#3-why-existing-solutions-fall-short)
4. [The Opportunity](#4-the-opportunity)
5. [Our Solution Approach](#5-our-solution-approach)
6. [What Success Looks Like](#6-what-success-looks-like)
7. [Scope & Boundaries](#7-scope--boundaries)

---

## 1. The Business Environment

### The Modern Data Company

Every business today generates data. A retail company like our scenario tracks:

- **Customers** — who they are, where they are, when they joined
- **Products** — what is sold, at what price, in which category
- **Orders** — who bought what, when, in what quantity
- **Fulfilment** — order status, shipping, cancellations

This data lives in a **relational database** — typically PostgreSQL, MySQL, or a
cloud equivalent. It is the single source of truth for the business.

### The Two Worlds Problem

Inside most companies there are two groups of people who both need access to this data:

**Group A — Technical users (engineers, data analysts)**
- Can write SQL queries
- Have direct database access
- Represent maybe 5–10% of the company

**Group B — Business users (managers, analysts, marketing, finance)**
- Need data to make decisions every day
- Cannot write SQL
- Represent the other 90–95% of the company

These two groups exist in completely separate worlds. The result is a bottleneck.

---

## 2. The Problem

### The Current Workflow

Here is what happens today when a business analyst needs a data answer:

```
Day 1, 9am
  Analyst: "I need to know the top 5 products sold last month"
  → Opens ticketing system
  → Writes a support ticket with their question
  → Assigns it to the data team

Day 1-2
  Data team: sees ticket in their queue
  → Prioritises it against other work
  → Eventually finds time to write the SQL query
  → Runs the query
  → Exports to CSV
  → Emails the CSV back

Day 2-3
  Analyst: receives the CSV
  → Opens in Excel
  → Tries to understand the column names
  → Realises they actually wanted it broken down by region too
  → Creates another ticket...
```

**Total time: 2–3 days for a question that takes 3 seconds to answer with the right tools.**

### The Human Cost

This workflow has real costs beyond just time:

| Cost | Impact |
|---|---|
| Delayed decisions | Marketing campaigns run on stale data |
| Data team bottleneck | Engineers spend time on mechanical queries instead of building |
| Analyst frustration | People lose trust in data processes |
| Ticket backlog | Simple questions compete with complex engineering work |
| Stale insights | A report about last month's sales loses value every day it waits |

### The Root Cause

The root cause is not that business analysts are unintelligent — it is that
**SQL is a technical language that requires training and practice**, and asking
every employee to learn it is not a realistic solution.

SQL for a simple question looks like this:

```sql
SELECT
    p.name AS product_name,
    SUM(oi.quantity) AS total_units_sold
FROM order_items oi
INNER JOIN orders o ON oi.order_id = o.id
INNER JOIN products p ON oi.product_id = p.id
WHERE
    o.ordered_at >= NOW() - INTERVAL '30 days'
    AND o.status != 'cancelled'
GROUP BY p.name
ORDER BY total_units_sold DESC
LIMIT 5;
```

Even this "simple" query requires knowing:
- JOIN syntax and when to use INNER vs LEFT
- Aggregate functions (SUM, COUNT, AVG)
- GROUP BY behaviour
- WHERE clause filtering
- Date arithmetic with intervals
- Business logic (excluding cancelled orders)

This is not trivial knowledge.

---

## 3. Why Existing Solutions Fall Short

### Dashboards (Tableau, Power BI, Looker)

Dashboards are visual tools that display pre-built charts and metrics.

**What they do well:**
- Beautiful visualisations
- Fast to view known metrics
- Non-technical users can consume them

**Why they fail here:**
- Dashboards answer **predetermined questions** — the ones whoever built the dashboard
  thought to ask
- Any new question requires a developer to add a new chart
- The bottleneck still exists — it just moved from "write a query" to "update the dashboard"
- Dashboards are for monitoring, not exploration

### Self-Service BI Tools

Some tools (Metabase, Redash) let non-technical users build queries visually.

**What they do well:**
- No SQL required for simple queries
- Some users can be self-sufficient for basic questions

**Why they fail here:**
- Multi-table questions still require understanding of table relationships
- Users need to know what tables/columns to look at
- Complex aggregations and date logic are still confusing
- Requires training and onboarding for each new user

### Asking a Data Analyst Colleague

**What it does well:**
- Flexible — they understand context
- Can ask clarifying questions

**Why it fails here:**
- The analyst's time is the most expensive resource
- Doesn't scale as the company grows
- Creates dependency and single points of failure

---

## 4. The Opportunity

### The NLQ Moment

**Natural Language Query (NLQ)** is the idea that users should be able to ask questions
about data in the same way they would ask a human colleague — in plain English.

The technology to make this work reliably has arrived in the form of **Large Language
Models (LLMs)** — AI systems trained on vast amounts of text and code that can:

1. Understand the intent behind a plain English question
2. Understand the structure of a database from its schema
3. Generate syntactically correct, semantically appropriate SQL
4. Translate raw database results back into a human-readable answer

### Why Now?

NLQ has been attempted for decades. It only works reliably now because:

| Earlier attempts | Modern LLMs |
|---|---|
| Rule-based parsing — broke on anything unexpected | Learned patterns from billions of examples |
| Required extensive manual configuration per database | Understand schema from a description |
| Could only handle simple queries | Handle complex joins, aggregations, CTEs |
| Poor at understanding business context | Can follow natural language business rules |

---

## 5. Our Solution Approach

### The Core Idea

Place an AI layer between the business user and the database. The AI:
1. Understands the question in plain English
2. Knows the database schema
3. Generates the correct SQL
4. Executes it
5. Translates the result back to English

```
Before:
  Business User → [2 days] → Data Engineer → Database

After:
  Business User → [5 seconds] → AI Layer → Database
```

### The Three Layers

**Layer 1 — Interface**
A web-based chat UI that any employee can use without training.
Built with Chainlit — a Python framework designed for LLM chat applications.

**Layer 2 — Intelligence**
A LangChain SQL agent powered by Llama 3.3 70B via Groq.
The agent understands the question, knows the schema, generates SQL, executes it,
and formats the answer.

**Layer 3 — Data**
A PostgreSQL database with a retail schema. In a real deployment this would be
the company's actual database.

### Design Principles

**1. No installation for users**
The entire system runs in Docker. One command to start, accessible via browser.

**2. No hardcoded secrets**
All credentials are in environment variables. The repo itself contains no secrets.

**3. Guardrails by default**
The system only allows read queries. DROP, DELETE, UPDATE are blocked at multiple
layers — the LLM prompt and the SQL guard.

**4. Honest about its scope**
The system is not a replacement for data engineering. It answers analytical questions.
Complex transformations, data modelling, and pipeline work still require engineers.

---

## 6. What Success Looks Like

### For the Business User

- Types a question in plain English
- Gets a correct answer in under 10 seconds
- Can ask follow-up questions ("What about last week?" / "Which region was highest?")
- Does not need to understand SQL, database schemas, or data models
- Gets answers that respect business rules (e.g. cancelled orders not counted as sales)

### For the Data Team

- No longer receives tickets for simple data questions
- Can focus on complex engineering work
- Has confidence that the system applies correct business logic

### Example Interactions That Should Work

| User asks | Expected behaviour |
|---|---|
| "Top 5 products last month?" | Lists products by units sold, excludes cancelled orders |
| "How many pending orders in North?" | Counts orders filtered by status and region |
| "Show me inactive customers" | Identifies customers with no orders in last 90 days |
| "What about yesterday?" | Understands context from previous question |
| "Which product had most revenue?" | Calculates quantity × unit_price, not just count |

---

## 7. Scope & Boundaries

### In Scope (v1)

- Natural language queries against a single PostgreSQL database
- Read-only queries (no data modification)
- Session-scoped conversation history (follow-up questions within one session)
- Containerised deployment via Docker Compose

### Out of Scope (v1)

| Feature | Why deferred |
|---|---|
| User authentication | Adds significant complexity; not needed for internal demo |
| Multiple database support | Different schemas need different business rules |
| Persistent query history | Requires a database or file store for history |
| Fine-tuning the LLM | Expensive; prompt engineering is sufficient for v1 |
| Cloud deployment | Adds infrastructure complexity; local Docker is sufficient to validate |
| Data visualisation | Charts and graphs; text answers sufficient for v1 |
| Query explanation | Showing the SQL to the user; useful but not core |

### Known Limitations

**1. Schema complexity**
The more tables and columns the database has, the more context the LLM needs.
Very large schemas may exceed the model's context window or degrade SQL quality.

**2. Ambiguous questions**
"Show me the best customers" is ambiguous — best by revenue? by order count? by recency?
The LLM will make a reasonable interpretation but may not match business intent.

**3. Business rule coverage**
The system only applies the business rules explicitly listed in `_BUSINESS_RULES`.
Any domain logic not mentioned may be handled incorrectly.

**4. Hallucination risk**
LLMs can occasionally generate SQL that looks correct but isn't. The agent's self-
correction loop catches most errors, but complex queries should be verified.

**5. Session-only history**
Refreshing the browser starts a fresh session. There is no memory across sessions.
