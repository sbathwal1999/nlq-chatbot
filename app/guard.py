"""
guard.py — SQL safety filter

Blocks any SQL that would mutate or destroy data before it reaches the database.
The LangChain SQL agent can occasionally generate DML/DDL if the LLM misbehaves,
and users can also type raw SQL directly — so we intercept both cases here as a
hard stop before anything reaches PostgreSQL.

Only SELECT statements (including CTEs that resolve to a SELECT) are allowed through.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Matches the first keyword of a destructive SQL statement.
# Applied after stripping comments so inline tricks like `/* */DROP` are caught.
_BLOCKED_PATTERN = re.compile(
    r"^\s*(DROP|DELETE|UPDATE|INSERT|ALTER|TRUNCATE|CREATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)

# Matches a leading CTE block so we can check what comes after it.
# Handles `WITH cte_name AS ( ... ) SELECT ...` patterns.
_CTE_PREFIX = re.compile(
    r"^WITH\s+\w+.*?\)\s*",
    re.DOTALL | re.IGNORECASE,
)


def is_safe(sql: str) -> bool:
    """Return True only if the SQL is a read-only SELECT (or CTE → SELECT) statement.

    Args:
        sql: The raw SQL string to validate. May contain comments.

    Returns:
        True if the statement is safe to execute, False otherwise.
    """
    # Strip single-line and multi-line SQL comments before pattern matching
    clean = re.sub(r"--.*$", "", sql, flags=re.MULTILINE).strip()
    clean = re.sub(r"/\*.*?\*/", "", clean, flags=re.DOTALL).strip()

    if not clean:
        logger.warning("Received empty SQL after stripping comments — blocking.")
        return False

    # Reject any statement that starts with a known destructive keyword
    if _BLOCKED_PATTERN.match(clean):
        logger.warning("Blocked destructive SQL statement: %.120s", clean)
        return False

    # Strip a leading CTE (WITH ... AS (...)) and check that the body is a SELECT
    body = _CTE_PREFIX.sub("", clean).strip()
    if not body.upper().startswith("SELECT"):
        logger.warning("Blocked non-SELECT SQL statement: %.120s", clean)
        return False

    return True
