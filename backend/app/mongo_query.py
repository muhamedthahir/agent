"""Text-to-MongoDB-query path.

Claude turns a natural-language question into a read-only aggregation
pipeline; we validate it (no writes), execute it via pymongo with a hard row
cap, and hand the rows back to the agent for a natural-language answer.
"""
import json
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from bson import ObjectId
from langchain_anthropic import ChatAnthropic

from .config import get_settings
from .db import get_client
from .schema import COLLECTIONS, SCHEMA_TEXT

# Aggregation operators that can write or execute code — never allowed.
FORBIDDEN = {"$out", "$merge", "$function", "$accumulator", "$where"}


class QueryError(Exception):
    """Raised when a generated query is unsafe or unusable."""


@lru_cache
def _llm() -> ChatAnthropic:
    s = get_settings()
    return ChatAnthropic(
        model=s.claude_model, max_tokens=s.max_tokens, api_key=s.anthropic_api_key,
        timeout=60,
    )


_SYSTEM = (
    "You translate questions into MongoDB aggregation queries for the TOMS "
    "database. Output ONLY a JSON object, no prose, no markdown fences, in the "
    'form: {"collection": "<name>", "pipeline": [ ...stages... ]}. '
    "Use read-only stages only ($match, $lookup, $group, $project, $sort, "
    "$limit, $count, $unwind, $addFields). Never use $out, $merge, $function, "
    "$where. Prefer $lookup to join across collections. Return a small, "
    "relevant projection.\n\n" + SCHEMA_TEXT
)


def _extract_json(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise QueryError(f"No JSON object in model output: {text[:200]}")
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise QueryError(f"Could not parse query JSON: {e}")


def generate_query(question: str) -> dict[str, Any]:
    msg = _llm().invoke([("system", _SYSTEM), ("human", question)])
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    return _extract_json(content)


def _scan_forbidden(node: Any) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in FORBIDDEN:
                raise QueryError(f"Forbidden operator: {k}")
            _scan_forbidden(v)
    elif isinstance(node, list):
        for item in node:
            _scan_forbidden(item)


def validate_query(q: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    collection = q.get("collection")
    pipeline = q.get("pipeline")
    if collection not in COLLECTIONS:
        raise QueryError(f"Unknown collection: {collection!r}")
    if not isinstance(pipeline, list) or not all(isinstance(s, dict) for s in pipeline):
        raise QueryError("pipeline must be a list of stage objects")
    _scan_forbidden(pipeline)
    # Always cap the result set as a final stage.
    pipeline = pipeline + [{"$limit": get_settings().max_result_docs}]
    return collection, pipeline


def _serialize(obj: Any) -> Any:
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def execute_query(collection: str, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    s = get_settings()
    col = get_client()[s.mongo_db][collection]
    rows = list(col.aggregate(pipeline, maxTimeMS=15000))
    return [_serialize(r) for r in rows]


def run(question: str) -> dict[str, Any]:
    """Full query path: generate -> validate -> execute."""
    raw = generate_query(question)
    collection, pipeline = validate_query(raw)
    rows = execute_query(collection, pipeline)
    return {"collection": collection, "pipeline": pipeline, "rows": rows}
