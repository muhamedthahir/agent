# MyAgent — Hybrid agent over MongoDB (TOMS) with Claude

An agent that answers questions about the **TOMS** MongoDB database. A cheap
**router** decides, per question, how to answer:

- **query path** — Claude writes a read-only MongoDB aggregation, we run it
  (`pymongo`) and Claude explains the rows. For precise/relational questions
  ("how many leaves are pending?", "who teaches CSE-A on Monday S1?").
- **semantic path** — vector retrieval (RAG) over the text-heavy collections.
  For free-text questions ("what are trainers reporting in tickets?").
- **both** — run both and let Claude synthesize.

**Stack**
- **Backend:** Python · FastAPI
- **Orchestration:** LangChain · traced by **LangSmith** (optional)
- **LLM:** Claude via `langchain-anthropic` (`claude-haiku-4-5` for testing,
  `claude-opus-4-8` for quality)
- **Embeddings:** **fastembed** (ONNX, local, no API key, **no torch**)
- **Vector store:** Chroma (local, on disk)
- **Data source:** MongoDB Atlas (`toms`)
- **Frontend:** React + TypeScript (Vite)

The router is a classification-only step (not Anthropic tool-calling); it can
be upgraded to a full tool-calling agent later.

---

## Prerequisites
- Python 3.10+ (invoked as `py` on this machine)
- Node.js 18+
- An `ANTHROPIC_API_KEY` with billing/credit
- Access to the MongoDB (`MONGODB_URI`)

---

## Backend setup

```bash
cd backend
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Configure secrets (the real `.env` is git-ignored):

```bash
copy .env.example .env
```

Set `ANTHROPIC_API_KEY` and `MONGODB_URI` in `.env`.

Verify the DB connection (read-only, lists collection counts):

```bash
py check_db.py
```

Run the API:

```bash
uvicorn app.main:app --reload --port 8000
```

- `GET  /health` — health check
- `POST /ingest` — embed the text-heavy collections for the semantic path
- `POST /query`  — `{ "question": "..." }` → `{ answer, route, query?, rows?, sources? }`

> First `/ingest` or a semantic `/query` downloads the fastembed model
> (~50 MB) once. No torch, no gigabyte downloads.

---

## Frontend setup

```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Open http://localhost:5173, click **Rebuild search index** once (enables the
semantic path), then ask questions. Each answer shows its route and,
expandable, the generated Mongo query / rows / retrieved sources.

---

## Configuration (backend `.env`)

| Variable | Purpose | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API key (**required**) | — |
| `CLAUDE_MODEL` | Answer + query-generation model | `claude-haiku-4-5` |
| `ROUTER_MODEL` | Cheap routing classifier | `claude-haiku-4-5` |
| `MAX_TOKENS` | Max answer tokens | `2048` |
| `MONGODB_URI` | Mongo connection string | `mongodb://localhost:27017` |
| `MONGO_DB` | Database name | `toms` |
| `MAX_RESULT_DOCS` | Hard cap on query rows | `50` |
| `RAG_COLLECTIONS` | Collections embedded for semantic search | `tickets,feedbackresponses,topic_tracker_entries,subjects` |
| `EMBEDDING_MODEL` | fastembed model | `BAAI/bge-small-en-v1.5` |
| `CHROMA_DIR` | Vector store path | `./chroma_store` |
| `RETRIEVER_K` | Docs retrieved per semantic query | `4` |
| `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` | Tracing (optional) | `false` / — / `myagent` |
| `FRONTEND_ORIGIN` | CORS origin | `http://localhost:5173` |

---

## Safety
- The query path is **read-only**: generated pipelines are rejected if they
  contain `$out`, `$merge`, `$function`, `$accumulator`, or `$where`, and every
  result set is capped at `MAX_RESULT_DOCS`.
- **Recommended:** point `MONGODB_URI` at a **read-only** MongoDB user so even
  a bug can't mutate data.
- `.env` is git-ignored; never commit real keys. If a key or DB credential is
  exposed, rotate it.

---

## Project layout
```
backend/
  app/
    config.py       # env settings
    db.py           # MongoDB client
    schema.py       # distilled TOMS schema for query generation
    mongo_query.py  # text-to-Mongo-query path (read-only)
    rag.py          # semantic path (fastembed + Chroma)
    router.py       # per-question route classifier
    agent.py        # orchestrates route → retrieve → answer
    main.py         # FastAPI app
  check_db.py       # read-only connection check
  requirements.txt
frontend/           # React + TypeScript (Vite)
```

## Extending later
- Upgrade the router to a **tool-calling** agent (Claude orchestrates the
  query and retrieval tools directly) via LangGraph.
- Add name→ObjectId resolution helpers for trickier relational questions.
