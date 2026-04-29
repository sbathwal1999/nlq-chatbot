# 05 — LangChain & SQL Agents

## Table of Contents

1. [What is LangChain?](#1-what-is-langchain)
2. [Chains vs Agents](#2-chains-vs-agents)
3. [Tools — The Agent's Hands](#3-tools--the-agents-hands)
4. [The Agent Loop](#4-the-agent-loop)
5. [ReAct vs Tool-Calling](#5-react-vs-tool-calling)
6. [SQLDatabaseToolkit](#6-sqldatabasetoolkit)
7. [create_sql_agent — The API](#7-create_sql_agent--the-api)
8. [Prompt Anatomy](#8-prompt-anatomy)
9. [Memory in LangChain vs Our Approach](#9-memory-in-langchain-vs-our-approach)
10. [Key Design Decisions](#10-key-design-decisions)

---

## 1. What is LangChain?

LangChain is a Python (and JavaScript) framework for building applications powered by
Large Language Models. It solves a practical problem: LLMs alone are stateless text
processors — they take text in and produce text out. Real applications need:

- **Persistence** — remembering previous messages
- **Tool use** — calling APIs, running code, querying databases
- **Orchestration** — multi-step reasoning, conditional logic
- **Structured I/O** — parsing model output into typed objects

LangChain provides abstractions for all of these. Think of it as the "glue layer"
between an LLM and the rest of your application.

### The LangChain Ecosystem

```
langchain-core          ← Base abstractions (BaseChain, BaseTool, BaseMemory)
langchain               ← High-level chains, agents, memory classes
langchain-community     ← Third-party integrations (SQLDatabase, most toolkits)
langchain-groq          ← Groq-specific ChatModel implementation
langchain-openai        ← OpenAI-specific (for reference)
```

Our project uses:
```toml
langchain>=0.2.0
langchain-community>=0.2.0   # create_sql_agent, SQLDatabase
langchain-groq>=0.1.0        # ChatGroq
```

### The Core Abstraction: Runnables

Everything in modern LangChain is a `Runnable` — an object with a `.invoke()` method.
Runnables can be chained together with the pipe operator (`|`):

```python
chain = prompt | llm | output_parser
result = chain.invoke({"question": "..."})
```

This is the "chain" in LangChain — a pipeline of components, each feeding into the next.

---

## 2. Chains vs Agents

### Chains — Fixed Pipelines

A **chain** is a predetermined sequence of steps:

```
Input → Step 1 → Step 2 → Step 3 → Output
```

The path is fixed at design time. A chain does not make decisions — it just executes
the pre-defined sequence.

**Example: A simple Q&A chain**
```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq

prompt = ChatPromptTemplate.from_template("Answer this question: {question}")
llm = ChatGroq(model="llama-3.3-70b-versatile")

chain = prompt | llm
result = chain.invoke({"question": "What is SQL?"})
```

Chains are fast and predictable, but inflexible. They cannot adapt based on
intermediate results.

### Agents — Dynamic Decision Makers

An **agent** is a loop where an LLM decides, at each step, what to do next:

```
Input
  │
  ▼
LLM: What should I do first?
  │
  ▼
Call a tool
  │
  ▼
LLM: What should I do with this result?
  │
  ▼
Call another tool (or give a final answer)
  │
  ▼
Output
```

The LLM makes decisions. The number of steps is not fixed. The agent can explore,
recover from errors, and adapt based on what it discovers.

### When to Use Which

| Use a chain when | Use an agent when |
|---|---|
| The steps are always the same | The steps depend on intermediate results |
| Speed matters more than flexibility | Flexibility matters more than predictability |
| The task has a clear, fixed structure | The task requires exploration or multi-step reasoning |
| You need deterministic behaviour | You need adaptive behaviour |

**Our use case:** SQL query answering requires an agent. The agent needs to discover
the schema first, then decide which tables to query, then decide how to join them.
These decisions depend on the question and the schema — they cannot be hardcoded.

---

## 3. Tools — The Agent's Hands

A **tool** is a function the agent can call. Tools are what give the agent the ability
to interact with the outside world. Without tools, the agent is trapped inside its
own knowledge.

### Tool Anatomy

```python
from langchain_core.tools import Tool

def search_database(query: str) -> str:
    """Run a SQL query and return the results."""
    return db.run(query)

tool = Tool(
    name="sql_db_query",
    func=search_database,
    description="Execute a SQL SELECT query against the database. Input: a SQL string."
)
```

Three parts:
- **`name`** — the identifier the LLM uses to call the tool
- **`func`** — the Python function that actually runs
- **`description`** — natural language explanation of what the tool does and when to use it

The description is critical. The LLM reads descriptions to decide which tool to use.
A bad description leads to wrong tool choices.

### How the LLM Calls a Tool

In tool-calling mode, the LLM outputs structured JSON specifying which tool to call
and with what arguments:

```json
{
  "tool": "sql_db_query",
  "tool_input": {
    "query": "SELECT name, SUM(quantity) FROM order_items JOIN orders ON ... GROUP BY name LIMIT 5"
  }
}
```

LangChain parses this JSON, calls the corresponding Python function, and feeds the
result back to the LLM as a tool observation.

---

## 4. The Agent Loop

The agent runs an iterative loop until it produces a final answer or exceeds the
maximum number of steps.

```
┌──────────────────────────────────────────────────────────────────┐
│                         AGENT LOOP                               │
│                                                                  │
│  1. PLAN                                                         │
│     LLM receives: system prompt + tools list + current state     │
│     LLM outputs: tool call OR final answer                       │
│                                                                  │
│  2. ACT                                                          │
│     If tool call: LangChain executes the tool                    │
│     If final answer: loop ends                                   │
│                                                                  │
│  3. OBSERVE                                                      │
│     Tool result is appended to the conversation history          │
│     LLM sees: original question + all tool calls + all results   │
│                                                                  │
│  ──────────────────────────────────────────────────────────────  │
│  Repeat from step 1 until:                                       │
│    - LLM produces a final answer                                 │
│    - max_iterations is exceeded (default: 15)                    │
│    - An error occurs                                             │
└──────────────────────────────────────────────────────────────────┘
```

### A Concrete Example

**Question:** "What were the top 3 products by revenue last month?"

```
Iteration 1:
  LLM decides → call sql_db_list_tables
  Tool returns → "customers, order_items, orders, products"

Iteration 2:
  LLM decides → call sql_db_schema for "order_items, orders, products"
  Tool returns → CREATE TABLE orders (...), CREATE TABLE order_items (...), ...

Iteration 3:
  LLM decides → call sql_db_query
  Input: "SELECT p.name, SUM(oi.quantity * oi.unit_price) AS revenue
          FROM order_items oi
          JOIN orders o ON oi.order_id = o.id
          JOIN products p ON oi.product_id = p.id
          WHERE o.ordered_at >= NOW() - INTERVAL '30 days'
            AND o.status != 'cancelled'
          GROUP BY p.name
          ORDER BY revenue DESC
          LIMIT 3"
  Tool returns → [(Widget A, 4500.00), (Widget B, 3200.00), (Widget C, 2100.00)]

Iteration 4:
  LLM decides → final answer
  Output: "The top 3 products by revenue last month were:
           1. Widget A — £4,500
           2. Widget B — £3,200
           3. Widget C — £2,100"
```

The key insight: the LLM discovered the schema dynamically. It did not know the column
names in advance — it found them by calling tools.

### Conversation History in the Loop

Every iteration, the LLM sees the full history of the current agent run:

```
[system prompt]
[user: original question]
[assistant: tool call → sql_db_list_tables]
[tool: "customers, order_items, orders, products"]
[assistant: tool call → sql_db_schema]
[tool: "CREATE TABLE orders ..."]
[assistant: tool call → sql_db_query]
[tool: "[('Widget A', 4500.00), ...]"]
[assistant: final answer]
```

This is why agents can use previous tool results to inform later tool calls —
everything accumulates in the context.

---

## 5. ReAct vs Tool-Calling

LangChain supports multiple agent types. The two most relevant for our use case:

### ReAct (Reasoning and Acting)

ReAct is a text-based approach. The LLM produces structured free text following
a `Thought: Action: Observation:` format:

```
Thought: I need to see what tables are available.
Action: sql_db_list_tables
Action Input: ""
Observation: customers, order_items, orders, products
Thought: I should look at the schema for the relevant tables.
Action: sql_db_schema
Action Input: "orders, order_items, products"
Observation: CREATE TABLE orders ...
Thought: Now I can write the query.
Action: sql_db_query
Action Input: "SELECT ..."
Observation: [results]
Thought: I have the answer.
Final Answer: The top 3 products were...
```

LangChain parses this text with regex to extract the action and input.

**The problem:** This is fragile. If the LLM deviates even slightly from the format
(adds an extra newline, uses different capitalisation, adds a comma), the regex parser
fails. The error `"observation from last action is missing"` means the parser could
not find the observation in the expected position.

Llama models are particularly prone to this because they were not trained specifically
on LangChain's ReAct format.

### Tool-Calling (Function Calling)

Tool-calling uses structured JSON output. The LLM does not produce free text —
it produces a JSON object specifying the function call:

```json
{
  "name": "sql_db_schema",
  "arguments": {
    "table_names": "orders, order_items, products"
  }
}
```

LangChain parses this JSON directly — no regex, no text matching. JSON is either
valid or it isn't. There is no ambiguity.

**Why it works better:**
- Llama 3.3 has native function-calling support (trained on this format)
- JSON parsing is deterministic
- The LLM cannot "accidentally" output the wrong format
- Error messages are clearer when something goes wrong

```python
# How we set this in chain.py
agent = create_sql_agent(
    llm=llm,
    db=db,
    agent_type="tool-calling",   # ← key line
    ...
)
```

### Comparison Table

| Aspect | ReAct | Tool-Calling |
|---|---|---|
| Output format | Free text (`Thought: Action:`) | Structured JSON |
| Parsing | Regex on text | Native JSON parse |
| Reliability | Brittle — format-dependent | Robust — schema-validated |
| Llama compatibility | Poor — format mismatch | Good — native support |
| Error when broken | "observation missing" | Clear JSON parse error |
| Debuggability | Hard (text inspection) | Easy (structured logs) |

---

## 6. SQLDatabaseToolkit

The `SQLDatabaseToolkit` is LangChain's pre-built collection of tools for interacting
with SQL databases. When you call `create_sql_agent`, it automatically creates and
registers these tools.

### The Four Tools

**Tool 1: `sql_db_list_tables`**
```
Name:        sql_db_list_tables
Description: Input is an empty string, output is a comma-separated list
             of tables in the database.
Use case:    Agent first call — discover what tables exist
```

**Tool 2: `sql_db_schema`**
```
Name:        sql_db_schema
Description: Input is a comma-separated list of tables; output is the
             schema and sample rows for those tables.
Use case:    Agent second call — understand table structure
Example output:
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
  ...
  */
```

The sample rows are especially valuable — they show the LLM actual data values,
helping it understand what `status` values exist, date formats, etc.

**Tool 3: `sql_db_query`**
```
Name:        sql_db_query
Description: Input is a SQL query; output is the result. If the query
             is incorrect, an error message is returned.
Use case:    Execute the SQL the LLM generated
```

**Tool 4: `sql_db_query_checker`**
```
Name:        sql_db_query_checker
Description: Use this tool to double check if your query is correct
             before executing it.
Use case:    LLM can optionally validate its SQL before running it
```

The query checker actually calls the LLM again with a specific prompt asking it to
verify the SQL for common errors (wrong column names, invalid syntax, etc.). It is
a second LLM call, so it adds latency but improves correctness on complex queries.

### How SQLDatabase Works

Under the hood, `SQLDatabase` wraps SQLAlchemy:

```python
from langchain_community.utilities import SQLDatabase

db = SQLDatabase.from_uri("postgresql+psycopg2://user:pass@host:5432/dbname")

# What it does internally:
# - Creates a SQLAlchemy engine
# - Inspects the schema using information_schema
# - Stores table metadata for schema tool responses
# - Runs queries via engine.execute()
```

The `db.dialect` attribute contains the database type (`postgresql`, `sqlite`, etc.).
This is auto-injected into the prompt via `{dialect}` placeholder in `SQL_PREFIX`.

---

## 7. create_sql_agent — The API

`create_sql_agent` is a factory function that assembles all the pieces:

```python
from langchain_community.agent_toolkits import create_sql_agent

agent = create_sql_agent(
    llm=llm,                          # The language model
    db=db,                            # SQLDatabase instance
    agent_type="tool-calling",        # Agent strategy
    top_k=50,                         # Max rows to return in results
    prefix=AGENT_PREFIX,              # System prompt (before SQL_PREFIX defaults)
    verbose=False,                    # Whether to print intermediate steps
    agent_executor_kwargs={           # Passed to AgentExecutor
        "handle_parsing_errors": True # Return error text instead of crashing
    },
)
```

### What It Does Internally

```
create_sql_agent(llm, db, ...)
    │
    ├── Creates SQLDatabaseToolkit(db=db, llm=llm)
    │       └── Initialises the 4 SQL tools
    │
    ├── Builds prompt template
    │       ├── Uses prefix parameter (our AGENT_PREFIX)
    │       └── Fills {dialect} and {top_k} placeholders automatically
    │
    ├── Creates the agent (ChatAgent for tool-calling)
    │       └── Binds tools to the LLM (using llm.bind_tools())
    │
    └── Wraps in AgentExecutor
            └── The loop runner that calls agent.plan() → tool → repeat
```

### The `prefix` Parameter

The `prefix` becomes the system prompt sent to the LLM at the start of every request.

```python
# Our AGENT_PREFIX = _BUSINESS_RULES + SQL_PREFIX
#
# SQL_PREFIX comes from LangChain:
# "You are an agent designed to interact with a SQL database.
# Given an input question, create a syntactically correct {dialect} query
# to run, then look at the results of the query and return the answer...
# Unless the user specifies a specific number of examples they wish to
# obtain, always limit your query to at most {top_k} results..."
#
# {dialect} is filled with "postgresql"
# {top_k} is filled with 50 (our MAX_ROWS setting)
```

By prepending `_BUSINESS_RULES` to `SQL_PREFIX`, our business rules appear before
the standard LangChain instructions — making them take priority.

### The `handle_parsing_errors` Option

```python
agent_executor_kwargs={"handle_parsing_errors": True}
```

When the LLM produces output that cannot be parsed (broken JSON, unexpected format),
instead of raising a Python exception, LangChain returns the error text to the LLM
as an observation: `"Could not parse LLM output: ..."`. The LLM can then retry.

This is important for robustness — without it, any parsing hiccup crashes the request.

### Invoking the Agent

```python
result = agent.invoke({"input": "What were the top 5 products last month?"})
# result is a dict: {"input": "...", "output": "The top 5 products were..."}

answer = result.get("output", "I couldn't find an answer.")
```

---

## 8. Prompt Anatomy

Every time the agent runs, the LLM receives a carefully structured prompt. Understanding
this structure explains why the agent behaves the way it does.

### Full Prompt Structure

```
┌───────────────────────────────────────────────────────────────┐
│  SYSTEM MESSAGE                                               │
│                                                               │
│  [_BUSINESS_RULES]                                            │
│  "You are a helpful data analyst assistant for a retail       │
│   company. Business rules:                                    │
│   - NEVER include cancelled orders...                         │
│   - 'last month' means past 30 days..."                       │
│                                                               │
│  [SQL_PREFIX with placeholders filled]                        │
│  "You are an agent designed to interact with a SQL database.  │
│   Given an input question, create a syntactically correct     │
│   postgresql query to run, then look at the results and       │
│   return the answer.                                          │
│   Always limit results to at most 50 rows..."                 │
├───────────────────────────────────────────────────────────────┤
│  TOOLS AVAILABLE                                              │
│                                                               │
│  sql_db_list_tables: Input empty string, output table list    │
│  sql_db_schema: Input table names, output schema + samples    │
│  sql_db_query: Input SQL, output results                      │
│  sql_db_query_checker: Double-check a query before running    │
├───────────────────────────────────────────────────────────────┤
│  CONVERSATION HISTORY (injected by app.py)                    │
│                                                               │
│  Previous conversation:                                       │
│    User: What were the top 5 products?                        │
│    Assistant: The top 5 products were...                      │
├───────────────────────────────────────────────────────────────┤
│  CURRENT USER MESSAGE                                         │
│                                                               │
│  Current question: What about last week?                      │
└───────────────────────────────────────────────────────────────┘
```

### Why Business Rules Come First

Prompt position matters. Content near the beginning of the system prompt tends to
have more influence than content near the end. By placing `_BUSINESS_RULES` before
`SQL_PREFIX`, we ensure the LLM prioritises our business logic over the generic
LangChain instructions.

If we placed business rules at the end, the model might default to the generic
LangChain behaviour and only "notice" the business rules as an afterthought.

---

## 9. Memory in LangChain vs Our Approach

### LangChain's Built-in Memory

LangChain provides memory classes for maintaining conversation history:

```python
from langchain.memory import ConversationBufferMemory

memory = ConversationBufferMemory()
memory.save_context({"input": "What were sales?"}, {"output": "Sales were..."})
# memory stores and retrieves the conversation
```

Several types exist:
- `ConversationBufferMemory` — stores the full conversation verbatim
- `ConversationSummaryMemory` — summarises older messages to save tokens
- `ConversationBufferWindowMemory` — keeps only the last N messages
- `VectorStoreRetrieverMemory` — stores in a vector database for semantic retrieval

### Why We Didn't Use It

LangChain memory has limitations for our use case:

1. **Agent compatibility:** Memory integration varies by agent type. Tool-calling agents
   have different memory attachment points than ReAct agents. Getting it right requires
   careful configuration.

2. **Transparency:** Built-in memory is a black box — it injects history in ways that
   are hard to inspect or debug.

3. **Over-engineering:** For 5 conversation turns, we don't need an abstraction layer.
   A Python list does the job.

### Our Approach — Plain Text Prepend

```python
# app.py
def _build_prompt_with_history(question: str, history: list[dict[str, str]]) -> str:
    if not history:
        return question
    lines = ["Previous conversation:"]
    for turn in history:
        lines.append(f"  User: {turn['question']}")
        lines.append(f"  Assistant: {turn['answer']}")
    lines.append(f"\nCurrent question: {question}")
    return "\n".join(lines)
```

The result is readable text that any LLM can follow:

```
Previous conversation:
  User: What were the top 5 products last month?
  Assistant: The top 5 products by units sold were: 1. Ballpoint Pens...
  User: What about revenue instead of units?
  Assistant: By revenue, the top 5 were: 1. Laptop Pro...

Current question: And what region had the highest share?
```

**Advantages:**
- Easy to inspect and debug (just print it)
- Works with any agent type
- We control exactly what is included
- The window size (5 turns) is easily configurable

---

## 10. Key Design Decisions

### Why LangChain at all?

We could have written the agent loop manually — call the LLM, parse the output, call
the database, repeat. We used LangChain because:

- The SQL toolkit is already built and tested
- The agent loop handles edge cases (max iterations, error recovery)
- `create_sql_agent` gives us working SQL query generation in ~10 lines

The downside: LangChain is a heavy dependency with frequent API changes. For a
production system at scale, you might build the agent loop yourself for more control.

### Why `create_sql_agent` Over `SQLDatabaseChain`?

LangChain also has `SQLDatabaseChain` — a simpler alternative that does
`question → SQL → execute → answer` in one shot without an agent loop.

We chose `create_sql_agent` because:

| `SQLDatabaseChain` | `create_sql_agent` |
|---|---|
| Single shot — one SQL query | Multi-step — explores schema first |
| Must specify tables upfront or include full schema | Discovers tables dynamically |
| Fails on complex queries (multiple joins) | Handles complex queries via iteration |
| No self-correction | Can retry failed queries |

The agent approach is slower (more LLM calls) but significantly more accurate.

### The `verbose=False` Choice

Setting `verbose=True` prints every intermediate step — every tool call, every LLM
response — to stdout. This is extremely useful for debugging.

We set `verbose=False` in production to avoid cluttering logs, but you should set
it to `True` while developing:

```python
agent = create_sql_agent(
    ...,
    verbose=True,  # ← see every step while developing
)
```

### `handle_parsing_errors=True`

Without this, a single malformed JSON response from the LLM crashes the entire request.
With it, the error is fed back to the LLM as context and it can recover.

This is an important reliability setting — always enable it in production.
