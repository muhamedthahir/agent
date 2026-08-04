"""Diagnose why `app.main` fails to import or the server won't start.

Writes everything to diagnose_log.txt (next to this file) AND prints to
stdout, so output is captured no matter how the shell handles redirection.

Run from backend/ with the venv active:   py diagnose.py
"""
import sys
import traceback
from pathlib import Path

LOG_PATH = Path(__file__).parent / "diagnose_log.txt"
lines: list[str] = []


def log(msg: str) -> None:
    lines.append(msg)
    print(msg)


def try_import(label: str, fn) -> bool:
    try:
        fn()
        log(f"[OK]   {label}")
        return True
    except Exception:
        log(f"[FAIL] {label}")
        log(traceback.format_exc())
        return False


log(f"Python executable: {sys.executable}")
log(f"Python version:    {sys.version}")
log(f"CWD:                {Path.cwd()}")
log(f"This file:          {Path(__file__).resolve()}")
log("")

log("--- Step 1: third-party package imports ---")
try_import("fastapi", lambda: __import__("fastapi"))
try_import("pymongo", lambda: __import__("pymongo"))
try_import("pydantic_settings", lambda: __import__("pydantic_settings"))
try_import("langchain_anthropic", lambda: __import__("langchain_anthropic"))
try_import("langchain_chroma", lambda: __import__("langchain_chroma"))
try_import("langchain_community.embeddings", lambda: __import__(
    "langchain_community.embeddings", fromlist=["FastEmbedEmbeddings"]
))
try_import("fastembed", lambda: __import__("fastembed"))
try_import("bson (from pymongo)", lambda: __import__("bson"))
log("")

log("--- Step 2: app package imports (in dependency order) ---")
ok = True
ok &= try_import("app.config", lambda: __import__("app.config"))
ok &= try_import("app.db", lambda: __import__("app.db"))
ok &= try_import("app.schema", lambda: __import__("app.schema"))
ok &= try_import("app.rag", lambda: __import__("app.rag"))
ok &= try_import("app.mongo_query", lambda: __import__("app.mongo_query"))
ok &= try_import("app.router", lambda: __import__("app.router"))
ok &= try_import("app.agent", lambda: __import__("app.agent"))
ok &= try_import("app.ingest", lambda: __import__("app.ingest"))
ok &= try_import("app.schemas", lambda: __import__("app.schemas"))
log("")

log("--- Step 3: app.main (the actual FastAPI app) ---")
try_import("app.main", lambda: __import__("app.main"))
log("")

if ok:
    log("--- Step 4: settings sanity check ---")
    try:
        from app.config import get_settings
        s = get_settings()
        log(f"anthropic_api_key set: {bool(s.anthropic_api_key)} (len={len(s.anthropic_api_key)})")
        log(f"mongodb_uri:           {s.mongodb_uri[:20]}...")
        log(f"mongo_db:              {s.mongo_db}")
    except Exception:
        log(traceback.format_exc())

log("")
log(f"Full log written to: {LOG_PATH.resolve()}")
LOG_PATH.write_text("\n".join(lines), encoding="utf-8")
