"""FastAPI entrypoint for the MyAgent hybrid agent."""
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import agent
from . import ingest as ingest_module
from .config import get_settings
from .db import ensure_indexes
from .schemas import IngestResponse, QueryRequest, QueryResponse


def configure_environment() -> None:
    """Export settings that LangChain/LangSmith read from os.environ."""
    s = get_settings()
    if s.anthropic_api_key:
        os.environ.setdefault("ANTHROPIC_API_KEY", s.anthropic_api_key)
    if s.hf_token:
        os.environ.setdefault("HF_TOKEN", s.hf_token)
    if s.langsmith_tracing and s.langsmith_api_key:
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = s.langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = s.langsmith_project


configure_environment()
settings = get_settings()

app = FastAPI(title="MyAgent Hybrid Agent API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    print('Adding indexes')
    ensure_indexes()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest", response_model=IngestResponse)
def ingest_endpoint() -> dict:
    """Embed the text-heavy collections for the semantic path."""
    return ingest_module.ingest()


@app.post("/query", response_model=QueryResponse)
def query_endpoint(req: QueryRequest) -> dict:
    history = [h.model_dump() for h in req.history] if req.history else []
    return agent.answer(req.question, history)
