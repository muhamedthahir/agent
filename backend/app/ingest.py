"""Embed the text-heavy TOMS collections into Chroma for the semantic path.

Each document is rendered to JSON text and keyed by "<collection>:<_id>" so
re-ingesting updates rather than duplicates, and ids never clash across
collections.
"""
import json

from langchain_core.documents import Document

from .config import get_settings
from .db import get_client
from .rag import get_vectorstore


def _doc_to_text(doc: dict) -> str:
    body = {k: v for k, v in doc.items() if k != "_id"}
    return json.dumps(body, default=str, ensure_ascii=False)


def ingest() -> dict:
    s = get_settings()
    db = get_client()[s.mongo_db]

    documents: list[Document] = []
    ids: list[str] = []
    by_collection: dict[str, int] = {}

    for name in s.rag_collection_list:
        count = 0
        for doc in db[name].find({}):
            text = _doc_to_text(doc)
            if not text.strip():
                continue
            uid = f"{name}:{doc.get('_id', '')}"
            documents.append(
                Document(
                    page_content=text,
                    metadata={"collection": name, "_id": str(doc.get("_id", ""))},
                )
            )
            ids.append(uid)
            count += 1
        by_collection[name] = count

    if documents:
        get_vectorstore().add_documents(documents, ids=ids)

    return {"ingested": len(documents), "by_collection": by_collection}
