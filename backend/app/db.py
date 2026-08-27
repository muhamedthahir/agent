"""MongoDB connection helpers."""
import logging

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import OperationFailure

from .config import get_settings

log = logging.getLogger(__name__)

_client: MongoClient | None = None

# Fields the query-generation prompt (schema.py) marks as unique business
# keys, soft string links, or ObjectId refs commonly used as $lookup keys.
# Indexing these keeps joins from falling back to a full collection scan.
# `unique=True` mirrors the fields schema.py marks with "*".
_INDEXES: dict[str, list[tuple[str, ...] | str]] = {
    "schools": ["code"],
    "departments": ["code", "school"],
    "students": ["rollNumber", "section", "batch"],
    "trainers": ["employeeId", "scheduleTrainerCodes", "department"],
    "users": ["email", "trainer"],
    "subjects": ["code"],
    "schedules": ["trainerCode", "subject", "venue"],
    "leaves": ["trainer", "status"],
    "classcancellations": ["schedules"],
    "attendances": ["trainer", "student", "schedule"],
    "trainerdailyattendances": [("trainer", "date")],
    "topic_tracker_entries": [("schedule", "date"), "trainer", "subject"],
    "tickets": ["ticketId", "trainer", "raisedBy"],
    "feedbackforms": ["monthKey"],
    "feedbackresponses": ["rollNumber", "form", "trainer"],
    "notifications": ["recipient"],
    "app_settings": ["key"],
}

_UNIQUE_FIELDS = {
    ("schools", "code"),
    ("departments", "code"),
    ("students", "rollNumber"),
    ("trainers", "employeeId"),
    ("users", "email"),
    ("subjects", "code"),
    ("tickets", "ticketId"),
    ("feedbackforms", "monthKey"),
    ("app_settings", "key"),
    ("trainerdailyattendances", ("trainer", "date")),
    ("topic_tracker_entries", ("schedule", "date")),
}


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(get_settings().mongodb_uri)
    return _client


def get_collection() -> Collection:
    s = get_settings()
    return get_client()[s.mongo_db][s.mongo_collection]


def ensure_indexes() -> None:
    """Create indexes on known join/lookup keys, idempotently.

    Called once at startup. Safe to re-run — an equivalent index already
    existing is a no-op. A pre-existing index with the same auto-generated
    name but different options (e.g. unique) is logged and skipped rather
    than crashing startup, since it already serves the same lookup.
    """
    s = get_settings()
    db = get_client()[s.mongo_db]
    for collection, fields in _INDEXES.items():
        col = db[collection]
        for field in fields:
            keys = [(f, ASCENDING) for f in field] if isinstance(field, tuple) else [(field, ASCENDING)]
            unique = (collection, field) in _UNIQUE_FIELDS
            try:
                col.create_index(keys, unique=unique)
            except OperationFailure as e:
                log.warning("Skipping index %s.%s: %s", collection, field, e)
