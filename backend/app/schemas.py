"""Request/response models for the API."""
from typing import Any

from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str


class Source(BaseModel):
    id: str
    collection: str
    text: str


class QueryResponse(BaseModel):
    answer: str
    route: str
    query: dict[str, Any] | None = None
    rows: list[dict[str, Any]] | None = None
    sources: list[Source] | None = None


class IngestResponse(BaseModel):
    ingested: int
    by_collection: dict[str, int]
