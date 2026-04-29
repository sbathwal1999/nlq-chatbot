# 11 — Advanced NLQ: Research, Improvements & Production Readiness

## Table of Contents

1. [Where We Are Today](#1-where-we-are-today)
2. [The Research Landscape](#2-the-research-landscape)
3. [Benchmark Datasets](#3-benchmark-datasets)
4. [Technique 1 — Few-Shot Example Selection](#4-technique-1--few-shot-example-selection)
5. [Technique 2 — Schema Retrieval & Pruning](#5-technique-2--schema-retrieval--pruning)
6. [Technique 3 — Query Decomposition](#6-technique-3--query-decomposition)
7. [Technique 4 — Self-Correction & Execution Feedback](#7-technique-4--self-correction--execution-feedback)
8. [Technique 5 — Ambiguity Detection & Clarification](#8-technique-5--ambiguity-detection--clarification)
9. [Technique 6 — Multi-Agent Architecture](#9-technique-6--multi-agent-architecture)
10. [Technique 7 — Fine-Tuning vs Prompting](#10-technique-7--fine-tuning-vs-prompting)
11. [Connecting a Production Database](#11-connecting-a-production-database)
12. [Improvement Roadmap](#12-improvement-roadmap)

---

## 1. Where We Are Today

Our current system is a solid **baseline NLQ implementation**. To understand where
it sits on the research spectrum, here is an honest assessment:

### What We Do Well

| Capability | Our implementation |
|---|---|
| Single-hop questions | ✅ "Top 5 products last month" — handled reliably |
| Simple JOIN queries | ✅ Agent discovers schema and generates joins |
| Business rule application | ✅ `_BUSINESS_RULES` in system prompt |
| Short follow-up questions | ✅ History prepended as plain text |
| Safety (read-only) | ✅ Three-layer defence |

### Where We Fall Short

| Limitation | Root cause |
|---|---|
| Complex multi-step questions | Single agent loop, no decomposition |
| Large schemas (100+ tables) | Full schema sent to LLM, context overflow |
| Ambiguous questions | No clarification step — LLM guesses |
| Wrong answers on edge cases | No verification against execution results |
| No examples shown to LLM | Zero-shot SQL generation only |
| Session-only memory | No learning from past corrections |

Each of these limitations has been studied deeply in the research literature.
The sections below explain the best solutions found so far and how to implement them.

---

## 2. The Research Landscape

NL2SQL (Natural Language to SQL, also called Text-to-SQL or NLQ) is one of the
most actively studied problems in AI. The research progression:

```
Era 1 (pre-2018) — Rule-based systems
  Hand-written grammars and templates
  Fragile, domain-specific, couldn't generalise

Era 2 (2018-2020) — Sequence-to-sequence neural models
  BERT-based encoders, seq2seq decoders
  Better generalisation, still needed schema-specific training

Era 3 (2020-2022) — Pre-trained language models
  T5, BART fine-tuned on SQL benchmarks
  Spider benchmark becomes the standard
  RAT-SQL, BRIDGE — schema-linking era

Era 4 (2022-present) — Large language models + prompting
  GPT-4, Llama, Claude — zero/few-shot SQL generation
  DAIL-SQL, DIN-SQL, C3-SQL — prompt engineering era
  BIRD benchmark raises the bar to production complexity
  Multi-agent systems, execution-guided refinement
```

### State of the Art (2024-2025)

On the BIRD benchmark (the hardest production-like dataset), top systems achieve:

| System | Approach | Accuracy |
|---|---|---|
| CHASE-SQL | Multi-agent + chain-of-thought | ~73% |
| RSL-SQL | Schema linking + self-correction | ~72% |
| ReviSQL | RL with execution feedback | ~71% |
| MAC-SQL | Multi-agent collaboration | ~70% |
| GPT-4 zero-shot | No specialisation (like our system) | ~46-55% |
| Our system (estimated) | Zero-shot, small schema | ~55-65% |

Our system performs comparably to GPT-4 zero-shot on our small schema. As schema
complexity and question difficulty increase, the gap to specialised systems grows.

---

## 3. Benchmark Datasets

Understanding the benchmarks helps calibrate how hard the problem is.

### WikiSQL (2017)
- 80,654 NL-SQL pairs across 24,241 tables
- Single-table queries only — no JOINs
- Easy enough that modern LLMs achieve near-perfect accuracy
- No longer a meaningful challenge

### Spider (2018)
- 10,181 NL-SQL pairs across 200 databases
- Multi-table queries with complex JOINs, subqueries, aggregations
- Cross-domain — training and test databases are different
- The standard benchmark for years; modern LLMs score 80-85%

### CoSQL (2019)
- Multi-turn conversational Text-to-SQL
- Questions that reference prior turns ("What about last week?" style)
- Tests what our history feature is trying to solve

### BIRD (Big Bench for Large-scale Database Grounded Text-to-SQL, 2023)
- 12,751 NL-SQL pairs across 95 databases
- Real-world databases with large schemas (many tables, columns, values)
- Includes "external knowledge" — business rules the model must know
- Hard: requires domain knowledge, complex aggregations, dirty data handling
- Current state-of-the-art is ~73% — far below human performance (~92%)

### KaggleDBQA (2021)
- Real-world Kaggle databases — messy, inconsistent naming
- Tests robustness to imperfect schema design
- Much harder than Spider; top systems score ~20-30%

**The takeaway:** Our small, clean retail schema is much easier than any of these
benchmarks. Real production databases look like KaggleDBQA — messy, large, inconsistent.
The techniques below address that gap.

---

## 4. Technique 1 — Few-Shot Example Selection

### The Problem

Our current system uses **zero-shot prompting** — it gives the LLM the schema and
a question, with no examples of correct Q&A pairs. Zero-shot works for simple
questions but degrades on complex ones.

### The Research Finding

**DAIL-SQL (2023)** showed that carefully selected few-shot examples improve accuracy
by 5-15% on Spider and BIRD. The key insight: examples must be **structurally similar**
to the current question — not just semantically similar.

A question about revenue needs examples that also use `SUM(quantity * unit_price)`,
not just examples about "products".

### Implementation

Store a curated set of (question, SQL) pairs as examples:

```python
# chain.py — add to _BUSINESS_RULES or a separate section

EXAMPLE_PAIRS = [
    {
        "question": "What were the top 5 products by revenue last month?",
        "sql": """
            SELECT p.name, SUM(oi.quantity * oi.unit_price) AS revenue
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            JOIN products p ON oi.product_id = p.id
            WHERE o.status != 'cancelled'
              AND o.ordered_at >= NOW() - INTERVAL '30 days'
            GROUP BY p.name
            ORDER BY revenue DESC
            LIMIT 5;
        """,
    },
    {
        "question": "How many orders were placed in each region this week?",
        "sql": """
            SELECT c.region, COUNT(DISTINCT o.id) AS order_count
            FROM orders o
            JOIN customers c ON o.customer_id = c.id
            WHERE o.status != 'cancelled'
              AND o.ordered_at >= NOW() - INTERVAL '7 days'
            GROUP BY c.region
            ORDER BY order_count DESC;
        """,
    },
    {
        "question": "Which customers have not placed any orders in the last 90 days?",
        "sql": """
            SELECT c.name, c.email
            FROM customers c
            WHERE c.id NOT IN (
                SELECT DISTINCT customer_id
                FROM orders
                WHERE ordered_at >= NOW() - INTERVAL '90 days'
                  AND status != 'cancelled'
            )
            ORDER BY c.name;
        """,
    },
]

def _format_examples(examples: list[dict]) -> str:
    """Format Q&A pairs as few-shot examples for the system prompt."""
    lines = ["\nExamples of correct queries:"]
    for ex in examples:
        lines.append(f"\nQuestion: {ex['question']}")
        lines.append(f"SQL:\n{ex['sql'].strip()}")
    return "\n".join(lines)

# In build_chain(), add examples to AGENT_PREFIX:
AGENT_PREFIX = _BUSINESS_RULES + _format_examples(EXAMPLE_PAIRS) + SQL_PREFIX
```

### Advanced: Dynamic Example Selection

For larger example sets, select the most relevant examples per question using
embedding similarity:

```python
# Requires: uv add sentence-transformers
from sentence_transformers import SentenceTransformer
import numpy as np

_encoder = SentenceTransformer("all-MiniLM-L6-v2")
_example_embeddings = _encoder.encode([ex["question"] for ex in EXAMPLE_PAIRS])

def select_examples(question: str, k: int = 3) -> list[dict]:
    """Return the k most similar examples to the current question."""
    q_embedding = _encoder.encode([question])
    similarities = np.dot(_example_embeddings, q_embedding.T).flatten()
    top_k_indices = np.argsort(similarities)[-k:][::-1]
    return [EXAMPLE_PAIRS[i] for i in top_k_indices]
```

Then in `app.py`, call `select_examples(question)` and inject them into the prompt
before invoking the agent.

**Research reference:** DAIL-SQL ("Efficient Prompting of Large Language Models for
Text-to-SQL", 2023) — showed question-SQL skeleton matching outperforms pure semantic
similarity for example selection.

---

## 5. Technique 2 — Schema Retrieval & Pruning

### The Problem

For a database with 50+ tables and 500+ columns, sending the full schema to the LLM:
1. Exceeds the context window
2. Confuses the model with irrelevant tables
3. Increases cost and latency

Our retail schema has 4 tables — this is not a problem today. But connecting to a
real ERP or data warehouse makes it critical.

### The Research Finding

**RSL-SQL (2024)** showed that schema pruning can:
- Reduce input columns by **83%**
- While maintaining **94% recall** of relevant columns
- Improve accuracy significantly versus full-schema approaches

The trick: use the question to predict which tables and columns are relevant before
building the final prompt.

### Implementation: Two-Stage Schema Filtering

**Stage 1 — Table selection**

Use the LLM itself to predict which tables are needed before running the full agent:

```python
# In a new file: schema_filter.py

from langchain_groq import ChatGroq
from langchain_community.utilities import SQLDatabase
from pydantic import SecretStr
import os

TABLE_FILTER_PROMPT = """
Given the following database tables and a question, list only the table names
that are needed to answer the question. Return ONLY a comma-separated list of
table names, nothing else.

Available tables:
{tables}

Question: {question}

Required tables:
"""

def select_relevant_tables(question: str, db: SQLDatabase, llm: ChatGroq) -> list[str]:
    """Return the subset of tables relevant to the question."""
    all_tables = db.get_usable_table_names()
    prompt = TABLE_FILTER_PROMPT.format(
        tables="\n".join(f"- {t}" for t in all_tables),
        question=question,
    )
    response = llm.invoke(prompt)
    selected = [t.strip() for t in response.content.split(",")]
    # Validate — only return tables that actually exist
    return [t for t in selected if t in all_tables]
```

**Stage 2 — Build scoped agent**

```python
# chain.py — modify build_chain to accept a table subset

def build_scoped_agent(tables: list[str]) -> object:
    """Build an agent restricted to the given table subset."""
    db = SQLDatabase.from_uri(db_url, include_tables=tables)
    return create_sql_agent(llm=llm, db=db, ...)
```

**Stage 3 — Integrate in app.py**

```python
# app.py — two-step invocation
relevant_tables = select_relevant_tables(question, full_db, llm)
scoped_agent = build_scoped_agent(relevant_tables)
result = await cl.make_async(scoped_agent.invoke)({"input": prompt})
```

### Vector-Based Schema Retrieval (for very large schemas)

For databases with 100+ tables, use semantic search over table descriptions:

```python
# Requires: uv add chromadb sentence-transformers

import chromadb
from sentence_transformers import SentenceTransformer

# At startup: build a vector index of table descriptions
def build_schema_index(db: SQLDatabase) -> chromadb.Collection:
    client = chromadb.Client()
    collection = client.create_collection("schema")
    encoder = SentenceTransformer("all-MiniLM-L6-v2")

    for table in db.get_usable_table_names():
        # Get column names as a description
        info = db.get_table_info([table])
        embedding = encoder.encode(info).tolist()
        collection.add(
            documents=[info],
            embeddings=[embedding],
            ids=[table],
        )
    return collection

# At query time: retrieve top-k relevant tables
def retrieve_tables(question: str, collection, k: int = 5) -> list[str]:
    encoder = SentenceTransformer("all-MiniLM-L6-v2")
    q_embedding = encoder.encode(question).tolist()
    results = collection.query(query_embeddings=[q_embedding], n_results=k)
    return results["ids"][0]
```

**Research reference:** CRUSH4SQL, CSR-RAG — both use multi-dimensional retrieval
(contextual, structural, relational) rather than a single embedding distance.

---

## 6. Technique 3 — Query Decomposition

### The Problem

Complex questions like "For each region, what percentage of orders placed last month
were delivered, and which region had the highest delivery rate?" require multiple
sub-queries, intermediate aggregations, and final joins. A single-shot agent often
fails or produces incorrect SQL for these.

### The Research Finding

**DIN-SQL (2024)** decomposes complex questions into sub-problems before SQL generation:

1. **Classify** the question complexity (simple / nested / multi-step)
2. **Decompose** multi-step questions into ordered sub-problems
3. **Solve** each sub-problem (generating a sub-query or CTE)
4. **Combine** sub-results into the final answer

This mirrors how a human SQL expert approaches hard questions — breaking them down
before writing any code.

**MAC-SQL (2024)** takes this further with specialised agents:
- A **selector** agent picks relevant tables
- A **decomposer** agent breaks the question into sub-tasks
- A **refiner** agent fixes execution errors

### Implementation: Decomposition via Chain-of-Thought

Add a decomposition step before the SQL agent:

```python
# decompose.py — new file

DECOMPOSITION_PROMPT = """
Analyse this database question and determine if it requires multiple steps.

Question: {question}

If the question can be answered with a single SQL query, reply:
SIMPLE: [restate the question]

If the question requires multiple steps or sub-queries, reply:
COMPLEX
Step 1: [first sub-question]
Step 2: [second sub-question]
...
Final: [how to combine the steps]

Be concise. Only list the steps, no explanation.
"""

def decompose_question(question: str, llm) -> list[str]:
    """
    Return a list of sub-questions if complex, or a single-element list if simple.
    """
    response = llm.invoke(DECOMPOSITION_PROMPT.format(question=question))
    text = response.content.strip()

    if text.startswith("SIMPLE:"):
        return [question]  # No decomposition needed

    # Parse COMPLEX response
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    steps = [l.split(":", 1)[1].strip() for l in lines if ":" in l and not l.startswith("COMPLEX")]
    return steps if steps else [question]
```

```python
# app.py — updated on_message

sub_questions = decompose_question(question, llm)

if len(sub_questions) == 1:
    # Simple path — current behaviour
    result = await cl.make_async(agent.invoke)({"input": prompt})
    answer = result.get("output", "")
else:
    # Complex path — solve each sub-question, combine
    partial_answers = []
    for sub_q in sub_questions:
        sub_result = await cl.make_async(agent.invoke)({"input": sub_q})
        partial_answers.append(sub_result.get("output", ""))

    # Ask LLM to synthesise the partial answers
    synthesis_prompt = (
        f"Original question: {question}\n\n"
        + "\n\n".join(f"Sub-answer {i+1}: {a}" for i, a in enumerate(partial_answers))
        + "\n\nCombine the above sub-answers into a single, complete answer."
    )
    final = llm.invoke(synthesis_prompt)
    answer = final.content
```

**Research reference:** DIN-SQL ("Decomposed In-Context Learning with Few-Shot Prompting
for Text-to-SQL", 2023) — achieved 82.8% on Spider by decomposing questions before
SQL generation.

---

## 7. Technique 4 — Self-Correction & Execution Feedback

### The Problem

The LLM sometimes generates SQL that looks syntactically correct but produces wrong
results — wrong column references, missing filters, off-by-one date logic. Our current
system has no way to detect or correct these errors.

### The Research Finding

**ReviSQL (2024)** and **MTSQL-R1** use execution results as feedback:
1. Generate a candidate SQL query
2. Execute it
3. If it throws an error — feed the error back and ask the LLM to fix it
4. If it succeeds — optionally verify the result makes sense

This "execution-guided refinement" is the most reliable form of self-correction
because it uses actual database feedback rather than another LLM call.

### Implementation: Retry on Error

LangChain's `handle_parsing_errors=True` already handles LLM formatting errors.
We can add explicit SQL error recovery:

```python
# In chain.py, or as a wrapper around agent.invoke

MAX_RETRIES = 2

def invoke_with_retry(agent, prompt: str) -> dict:
    """
    Invoke the agent. On SQL error, feed the error back and retry.
    """
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        if attempt > 0 and last_error:
            # Prepend the error as context for the retry
            retry_prompt = (
                f"{prompt}\n\n"
                f"Note: A previous attempt generated a SQL query that failed "
                f"with this error: {last_error}\n"
                f"Please fix the SQL and try again."
            )
        else:
            retry_prompt = prompt

        result = agent.invoke({"input": retry_prompt})
        output = result.get("output", "")

        # Check if the output contains an error indication
        if "error" in output.lower() and "sql" in output.lower():
            last_error = output
            continue

        return result

    return {"output": f"Unable to answer after {MAX_RETRIES} retries. Last error: {last_error}"}
```

### Implementation: Result Sanity Check

```python
SANITY_CHECK_PROMPT = """
A user asked: "{question}"
The database returned: "{result}"
The system answered: "{answer}"

Does the answer make sense given the question? Reply YES or NO and one sentence why.
"""

async def sanity_check(question: str, sql_result: str, answer: str, llm) -> bool:
    """Return True if the answer appears reasonable."""
    response = llm.invoke(SANITY_CHECK_PROMPT.format(
        question=question, result=sql_result, answer=answer
    ))
    return response.content.strip().upper().startswith("YES")
```

This is an extra LLM call (adds ~300ms) but can catch obvious wrong answers before
they reach the user.

**Research reference:** RSL-SQL uses "multi-turn self-correction" — the model checks
its own SQL against schema constraints before executing. GradeSQL uses graph-based
reward models to score intermediate SQL generation steps.

---

## 8. Technique 5 — Ambiguity Detection & Clarification

### The Problem

"Show me the best customers" is ambiguous — best by revenue? by order count? by
recency? Our system makes a silent assumption. The user may not even notice if the
assumption is wrong.

### The Research Finding

**AmbiSQL (2024)** detects query ambiguities and generates multiple-choice
clarification questions. Rather than guessing, the system asks the user which
interpretation they intended.

This is especially valuable in production: wrong assumptions in a business report
can lead to bad decisions.

### Implementation

```python
# ambiguity.py — new file

AMBIGUITY_PROMPT = """
Analyse this database question for ambiguity.

Question: {question}

A question is ambiguous if:
- A key term could be measured in multiple ways (e.g. "best" could mean revenue or count)
- A time period is unclear (e.g. "recent" with no definition)
- A filter could be applied in multiple ways

If the question is clear, reply: CLEAR

If the question is ambiguous, reply:
AMBIGUOUS
Interpretations:
1. [first interpretation]
2. [second interpretation]
(list up to 3)
"""

def detect_ambiguity(question: str, llm) -> list[str] | None:
    """
    Return None if question is clear.
    Return a list of interpretations if ambiguous.
    """
    response = llm.invoke(AMBIGUITY_PROMPT.format(question=question))
    text = response.content.strip()

    if text.startswith("CLEAR"):
        return None

    lines = text.split("\n")
    interpretations = [
        l.split(".", 1)[1].strip()
        for l in lines
        if l.strip() and l.strip()[0].isdigit()
    ]
    return interpretations if interpretations else None
```

```python
# app.py — add before agent invocation

interpretations = detect_ambiguity(question, llm)
if interpretations:
    options = "\n".join(f"{i+1}. {interp}" for i, interp in enumerate(interpretations))
    clarification = (
        f"I want to make sure I answer correctly. Your question could mean:\n\n"
        f"{options}\n\n"
        f"Which did you mean? (reply with the number, or rephrase your question)"
    )
    await cl.Message(content=clarification).send()
    # Store the interpretations in session — handle the follow-up in the next turn
    cl.user_session.set("pending_interpretations", interpretations)
    cl.user_session.set("pending_question", question)
    return
```

**Research reference:** AmbiSQL — "Detecting and Interactively Resolving Ambiguity
in Text-to-SQL" (2024). AmbiGraph-Eval showed that even top LLMs fail on ambiguous
queries — explicit detection and user confirmation is the only reliable fix.

---

## 9. Technique 6 — Multi-Agent Architecture

### The Problem

Our single agent does everything: list tables, inspect schema, generate SQL, format
the answer. This works for simple queries. For complex analytical questions it is
a single point of failure — if any step goes wrong, the whole answer is wrong.

### The Research Finding

**MAC-SQL (Multi-Agent Collaborative SQL, 2024)** and **CHASE-SQL** use specialised
agents:

```
Orchestrator Agent
    │
    ├── Schema Selector Agent
    │     Selects relevant tables, columns
    │     Returns: filtered schema
    │
    ├── SQL Generator Agent
    │     Takes filtered schema + question
    │     Returns: candidate SQL query
    │
    ├── SQL Critic Agent
    │     Reviews the generated SQL
    │     Checks for: missing filters, wrong joins, business rule violations
    │     Returns: corrected SQL or approval
    │
    └── Answer Formatter Agent
          Takes raw query results
          Returns: human-readable answer
```

This mirrors how a data team actually works — different specialists handle different
parts of the problem.

### Implementation Sketch

```python
# multi_agent_chain.py — new file
# Requires: LangGraph (pip install langgraph) for agent orchestration

from langgraph.graph import StateGraph, END
from typing import TypedDict

class SQLState(TypedDict):
    question: str
    relevant_tables: list[str]
    sql_query: str
    sql_result: str
    answer: str
    error: str | None

def schema_selector_node(state: SQLState) -> SQLState:
    """Select the tables relevant to the question."""
    tables = select_relevant_tables(state["question"], full_db, llm)
    return {**state, "relevant_tables": tables}

def sql_generator_node(state: SQLState) -> SQLState:
    """Generate SQL for the question using only the selected tables."""
    scoped_db = SQLDatabase.from_uri(db_url, include_tables=state["relevant_tables"])
    scoped_agent = create_sql_agent(llm=llm, db=scoped_db, ...)
    result = scoped_agent.invoke({"input": state["question"]})
    # Extract the SQL from the agent's intermediate steps
    sql = extract_sql_from_result(result)
    return {**state, "sql_query": sql}

def sql_critic_node(state: SQLState) -> SQLState:
    """Review the SQL for correctness against business rules."""
    critic_prompt = f"""
    Review this SQL query for a retail database.
    Business rules: cancelled orders must be excluded.

    SQL: {state['sql_query']}

    Does this SQL correctly apply the business rules?
    If yes, reply: APPROVED
    If no, reply: FIXED\n[corrected SQL]
    """
    response = llm.invoke(critic_prompt).content
    if response.startswith("APPROVED"):
        return state
    corrected_sql = response.replace("FIXED", "").strip()
    return {**state, "sql_query": corrected_sql}

# Build the graph
workflow = StateGraph(SQLState)
workflow.add_node("select_schema", schema_selector_node)
workflow.add_node("generate_sql", sql_generator_node)
workflow.add_node("critique_sql", sql_critic_node)
workflow.set_entry_point("select_schema")
workflow.add_edge("select_schema", "generate_sql")
workflow.add_edge("generate_sql", "critique_sql")
workflow.add_edge("critique_sql", END)

multi_agent = workflow.compile()
```

**Research reference:** MAC-SQL achieved ~67% on BIRD (vs ~55% for single-agent GPT-4).
CHASE-SQL's multi-agent chain-of-thought reached ~73% — the current state of the art.

---

## 10. Technique 7 — Fine-Tuning vs Prompting

### When Prompting Reaches Its Limits

Our current approach is pure **prompting** — we send the schema, business rules, and
question to a general-purpose LLM. For our 4-table demo schema, this works well.

For a production system with domain-specific terminology, complex schemas, and high
accuracy requirements, you eventually hit the ceiling of what prompting can achieve.

### Fine-Tuning Options

**Option A — Full fine-tuning**
Train the model on (question, SQL) pairs from your specific database:

```python
# Training data format
{"messages": [
    {"role": "system", "content": "You are a SQL expert for Acme Corp retail database..."},
    {"role": "user", "content": "What were Q3 sales by territory?"},
    {"role": "assistant", "content": "SELECT territory, SUM(amount) FROM sales WHERE quarter=3 GROUP BY territory"}
]}
```

- Requires ~500+ high-quality examples
- Needs GPU infrastructure (A100 or similar for 7B+ models)
- Can reduce prompt length dramatically (schema baked into weights)
- Best for high-volume production systems

**Option B — Schema Internalization**

The "Schema on the Inside" paper (2024) showed you can fine-tune a model to
*memorise* a specific database schema — reducing prompt length by 99% while
maintaining accuracy. Practical for databases that rarely change.

**Option C — LoRA / QLoRA (parameter-efficient fine-tuning)**

Fine-tune only a small adapter layer on top of the base model. Requires far less
GPU memory than full fine-tuning:

```bash
# Example using Hugging Face + PEFT library
pip install peft transformers datasets

# Fine-tune Llama 3 8B with LoRA on your SQL examples
# Realistic compute: 1 A100 GPU, ~2 hours for 1000 examples
```

**When to fine-tune vs keep prompting:**

| Scenario | Recommendation |
|---|---|
| <50 questions/day, small schema | Stay with prompting |
| Specific domain jargon confusing the model | Add more examples to prompt first |
| Hitting 70%+ accuracy with prompting | Fine-tuning unlikely to help much more |
| <50% accuracy despite good prompt engineering | Consider fine-tuning |
| High volume, cost is a concern | Fine-tune a smaller model |
| Schema changes frequently | Prompting — fine-tuning requires retraining |

**Research reference:** SQL-PaLM (Google, 2023) — systematic comparison of prompting
vs fine-tuning across model sizes. Finding: fine-tuning beats prompting when you have
500+ domain-specific examples; below that, prompt engineering is more cost-effective.

---

## 11. Connecting a Production Database

### The Realistic Challenge

A production database is not a clean 4-table schema. It might have:
- 200+ tables, many with cryptic names (`tbl_ord_hdr`, `dim_cust_v2`)
- Hundreds of columns, many redundant or deprecated
- Inconsistent naming (`customer_id`, `cust_id`, `CUSTOMERID` across tables)
- No documented relationships between tables
- Views, materialised views, stored procedures
- Dirty data (nulls everywhere, inconsistent values)

Each of these degrades NLQ accuracy. Here is how to address them systematically.

### Step 1 — Schema Documentation

The single highest-impact improvement is adding natural language descriptions
to your tables and columns. Without descriptions, the LLM must guess what
`tbl_ord_hdr.ord_sts_cd` means.

**Option A — PostgreSQL comments (persistent, source-controlled)**

```sql
COMMENT ON TABLE orders IS
    'Customer purchase orders. One row per order. Use order_items for line details.';

COMMENT ON COLUMN orders.status IS
    'Order lifecycle state. Values: pending, shipped, delivered, cancelled.
     IMPORTANT: Always exclude cancelled orders from sales calculations.';

COMMENT ON COLUMN orders.ordered_at IS
    'Timestamp when the customer placed the order (UTC).';
```

LangChain's `SQLDatabase` automatically includes comments in the schema output shown
to the LLM. This is the easiest and most maintainable approach.

**Option B — External schema registry (for legacy databases you cannot modify)**

```python
# schema_registry.py

TABLE_DESCRIPTIONS = {
    "tbl_ord_hdr": "Order header — one row per customer order. Equivalent to 'orders'.",
    "dim_cust_v2": "Customer dimension table — current version. Use this, not dim_cust_v1.",
    "fact_sales": "Daily sales aggregation. Pre-aggregated — use for dashboards, not raw analysis.",
}

COLUMN_DESCRIPTIONS = {
    "tbl_ord_hdr.ord_sts_cd": "Order status code. 'C' = cancelled, 'D' = delivered, 'S' = shipped, 'P' = pending.",
    "tbl_ord_hdr.ord_dt": "Order date (date only, no time). For time-of-day analysis, use tbl_ord_dtl.",
}

def enrich_schema_prompt(table: str, column: str | None = None) -> str:
    """Return human-readable description for a table or column."""
    if column:
        key = f"{table}.{column}"
        return COLUMN_DESCRIPTIONS.get(key, "")
    return TABLE_DESCRIPTIONS.get(table, "")
```

Inject these descriptions into `_BUSINESS_RULES` or as part of the schema tool output.

### Step 2 — Table Allowlist

Do not expose your entire database to the LLM. Define which tables are safe and
relevant for NLQ:

```python
# chain.py
ALLOWED_TABLES = [
    "customers",
    "orders",
    "order_items",
    "products",
    # Explicitly exclude: audit_log, user_sessions, internal_config
]

db = SQLDatabase.from_uri(
    db_url,
    include_tables=ALLOWED_TABLES,   # ← only these tables visible to agent
)
```

Benefits:
- Smaller context window (faster, cheaper)
- Prevents accidental queries against sensitive tables
- Reduces confusion from deprecated or internal tables

### Step 3 — Value Examples in Business Rules

For columns with a small, fixed set of valid values, list them explicitly:

```python
_BUSINESS_RULES = """
...
Valid order statuses: 'pending', 'shipped', 'delivered', 'cancelled'
  → Always use single quotes and exact lowercase spelling.

Valid regions: 'North', 'South', 'East', 'West'
  → Note: stored with capitalised first letter.

Valid product categories: 'Electronics', 'Stationery', 'Furniture', 'Accessories'
  → Use exact casing from this list.
"""
```

The LLM generates wrong SQL when it guesses column values (e.g. filtering on
`status = 'Cancelled'` when the actual value is `'cancelled'`).

### Step 4 — Query Result Validation

In production, add a layer that validates the result makes sense:

```python
# validation.py

def validate_result(question: str, result_rows: list, answer: str) -> tuple[bool, str]:
    """
    Basic sanity checks on query results.
    Returns (is_valid, reason).
    """
    # Empty result for a "how many" question is suspicious
    if not result_rows and any(w in question.lower() for w in ["how many", "count", "total"]):
        return False, "Query returned no rows for a count question"

    # Extremely large numbers in revenue context — check for unit_price * quantity bug
    if result_rows and len(result_rows[0]) > 0:
        first_value = result_rows[0][-1]
        if isinstance(first_value, (int, float)) and first_value > 1_000_000_000:
            return False, f"Suspiciously large value: {first_value}. Possible calculation error."

    return True, "OK"
```

### Step 5 — Logging for Continuous Improvement

Log every query and result to a database table. Review failures weekly and add them
as business rules or examples:

```sql
-- Add to your production database
CREATE TABLE nlq_log (
    id          SERIAL PRIMARY KEY,
    session_id  TEXT,
    question    TEXT NOT NULL,
    sql_query   TEXT,
    answer      TEXT,
    was_correct BOOLEAN,  -- user feedback: thumbs up/down
    asked_at    TIMESTAMP DEFAULT NOW()
);
```

```python
# app.py — log after each response
def log_query(session_id: str, question: str, sql: str, answer: str):
    db.run(
        "INSERT INTO nlq_log (session_id, question, sql_query, answer) "
        "VALUES (%s, %s, %s, %s)",
        (session_id, question, sql, answer)
    )
```

Reviewing `was_correct = false` rows gives you a prioritised list of what to fix.

---

## 12. Improvement Roadmap

A pragmatic ordering of improvements by effort vs impact:

### Tier 1 — Low effort, high impact (hours)

| Improvement | What to do | Expected gain |
|---|---|---|
| Add few-shot examples | Write 5-10 (question, SQL) pairs for common query types | +5-10% accuracy on similar questions |
| Add column comments | `COMMENT ON COLUMN` for all columns with unclear names | Eliminates wrong-column-name errors |
| Restrict to allowlist | Set `include_tables=` to only analytical tables | Reduces hallucinated table names |
| Add value examples | List valid values for enum-like columns in `_BUSINESS_RULES` | Eliminates wrong-value filter errors |

### Tier 2 — Medium effort, medium-high impact (days)

| Improvement | What to do | Expected gain |
|---|---|---|
| Ambiguity detection | Add `detect_ambiguity()` step before agent invocation | Eliminates wrong-interpretation errors |
| Retry on error | Wrap `agent.invoke()` with 2-retry error feedback loop | Recovers ~30% of SQL errors |
| Schema filtering | Add table selection LLM call before main agent | Required for schemas > 20 tables |
| Sanity check | Add post-answer LLM verification pass | Catches obvious wrong answers |

### Tier 3 — Higher effort, targeted impact (weeks)

| Improvement | What to do | Expected gain |
|---|---|---|
| Dynamic example selection | Embed examples and retrieve by similarity | +5-15% on complex queries |
| Query decomposition | Add decomposition step for multi-step questions | Handles previously unsolvable queries |
| Multi-agent pipeline | Separate schema, generation, critique agents | +10-20% on hard queries |
| User feedback loop | Thumbs up/down → log → add to examples | Compounding improvement over time |

### Tier 4 — Major investment (months)

| Improvement | What to do | Expected gain |
|---|---|---|
| Fine-tune on domain data | Collect 500+ examples, fine-tune Llama 8B | Specialised model for your schema |
| RL from execution feedback | ReviSQL-style RL training loop | Near-SOTA on your domain |
| Full multi-agent with LangGraph | MAC-SQL/CHASE-SQL architecture | Production-grade system |

### What Not to Do

- **Don't add more LLM calls than necessary.** Each call adds latency. The user
  notices when response time exceeds 10 seconds.
- **Don't try to solve schema noise with prompting.** Adding 200 column descriptions
  to the system prompt overflows the context window. Use schema filtering + targeted
  comments instead.
- **Don't skip the logging step.** You cannot improve what you do not measure. Logging
  queries and correctness is foundational to all other improvements.
- **Don't fine-tune before prompting is exhausted.** Fine-tuning is expensive and
  domain-specific. Exhaust prompt engineering first.

---

## Further Reading

| Paper | Key contribution | Read if you are... |
|---|---|---|
| DAIL-SQL (2023) | Systematic prompt engineering for Text-to-SQL | Starting with prompting improvements |
| DIN-SQL (2023) | Question decomposition | Tackling complex multi-step queries |
| MAC-SQL (2024) | Multi-agent collaboration | Ready to build a multi-agent pipeline |
| CHASE-SQL (2024) | Chain-of-thought + candidate selection | Aiming for SOTA accuracy |
| RSL-SQL (2024) | Schema linking for large databases | Connecting to a real large database |
| ReviSQL (2024) | RL with execution feedback | Considering fine-tuning / RL |
| AmbiSQL (2024) | Interactive ambiguity resolution | Dealing with vague business questions |
| Spider benchmark | Evaluation standard | Measuring and comparing your system |
| BIRD benchmark | Production-complexity evaluation | Testing against realistic schemas |

All papers are findable via Google Scholar or arxiv.org by searching the paper title.
