"""MongoDB connection helpers."""
from pymongo import MongoClient
from pymongo.collection import Collection

from .config import get_settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(get_settings().mongodb_uri)
    return _client


def get_collection() -> Collection:
    s = get_settings()
    return get_client()[s.mongo_db][s.mongo_collection]
