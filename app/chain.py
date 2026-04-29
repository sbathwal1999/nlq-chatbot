"""
chain.py — LangChain SQL agent setup

Why create_sql_agent with agent_type="tool-calling"?
  A simple one-shot SQLDatabaseChain generates SQL once and returns it with no
  ability to self-correct. create_sql_agent with tool-calling uses Groq's native
  function-calling API: the LLM decides which SQL tools to call, inspects results,
  and iterates until it has a confident answer — all in one agent.invoke() call.

  We use "tool-calling" (not the default "zero-shot-react-description") because
  the legacy ReAct mode requires strict Thought/Action/Observation text formatting
  that Llama models occasionally mis-format, causing "observation missing" errors.
  Native tool-calling is both more reliable and faster.

  Trade-off: multiple LLM + DB round-trips per question costs more tokens than a
  single chain call. Acceptable for a business analyst demo.

Builds the agent that:
  1. Receives a natural language question (optionally enriched with history)
  2. Introspects the live DB schema
  3. Calls the Groq LLM to generate SQL
  4. Executes the SQL against PostgreSQL
  5. Returns a plain-English answer

The agent is constructed once at session start and reused across messages.
"""

import logging
import os

from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.agent_toolkits.sql.prompt import SQL_PREFIX
from langchain_community.utilities import SQLDatabase
from langchain_groq import ChatGroq
from pydantic import SecretStr

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
# We extend the default LangChain SQL_PREFIX with business rules so the LLM
# applies them when generating SQL for every query.
#
# SQL_PREFIX already contains:
#   - instructions to use the SQL tools
#   - a reminder to only query existing columns
#   - a reminder to limit results
#
# We prepend our domain rules so they take priority.

_BUSINESS_RULES = """You are a helpful data analyst assistant for a retail company.

Business rules — apply these to EVERY query without exception:
- NEVER include orders with status = 'cancelled' when calculating sales, quantities, or revenue.
- "sold", "top products", "best sellers", "revenue" always mean non-cancelled orders only.
  Always add the filter: WHERE orders.status != 'cancelled'
- Valid order statuses are: pending, shipped, delivered, cancelled.
- "last month" means the past 30 days from today (use NOW() - INTERVAL '30 days').
- "yesterday" means the previous calendar day (use CURRENT_DATE - 1).
- "this week" means the past 7 days (use NOW() - INTERVAL '7 days').
- For sales volume questions, SUM(order_items.quantity) grouped by product.
- For revenue questions, SUM(order_items.quantity * order_items.unit_price).

"""

# Full prompt = our business rules + the standard LangChain SQL agent instructions
AGENT_PREFIX = _BUSINESS_RULES + SQL_PREFIX


def build_chain() -> object:
    """Build and return a LangChain SQL agent connected to PostgreSQL via Groq.

    Reads all connection parameters and tuning knobs from environment variables
    so no credentials are hardcoded. Raises ``KeyError`` if a required variable
    (GROQ_API_KEY, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB) is missing.

    Returns:
        A LangChain AgentExecutor ready to accept ``{"input": "<question>"}`` calls.
    """
    # --- LLM ---
    # temperature=0 keeps output deterministic — SQL must be exact, not creative.
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
    llm = ChatGroq(
        model=model,
        temperature=0,
        api_key=SecretStr(os.environ["GROQ_API_KEY"]),
    )
    logger.info("LLM initialised: %s via Groq", model)

    # --- Database ---
    # SQLAlchemy URL with explicit postgresql+psycopg2 dialect.
    # The dialect tells LangChain to use PostgreSQL-specific SQL syntax
    # (e.g. NOW(), INTERVAL, ILIKE) rather than generic ANSI SQL.
    # POSTGRES_HOST defaults to "localhost" so local dev works without Docker.
    db_url = (
        f"postgresql+psycopg2://"
        f"{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@{os.environ.get('POSTGRES_HOST', 'localhost')}"
        f":{os.environ.get('POSTGRES_PORT', '5432')}"
        f"/{os.environ['POSTGRES_DB']}"
    )
    db = SQLDatabase.from_uri(db_url)
    # db.dialect is passed automatically by create_sql_agent into the {dialect}
    # placeholder inside SQL_PREFIX — it tells the LLM to generate PostgreSQL-
    # specific syntax (NOW(), INTERVAL, ILIKE etc.) rather than generic ANSI SQL.
    logger.info(
        "Database connected: dialect=%s host=%s db=%s",
        db.dialect,
        os.environ.get("POSTGRES_HOST", "localhost"),
        os.environ["POSTGRES_DB"],
    )

    # --- Agent ---
    # top_k injects a LIMIT clause into generated queries so a question like
    # "show me all orders" never returns thousands of rows, overflows the LLM
    # context window, or produces a slow response.
    # Configurable via MAX_ROWS env var (default 50).
    top_k = int(os.environ.get("MAX_ROWS", 50))
    logger.info("SQL agent top_k (row cap) set to %d", top_k)
    logger.debug("Agent prompt prefix:\n%s", AGENT_PREFIX)

    # agent_type="tool-calling": uses Groq's native function-calling API instead
    # of the legacy ReAct text-parsing loop. Much more reliable with Llama models —
    # the ReAct format requires strict Thought/Action/Observation text which Llama
    # occasionally mis-formats, causing "observation missing" errors.
    #
    # prefix is a top-level param — it gets formatted with {dialect} and {top_k}
    # automatically before being passed to the LLM as a SystemMessage.
    agent = create_sql_agent(
        llm=llm,
        db=db,
        agent_type="tool-calling",
        top_k=top_k,
        prefix=AGENT_PREFIX,
        verbose=False,          # flip to True to log every tool-calling step
        agent_executor_kwargs={"handle_parsing_errors": True},
    )

    logger.info("SQL agent ready")
    return agent
