"""Hybrid agent: route -> retrieve (query and/or semantic) -> Claude answers.

Combines the text-to-Mongo-query path and the vector-RAG path based on the
router's decision, then asks Claude to answer grounded in whatever context
was gathered.
"""
import json
from functools import lru_cache
from typing import Any

from langchain_anthropic import ChatAnthropic

from . import mongo_query, rag, router
from .config import get_settings

_SYSTEM = (
    "You answer questions about the TOMS training-operations database using "
    "ONLY the context provided below (database query results and/or retrieved "
    "text snippets). If the context does not contain the answer, say so plainly "
    "rather than guessing. Be concise and cite concrete values from the data."
)


@lru_cache
def _llm() -> ChatAnthropic:
    s = get_settings()
    return ChatAnthropic(
        model=s.claude_model, max_tokens=s.max_tokens, api_key=s.anthropic_api_key,
        timeout=60,
    )


def answer(question: str) -> dict[str, Any]:
    route = router.classify(question)

    query_result: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None
    sources: list[dict[str, str]] | None = None
    context_parts: list[str] = []

    # --- Query path ---
    if route in ("query", "both"):
        try:
            result = mongo_query.run(question)
            query_result = {"collection": result["collection"], "pipeline": result["pipeline"]}
            rows = result["rows"]
            context_parts.append(
                "Database query results (collection "
                f"'{result['collection']}'):\n{json.dumps(rows, ensure_ascii=False)}"
            )
        except mongo_query.QueryError as e:
            context_parts.append(f"[Query path failed: {e}]")
        except Exception as e:  # execution/connection errors
            context_parts.append(f"[Query execution error: {e}]")

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
    msg = _llm().invoke(
        [("system", _SYSTEM), ("human", f"Context:\n{context}\n\nQuestion: {question}")]
    )
    answer_text = msg.content if isinstance(msg.content, str) else str(msg.content)

    return {
        "answer": answer_text,
        "route": route,
        "query": query_result,
        "rows": rows,
        "sources": sources,
    }
