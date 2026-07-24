"""Read-only connectivity check. Verifies the Atlas connection and lists
collections with document counts. Run from backend/:  py check_db.py
"""
from app.config import get_settings
from app.db import get_client


def main() -> None:
    s = get_settings()
    db = get_client()[s.mongo_db]
    names = sorted(db.list_collection_names())
    print(f"Connected to '{s.mongo_db}' — {len(names)} collections:\n")
    for name in names:
        marker = "  (semantic)" if name in s.rag_collection_list else ""
        print(f"  {name:32} {db[name].estimated_document_count():>8}{marker}")


if __name__ == "__main__":
    main()
