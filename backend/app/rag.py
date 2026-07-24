"""Semantic (vector) retrieval path.

Torch-free: embeddings run via fastembed (ONNX). Documents from the
text-heavy collections are embedded into Chroma by ingest.py; here we just
retrieve the most similar snippets for a question.
"""
from functools import lru_cache

from langchain_chroma import Chroma
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_core.documents import Document

from .config import get_settings

_COLLECTION = "toms"


@lru_cache
def get_embeddings() -> FastEmbedEmbeddings:
    # ONNX-based; first call downloads a small model (~50 MB). No torch.
    return FastEmbedEmbeddings(model_name=get_settings().embedding_model)


@lru_cache
def get_vectorstore() -> Chroma:
    s = get_settings()
    return Chroma(
        collection_name=_COLLECTION,
        embedding_function=get_embeddings(),
        persist_directory=s.chroma_dir,
    )


def retrieve(question: str) -> list[Document]:
    k = get_settings().retriever_k
    return get_vectorstore().as_retriever(search_kwargs={"k": k}).invoke(question)
