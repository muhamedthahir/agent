"""Shared per-request context threaded into every LLM call: recent chat
turns (so pronouns/follow-ups resolve) and the current date (so relative
date references resolve without asking the user).

Kept as plain (role, content) dicts/strings rather than LangChain message
objects so callers (router, query generation, final answer) don't need to
import LangChain just to use these.
"""
from datetime import datetime, timedelta

# Cap how many prior messages we forward — bounds token cost per call while
# still giving enough context to resolve pronouns/follow-ups like "he" or
# "and on Tuesday?".
MAX_TURNS = 6


def as_messages(history: list[dict[str, str]] | None) -> list[tuple[str, str]]:
    if not history:
        return []
    trimmed = history[-MAX_TURNS:]
    return [("human" if h["role"] == "user" else "ai", h["content"]) for h in trimmed]


def current_date_context() -> str:
    """Fresh on every call (not baked into a cached prompt) so 'today' stays
    correct across a long-running process."""
    now = datetime.now()
    today = now.date()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return (
        f"Current date/time: {now.isoformat(timespec='seconds')} "
        f"({today.strftime('%A')}). This week (Mon-Sun): {monday.isoformat()} "
        f"to {sunday.isoformat()}. Resolve relative date references ('today', "
        "'yesterday', 'this week', 'last week', 'this month', 'last month') "
        "against this date yourself — do not ask the user for the date."
    )
