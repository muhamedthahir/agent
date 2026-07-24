"""Router: the conditional-agent brain.

A cheap Claude call classifies each question into one of three retrieval
routes. This is NOT Anthropic tool-calling — just a classification + Python
branching, so it stays simple and predictable.
"""
from functools import lru_cache
from typing import Literal

from langchain_anthropic import ChatAnthropic

from .config import get_settings

Route = Literal["query", "semantic", "both"]

_SYSTEM = (
    "Classify the user's question about a training-operations database into "
    "exactly ONE routing label. Reply with only the label word.\n"
    "- query: precise/relational/countable questions answerable by a database "
    "query (counts, filters, lookups, 'how many', 'who teaches', 'list X where').\n"
    "- semantic: open-ended questions over free text (summaries, themes, "
    "'what are people saying', complaints, feedback sentiment).\n"
    "- both: needs precise data AND free-text understanding.\n"
    "Answer with one word: query, semantic, or both."
)


@lru_cache
def _llm() -> ChatAnthropic:
    s = get_settings()
    return ChatAnthropic(
        model=s.router_model, max_tokens=8, api_key=s.anthropic_api_key, timeout=30,
    )


def classify(question: str) -> Route:
    msg = _llm().invoke([("system", _SYSTEM), ("human", question)])
    text = (msg.content if isinstance(msg.content, str) else str(msg.content)).lower()
    if "both" in text:
        return "both"
    if "semantic" in text:
        return "semantic"
    if "query" in text:
        return "query"
    return "both"  # safe default when the classifier is unclear
