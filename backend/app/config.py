"""Central, env-driven configuration.

Every setting is read from environment variables (or the local .env file),
so nothing is hardcoded and secrets stay out of source control.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Anthropic / Claude
    anthropic_api_key: str = ""
    claude_model: str = "claude-haiku-4-5"          # answer + query generation
    router_model: str = "claude-haiku-4-5"          # cheap routing classifier
    max_tokens: int = 2048

    # MongoDB
    mongodb_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "toms"

    # Query path (text-to-Mongo-query)
    max_result_docs: int = 50                       # hard cap on rows returned

    # Semantic path (vector RAG) — torch-free embeddings via fastembed
    rag_collections: str = "tickets,feedbackresponses,topic_tracker_entries,subjects"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    chroma_dir: str = "./chroma_store"
    retriever_k: int = 4

    # LangSmith tracing (optional)
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "myagent"

    # CORS
    frontend_origin: str = "http://localhost:5173"

    @property
    def rag_collection_list(self) -> list[str]:
        return [c.strip() for c in self.rag_collections.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
