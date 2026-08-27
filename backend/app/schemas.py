"""Request/response models for the API."""
from typing import Any, Literal

from pydantic import BaseModel


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class QueryRequest(BaseModel):
    question: str
    history: list[HistoryTurn] | None = None


class Source(BaseModel):
    id: str
    collection: str
    text: str


class QueryResult(BaseModel):
    collection: str
    pipeline: list[dict[str, Any]]
    rows: list[dict[str, Any]]


class QueryResponse(BaseModel):
    answer: str
    route: str
    queries: list[QueryResult] | None = None
    sources: list[Source] | None = None
    query_error: str | None = None


class IngestResponse(BaseModel):
    ingested: int
    by_collection: dict[str, int]
