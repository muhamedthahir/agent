"""Hybrid agent: route -> retrieve (query and/or semantic) -> Claude answers.

Combines the text-to-Mongo-query path and the vector-RAG path based on the
router's decision, then asks Claude to answer grounded in whatever context
was gathered.
"""
import json
from datetime import datetime
from functools import lru_cache
from typing import Any

from langchain_anthropic import ChatAnthropic

from . import mongo_query, rag, router
from .config import get_settings
from .history import as_messages, current_date_context

_SYSTEM = (
    "You answer questions about training-operations records using ONLY the "
    "context provided below (system data and/or retrieved text snippets). "
    "If the context does not contain the answer, say so plainly rather than "
    "guessing. Be concise and cite concrete values from the data. "
    "If the results contain multiple distinct entities that could each be "
    "what the user meant (e.g. several trainers with similar names from a "
    "partial-name match), do NOT arbitrarily pick one or merge their data — "
    "list each candidate with its unique key (employeeId/rollNumber/etc.) and "
    "name, and ask the user which one they meant. "
    "\n\n"
    "Write for a non-technical audience — anyone using this app, not just "
    "engineers. Never mention databases, collections, fields, queries, "
    "pipelines, schemas, or any other implementation detail; describe "
    "things in plain business terms instead (e.g. say 'no resignation "
    "reason is recorded for this trainer' rather than 'the trainers "
    "collection has no resignationReason field'). If information genuinely "
    "isn't tracked anywhere in the system, just say it isn't recorded — "
    "don't speculate about which internal table or system it might live in. "
    "\n\n"
    "Format the answer as Markdown: **bold** the key values the user asked "
    "for (names, counts, dates, statuses), *italicize* secondary/contextual "
    "details, and use a short bullet or numbered list when returning 2-3 "
    "items instead of a run-on sentence. When the answer involves several "
    "records/rows each with more than one attribute (e.g. a list of "
    "trainers with their department and status, or a list of leave "
    "requests with dates and approvers), render it as a Markdown table "
    "with a header row instead of a list or prose — tables are much easier "
    "to scan. Don't overdo formatting — only highlight what's actually "
    "worth drawing the eye to. "
    "The retrieved context may contain results from more than one query "
    "(labeled 'query 1 of N', 'query 2 of N', ...) — when it does, that "
    "split was made specifically because answering requires comparing the "
    "two datasets yourself (e.g. matching rows across them by a shared "
    "date/trainer/id field to find what's present in one but missing from "
    "the other), not because they are unrelated topics. Do that comparison "
    "before answering. "
    "Trust the '(query already filtered by: ...)' note shown with each "
    "result as ground truth for what's already been matched, even when "
    "the individual rows don't repeat that field. In particular, the "
    "weekly timetable has no date field by design — it's a recurring "
    "weekday template — so a filter matching today's weekday (see the "
    "current-date context below) IS today's schedule; do not ask for a "
    "date field that data doesn't have, and do not claim you lack "
    "information that's already shown in the filter note."
)


def _contains_value(node: Any, value: str) -> bool:
    if isinstance(node, dict):
        return any(_contains_value(v, value) for v in node.values())
    if isinstance(node, list):
        return any(_contains_value(v, value) for v in node)
    return node == value


def _filters_summary(pipeline: list[dict[str, Any]]) -> str:
    """Surface the pipeline's own $match filters alongside its rows, so the
    answer step knows what was already filtered even when the $project
    stage drops the filtered field from the returned rows (e.g. filtering
    on date, or on a schedules.day weekday, but not projecting it back
    out). Deterministically flags a weekday filter that equals today's
    actual weekday, rather than leaving that inference to the answer LLM.
    """
    matches = [s["$match"] for s in pipeline if "$match" in s]
    if not matches:
        return ""
    today_weekday = datetime.now().strftime("%A")
    today_note = f" — {today_weekday} is today's date" if any(
        _contains_value(m, today_weekday) for m in matches
    ) else ""
    return (
        f" (query already filtered by: "
        f"{json.dumps(matches, ensure_ascii=False, default=str)}{today_note})"
    )


@lru_cache
def _llm() -> ChatAnthropic:
    s = get_settings()
    return ChatAnthropic(
        model=s.claude_model, max_tokens=s.max_tokens, api_key=s.anthropic_api_key,
        timeout=60,
    )


def answer(question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    route = router.classify(question, history)

    queries: list[dict[str, Any]] | None = None
    sources: list[dict[str, str]] | None = None
    query_error: str | None = None
    context_parts: list[str] = []

    # --- Query path ---
    if route in ("query", "both"):
        try:
            result = mongo_query.run(question, history)
            queries = result["queries"]
            total = len(queries)
            for i, r in enumerate(queries, start=1):
                label = (
                    f"collection '{r['collection']}'"
                    if total == 1
                    else f"query {i} of {total}, collection '{r['collection']}'"
                )
                context_parts.append(
                    f"Database query results ({label}){_filters_summary(r['pipeline'])}:\n"
                    f"{json.dumps(r['rows'], ensure_ascii=False)}"
                )
        except mongo_query.ClarificationNeeded as e:
            # Not a failure — the model needs more info. Hand its question
            # back verbatim instead of running it through query/answer
            # synthesis (there's nothing to synthesize yet).
            return {
                "answer": str(e),
                "route": route,
                "queries": None,
                "sources": None,
                "query_error": None,
            }
        except mongo_query.QueryError as e:
            query_error = str(e)
        except Exception as e:  # execution/connection errors
            query_error = f"Unexpected database error: {e}"
        if query_error:
            # Surfaced via query_error to the caller, not passed off as
            # normal context — a failed/timed-out join must read as an
            # explicit error, not a plausible-looking "no data" answer.
            context_parts.append(
                "[The database query failed and returned no data — do not "
                "claim there is no matching data; tell the user the query "
                "failed.]"
            )

    # --- Semantic path ---
    if route in ("semantic", "both"):
        docs = rag.retrieve(question)
        sources = [
            {
                "id": str(d.metadata.get("_id", "")),
                "collection": str(d.metadata.get("collection", "")),
                "text": d.page_content,
            }
            for d in docs
        ]
        if docs:
            snippets = "\n\n---\n\n".join(d.page_content for d in docs)
            context_parts.append(f"Retrieved text snippets:\n{snippets}")

    context = "\n\n====\n\n".join(context_parts) or "(no context available)"
    system = f"{_SYSTEM}\n\n{current_date_context()}"
    msg = _llm().invoke(
        [("system", system), *as_messages(history),
         ("human", f"Context:\n{context}\n\nQuestion: {question}")]
    )
    answer_text = msg.content if isinstance(msg.content, str) else str(msg.content)

    return {
        "answer": answer_text,
        "route": route,
        "queries": queries,
        "sources": sources,
        "query_error": query_error,
    }
