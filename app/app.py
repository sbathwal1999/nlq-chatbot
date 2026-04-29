"""
app.py — Chainlit entrypoint

This is the main application file. Chainlit reads this file and:
  - Serves the chat UI at http://localhost:8000
  - Calls on_chat_start() once when a new session opens
  - Calls on_message() for every user message

Flow per message:
  user input → SQL guard (if input looks like SQL) → agent (with history) → answer
"""

import logging
from typing import Any

import chainlit as cl

from chain import build_chain
from guard import is_safe

# Configure logging once at import time.
# Chainlit captures stdout, so we write to the standard logging stream instead.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# SQL-style keywords that indicate the user is typing raw SQL rather than a
# natural language question. Used to decide whether to run the guard check.
_SQL_FIRST_WORDS = {
    "SELECT", "WITH", "DROP", "DELETE", "UPDATE",
    "INSERT", "ALTER", "TRUNCATE", "CREATE",
}

# How many previous Q&A turns to include as context with each new question.
# Too many turns inflate the prompt and slow down the LLM; 5 is a good balance.
_HISTORY_WINDOW = 5


def _looks_like_sql(text: str) -> bool:
    """Return True if the first word of *text* is a SQL keyword.

    Natural language questions ("What were the top products?") never start
    with these words, so this is a cheap pre-filter before the full guard check.

    Args:
        text: The stripped user message.

    Returns:
        True if the message appears to be raw SQL.
    """
    tokens = text.split()
    return bool(tokens) and tokens[0].upper() in _SQL_FIRST_WORDS


def _build_prompt_with_history(question: str, history: list[dict[str, str]]) -> str:
    """Prepend recent conversation history to the current question.

    The LangChain SQL agent is stateless — it has no built-in memory between
    calls. We work around this by serialising the last N turns as plain text
    and prefixing them to the question so the LLM has context for follow-ups
    like "What about yesterday?" or "Which product was most sold?".

    Args:
        question: The current user question.
        history:  List of recent turns, each a dict with "question" and "answer".

    Returns:
        A combined prompt string with history prepended (or just the question
        if there is no history yet).
    """
    if not history:
        return question

    lines = ["Previous conversation:"]
    for turn in history:
        lines.append(f"  User: {turn['question']}")
        lines.append(f"  Assistant: {turn['answer']}")
    lines.append(f"\nCurrent question: {question}")

    return "\n".join(lines)


@cl.on_chat_start
async def on_chat_start() -> None:
    """Initialise a new chat session.

    Builds the SQL agent and stores it — along with an empty history list —
    in the Chainlit user session. Any misconfiguration (missing env vars,
    bad DB creds) surfaces here immediately rather than silently at startup.
    """
    logger.info("New chat session started")

    try:
        agent = build_chain()
    except Exception as exc:
        logger.exception("Failed to build SQL agent: %s", exc)
        await cl.Message(
            content="Failed to connect to the database or LLM. Please check the server logs."
        ).send()
        return

    # cl.user_session is scoped per browser session — no cross-user leakage.
    cl.user_session.set("agent", agent)
    # history holds the last _HISTORY_WINDOW turns as {question, answer} dicts.
    cl.user_session.set("history", [])
    logger.info("Agent and history store initialised for session")

    await cl.Message(
        content=(
            "Hello! I can answer questions about your data in plain English.\n\n"
            "Try asking something like:\n"
            "- *What were the top 5 products sold last month?*\n"
            "- *How many orders are pending?*\n"
            "- *Show me customers who haven't ordered in 90 days*"
        )
    ).send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Handle an incoming user message.

    Steps:
    1. If the message looks like raw SQL, run it through the safety guard.
    2. Prepend recent chat history to the question for context-aware follow-ups.
    3. Pass the enriched prompt to the SQL agent.
    4. Save the Q&A turn to history and send the answer back to the UI.

    Args:
        message: The Chainlit message object containing the user's input.
    """
    question = message.content.strip()
    logger.info("Received message: %.120s", question)

    # Only run the SQL guard when the input looks like a SQL statement.
    # Plain English questions pass straight through.
    if _looks_like_sql(question) and not is_safe(question):
        logger.warning("Blocked unsafe SQL input from user: %.120s", question)
        await cl.Message(
            content="Sorry, I can only answer read-only questions about the data."
        ).send()
        return

    agent: Any = cl.user_session.get("agent")
    history: list[dict[str, str]] = cl.user_session.get("history")

    # Build prompt with recent history so the agent understands follow-up questions.
    prompt = _build_prompt_with_history(question, history[-_HISTORY_WINDOW:])
    logger.info("Prompt sent to agent (with %d history turns)", min(len(history), _HISTORY_WINDOW))

    # Show a spinner while the agent thinks.
    # Schema introspection + LLM call typically takes 2–5 seconds.
    async with cl.Step(name="Querying database..."):
        try:
            # agent.invoke() runs the tool-calling agent loop:
            # schema discovery → SQL generation → execution → natural language answer.
            result = await cl.make_async(agent.invoke)({"input": prompt})
            answer = result.get("output", "I couldn't find an answer to that.")
            logger.info("Agent returned answer successfully")
        except Exception as exc:
            logger.exception("Agent error: %s", exc)
            answer = f"Something went wrong while querying the database: {exc}"

    # Persist this turn to history for future context.
    # We store the original question (not the enriched prompt) to keep history clean.
    history.append({"question": question, "answer": answer})
    cl.user_session.set("history", history)
    logger.info("History updated — total turns: %d", len(history))

    await cl.Message(content=answer).send()
