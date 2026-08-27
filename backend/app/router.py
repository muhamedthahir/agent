"""Router: the conditional-agent brain.

A cheap Claude call classifies each question into one of three retrieval
routes. This is NOT Anthropic tool-calling — just a classification + Python
branching, so it stays simple and predictable.
"""
from functools import lru_cache
from typing import Literal

from langchain_anthropic import ChatAnthropic

from .config import get_settings
from .history import as_messages

Route = Literal["query", "semantic", "both"]

_SYSTEM = (
    "Classify the user's question about a training-operations database into "
    "exactly ONE routing label. Reply with only the label word.\n"
    "- query: precise/relational/countable questions answerable by a database "
    "query (counts, filters, lookups, 'how many', 'who teaches', 'list X "
    "where', averages, ratings, statuses, dates). This includes BOTH "
    "feedback collections whenever the question is about their structured "
    "fields: feedbackforms (monthKey, title, status draft/published, "
    "publicSlug) and feedbackresponses (form, monthKey, rating 1-5, "
    "studentName, rollNumber, trainer, createdAt) — counts of responses, "
    "average rating, responses for a given form/month/trainer, published "
    "vs draft forms, etc. are all 'query', NOT 'semantic', just because the "
    "word 'feedback' appears.\n"
    "- semantic: open-ended questions that need reading free-text content "
    "to summarize or interpret (summaries, themes, 'what are people "
    "saying', common complaints, sentiment) — specifically the free-text "
    "fields feedbackresponses.comments and feedbackresponses.answers[].value "
    "(open-ended form answers).\n"
    "- both: needs precise structured data AND free-text understanding "
    "together (e.g. 'what's the average rating and what are people "
    "complaining about').\n"
    "When in doubt between query and semantic, prefer 'both' so the "
    "structured lookup is never skipped.\n"
    "Answer with one word: query, semantic, or both."
)


@lru_cache
def _llm() -> ChatAnthropic:
    s = get_settings()
    return ChatAnthropic(
        model=s.router_model, max_tokens=8, api_key=s.anthropic_api_key, timeout=30,
    )


def classify(question: str, history: list[dict[str, str]] | None = None) -> Route:
    msg = _llm().invoke([("system", _SYSTEM), *as_messages(history), ("human", question)])
    text = (msg.content if isinstance(msg.content, str) else str(msg.content)).lower()
    if "both" in text:
        return "both"
    if "semantic" in text:
        return "semantic"
    if "query" in text:
        return "query"
    return "both"  # safe default when the classifier is unclear
