"""Text-to-MongoDB-query path.

Claude turns a natural-language question into a read-only aggregation
pipeline; we validate it (no writes), execute it via pymongo with a hard row
cap, and hand the rows back to the agent for a natural-language answer.
"""
import json
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from langchain_anthropic import ChatAnthropic
from pymongo.errors import ExecutionTimeout, PyMongoError

from .config import get_settings
from .db import get_client
from .history import as_messages, current_date_context
from .schema import COLLECTIONS, SCHEMA_TEXT

# Aggregation operators that can write or execute code — never allowed.
FORBIDDEN = {"$out", "$merge", "$function", "$accumulator", "$where"}


class QueryError(Exception):
    """Raised when a generated query is unsafe or unusable."""


class ClarificationNeeded(Exception):
    """Raised when the model can't form a query and asks the user something
    instead — not a failure, just needs a reply shown to the user verbatim."""


@lru_cache
def _llm() -> ChatAnthropic:
    s = get_settings()
    return ChatAnthropic(
        model=s.claude_model, max_tokens=s.max_tokens, api_key=s.anthropic_api_key,
        timeout=60,
    )


_MAX_SUBQUERIES = 4

# Total LLM attempts per question: 1 initial try + retries where a concrete
# validation/execution error is fed back to Claude for self-correction (see
# run()). Bounded to cap added latency/cost on a still-broken query.
_MAX_ATTEMPTS = 2

_INTRO = (
    "You translate questions into MongoDB aggregation queries for the TOMS "
    "training-operations database, using the conversation history to "
    "resolve references like pronouns ('he', 'her', 'they') or follow-ups "
    "('and on Tuesday?') to a specific prior entity."
)

# Hard, non-negotiable constraints — kept short and stable.
_SAFETY_RULES = (
    "If the question is clear (on its own or with history), output ONLY a "
    'JSON object, no prose, no markdown fences, in the form: {"queries": '
    '[ {"collection": "<name>", "pipeline": [ ...stages... ]}, ... ] }, max '
    f"{_MAX_SUBQUERIES} entries. Reserve plain-text output (see below) for "
    "when you truly cannot form a query.\n"
    "Use read-only stages only ($match, $lookup, $group, $project, $sort, "
    "$limit, $count, $unwind, $addFields). Never use: "
    + ", ".join(sorted(FORBIDDEN)) + ". "
    "Every entry in \"queries\" must be independently filtered — never an "
    "unfiltered whole-collection scan. Put $match as early as possible, "
    "BUT ONLY for fields that already live on the base collection (plain "
    "fields, or exact equality/$in against a ->ref field's ObjectId "
    "itself). If the filter criterion (e.g. a person's name) lives on the "
    "OTHER side of a ->ref — the base collection only stores the ObjectId, "
    "not the name — you must $lookup that collection FIRST, then $match "
    "on the joined field; a regex against an ObjectId field matches "
    "nothing and fails silently, no error (Example 7). Return a small, "
    "relevant projection."
)

# Compact "how to" guidance for the recurring hard cases. Worked examples
# below carry the detail; keep this to the rule, not a walkthrough.
_DOMAIN_RULES = (
    "Default to a SINGLE entry in \"queries\" (using $lookup inside its "
    "pipeline to join across collections). Only emit more than one entry "
    "when the question genuinely cannot be answered by one pipeline — e.g. "
    "comparing two collections with no clean shared join key, or where "
    "joining would force you to reconstruct data (like calendar dates from "
    "a recurring weekday template) inside the pipeline (Example 3). Each "
    "entry's rows are handed to the answer step together, which does the "
    "actual cross-referencing — you do not need to compute the diff "
    "yourself.\n"
    "When the question names a specific person/entity by name, query for "
    "it directly with a case-insensitive partial regex (Example 1) — do "
    "NOT ask the user whether they meant the name or an ID, and do NOT "
    "require an exact spelling. Multiple matches (e.g. similarly-named "
    "trainers) are fine — return them all with their unique key so the "
    "answer step can ask the user which one, instead of you pre-emptively "
    "asking before even searching. Reserve a clarifying question yourself "
    "(plain text, no JSON) for when there is truly no name/identifier/"
    "entity to search on at all — e.g. an unresolved pronoun with nothing "
    "in history to resolve it against (Example 6). If the collection you're "
    "querying only stores that person as a ->ref (e.g. leaves.trainer is "
    "an ObjectId, not a name), regex-matching the name must happen AFTER "
    "$lookup-ing the referenced collection, never on the ref field itself "
    "(Example 7).\n"
    "schedules vs topic_tracker_entries is a PLAN vs ACTUAL distinction, "
    "NOT a date-range one — don't decide based on 'single day' vs 'range'. "
    "schedules is ONLY for plan/roster/assignment wording ('who's "
    "scheduled/assigned to teach today', 'what's on the timetable') — "
    "match schedules.day against the relevant weekday(s) (Example 4). "
    "Anything about ACTUAL occurrence — 'how many classes were taken/"
    "held', 'who took/conducted a class', attendance, topics covered, "
    "closed vs. pending — must query topic_tracker_entries instead, EVEN "
    "when scoped to a single day like 'today' or 'Monday' (Example 5). "
    "These read almost the same but aren't: 'who's taking classes today' "
    "(future-oriented roster wording, present continuous) is the plan "
    "(Example 4); 'how many classes were taken today' / 'who took a "
    "class' (past tense, an actual-occurrence count/fact) is Example 5 — "
    "when a question could plausibly be read either way, default to "
    "topic_tracker_entries, since it's the ledger that also tells you "
    "whether a planned class actually happened — schedules is just the "
    "template and won't reflect cancellations/leaves/no-shows. For any "
    "actual-occurrence question, compute the concrete ISO date(s) from "
    "the current-date "
    "context and filter topic_tracker_entries.date with $gte/$lte (or an "
    "exact match for one day) — never simulate a date range with a "
    "schedules.day weekday-name $in list; that matches every week/month "
    "on the template and filters nothing.\n"
    "Plain $match fields only accept literal values — never put a "
    "$-prefixed expression (e.g. $dateFromString, $map) as a value inside "
    "$in/$eq/$gt directly under $match (MongoDB rejects this with 'cannot "
    "nest $ under $in'). If a condition needs a computed value, either "
    "precompute it with $addFields and match the resulting plain field, or "
    "wrap the WHOLE condition in {\"$expr\": {...}} (Example 2).\n"
    "Never filter on a field in $match and then drop it from the final "
    "$project — if the question is scoped by a date, status, or name, keep "
    "that field in the projected output so the rows are self-explanatory "
    "and the answer step doesn't have to guess what was already matched.\n"
    "For a plain 'how many'/total-count question, output ONLY $match "
    "(using fields native to the collection) followed by $count — do NOT "
    "add an unrequested breakdown/group-by via $lookup just because it "
    "seems informative (Example 8). This matters because $unwind after a "
    "$lookup SILENTLY DROPS any document whose join found no match, "
    "unless you pass {\"path\": \"$field\", \"preserveNullAndEmptyArrays\": "
    "true} — there is no error, the row just vanishes, and a $count or "
    "$group taken after that point will silently under-report the true "
    "total. Every extra $lookup/$unwind you add beyond what the question "
    "requires is one more chance to quietly corrupt the exact number you "
    "were asked for. If the question DOES explicitly ask for a breakdown "
    "by some attribute, prefer grouping on a field that already lives on "
    "the collection itself (e.g. schedules.subjectCode) over joining to "
    "another collection just to get a nicer label — that avoids the "
    "join-drop risk entirely (Example 9). If a join is unavoidable for the "
    "breakdown, always set preserveNullAndEmptyArrays: true on the "
    "$unwind and bucket the unmatched rows under an explicit key (e.g. "
    "null/'Unknown') so the breakdown still sums to the real total."
)

_EXAMPLES: list[dict[str, Any]] = [
    {
        "question": "what's trainer Muhammed Salman's employee ID and department?",
        "response": {
            "queries": [
                {
                    "collection": "trainers",
                    "pipeline": [
                        {"$match": {"$and": [
                            {"name": {"$regex": "muhammed", "$options": "i"}},
                            {"name": {"$regex": "salman", "$options": "i"}},
                        ]}},
                        {"$lookup": {
                            "from": "departments",
                            "localField": "department",
                            "foreignField": "_id",
                            "as": "dept",
                        }},
                        {"$project": {"employeeId": 1, "name": 1, "dept.name": 1}},
                    ],
                }
            ]
        },
    },
    {
        "question": (
            "assuming today is Friday 2026-08-21, did trainer Muhammed "
            "Salman punch in on days he had a scheduled session last week?"
        ),
        "response": {
            "queries": [
                {
                    "collection": "topic_tracker_entries",
                    "pipeline": [
                        {"$match": {
                            "date": {"$gte": "2026-08-17", "$lte": "2026-08-23"},
                            "trainerName": {"$regex": "salman", "$options": "i"},
                        }},
                        {"$lookup": {
                            "from": "trainerdailyattendances",
                            "let": {"trn": "$trainer", "d": "$date"},
                            "pipeline": [
                                {"$match": {"$expr": {"$and": [
                                    {"$eq": ["$trainer", "$$trn"]},
                                    {"$eq": ["$date", "$$d"]},
                                ]}}},
                            ],
                            "as": "attendance",
                        }},
                        {"$match": {"$or": [
                            {"attendance": {"$size": 0}},
                            {"attendance.punchInAt": None},
                        ]}},
                        {"$project": {"date": 1, "trainerName": 1, "subject": 1}},
                    ],
                }
            ]
        },
    },
    {
        "question": (
            "which of trainer Muhammed Salman's scheduled classes this "
            "week haven't been held yet?"
        ),
        "response": {
            "queries": [
                {
                    "collection": "schedules",
                    "pipeline": [
                        {"$match": {"trainerCode": {"$regex": "salman", "$options": "i"}}},
                        {"$project": {"day": 1, "startTime": 1, "endTime": 1, "subjectCode": 1, "trainerCode": 1}},
                    ],
                },
                {
                    "collection": "topic_tracker_entries",
                    "pipeline": [
                        {"$match": {
                            "date": {"$gte": "2026-08-17", "$lte": "2026-08-23"},
                            "trainerName": {"$regex": "salman", "$options": "i"},
                        }},
                        {"$project": {"date": 1, "day": 1, "subject": 1, "sessionStatus": 1}},
                    ],
                },
            ]
        },
    },
    {
        "question": (
            "assuming today is Thursday 2026-08-27, who are all the "
            "trainers taking classes today?"
        ),
        "response": {
            "queries": [
                {
                    "collection": "schedules",
                    "pipeline": [
                        {"$match": {"day": "Thursday"}},
                        {"$lookup": {
                            "from": "trainers",
                            "localField": "trainerCode",
                            "foreignField": "scheduleTrainerCodes",
                            "as": "trainerDetails",
                        }},
                        {"$unwind": {"path": "$trainerDetails", "preserveNullAndEmptyArrays": True}},
                        {"$project": {
                            "day": 1, "startTime": 1, "endTime": 1, "subjectCode": 1,
                            "trainerName": "$trainerDetails.name",
                            "employeeId": "$trainerDetails.employeeId",
                        }},
                    ],
                }
            ]
        },
    },
    {
        "question": (
            "assuming today is Thursday 2026-08-27, how many classes has "
            "trainer Muhammed Salman taken this week?"
        ),
        "response": {
            "queries": [
                {
                    "collection": "topic_tracker_entries",
                    "pipeline": [
                        {"$match": {
                            "date": {"$gte": "2026-08-24", "$lte": "2026-08-30"},
                            "trainerName": {"$regex": "salman", "$options": "i"},
                        }},
                        {"$count": "classesTaken"},
                    ],
                }
            ]
        },
    },
    {
        "question": "did she attend yesterday?",
        "response_text": "Which trainer or student are you asking about?",
    },
    {
        "question": (
            "assuming today is 2026-08-27, does trainer Ravi Teja have "
            "leave today?"
        ),
        "response": {
            "queries": [
                {
                    "collection": "leaves",
                    "pipeline": [
                        {"$lookup": {
                            "from": "trainers",
                            "localField": "trainer",
                            "foreignField": "_id",
                            "as": "trainerInfo",
                        }},
                        {"$unwind": {"path": "$trainerInfo", "preserveNullAndEmptyArrays": True}},
                        {"$match": {
                            "$and": [
                                {"trainerInfo.name": {"$regex": "ravi", "$options": "i"}},
                                {"trainerInfo.name": {"$regex": "teja", "$options": "i"}},
                            ],
                            "startDate": {"$lte": "2026-08-27"},
                            "endDate": {"$gte": "2026-08-27"},
                        }},
                        {"$project": {
                            "trainerName": "$trainerInfo.name",
                            "startDate": 1, "endDate": 1, "reason": 1, "status": 1,
                        }},
                    ],
                }
            ]
        },
    },
    {
        "question": (
            "assuming today is Thursday 2026-08-27, how many classes were "
            "scheduled today for trainers?"
        ),
        "response": {
            "queries": [
                {
                    "collection": "schedules",
                    "pipeline": [
                        {"$match": {"day": "Thursday"}},
                        {"$count": "totalScheduledClasses"},
                    ],
                }
            ]
        },
    },
    {
        "question": (
            "assuming today is Thursday 2026-08-27, how many classes were "
            "scheduled today, broken down by subject?"
        ),
        "response": {
            "queries": [
                {
                    "collection": "schedules",
                    "pipeline": [
                        {"$match": {"day": "Thursday"}},
                        {"$group": {"_id": "$subjectCode", "count": {"$sum": 1}}},
                        {"$project": {"subjectCode": "$_id", "count": 1, "_id": 0}},
                    ],
                }
            ]
        },
    },
]


def _render_examples(examples: list[dict[str, Any]]) -> str:
    blocks = [
        f"Q: {ex['question']}\nA: "
        + (ex["response_text"] if "response_text" in ex else json.dumps(ex["response"]))
        for ex in examples
    ]
    return "# Examples\n\n" + "\n\n".join(blocks)


@lru_cache
def _build_system() -> str:
    return "\n\n".join([_INTRO, _SAFETY_RULES, _DOMAIN_RULES, _render_examples(_EXAMPLES), SCHEMA_TEXT])


def _extract_json(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ClarificationNeeded(text.strip())
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError as e:
        raise QueryError(f"Could not parse query JSON: {e}")


def _invoke(messages: list[tuple[str, str]]) -> tuple[dict[str, Any], str]:
    """One LLM call. Returns the parsed JSON alongside the raw text — the
    text is needed verbatim to feed this attempt back to Claude on retry."""
    msg = _llm().invoke(messages)
    content = msg.content if isinstance(msg.content, str) else str(msg.content)
    return _extract_json(content), content


def _scan_forbidden(node: Any) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in FORBIDDEN:
                raise QueryError(f"Forbidden operator: {k}")
            _scan_forbidden(v)
    elif isinstance(node, list):
        for item in node:
            _scan_forbidden(item)


# Fields stored as a real BSON Date in the TOMS schema (see schema.py). JSON
# has no Date type, so Claude emits these as ISO strings; a raw string never
# matches a Date field in $match/$gte/$lte, so we convert before executing.
_DATE_FIELDS = {
    "date", "startDate", "endDate", "approvedAt", "assignedAt", "fromDate",
    "toDate", "readAt", "publishedAt", "dateWorkedOn", "availedOn",
    "cancellationApprovedAt", "closedAt", "joiningDate", "resignationDate",
    "roleTransferEffectiveDate", "replacementAttendanceFrom",
    "replacementAttendanceTo", "punchInAt", "claimedAt", "completedAt",
    "createdAt", "updatedAt",
}


def _parse_iso(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


# Comparison operators whose $expr form is {"$op": [operandA, operandB]},
# e.g. {"$lte": ["$startDate", "2026-08-27"]} — the date field appears as a
# "$fieldPath" string operand here, not as a dict key, so the plain
# field-name-keyed activation in _convert_dates below never fires for it.
_EXPR_COMPARISON_OPS = {"$eq", "$ne", "$lt", "$lte", "$gt", "$gte"}


def _is_date_field_ref(value: Any) -> bool:
    """True if value is an aggregation field-path reference (e.g.
    "$startDate") to a known Date field, as opposed to a literal operand."""
    if not isinstance(value, str) or not value.startswith("$") or value.startswith("$$"):
        return False
    field = value[1:]
    return field in _DATE_FIELDS or field.rsplit(".", 1)[-1] in _DATE_FIELDS


def _maybe_parse_iso(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return _parse_iso(value)
        except ValueError:
            return value
    return value


def _convert_dates(node: Any, active: bool = False) -> Any:
    """Recursively turn ISO date strings under a known Date field (or a
    comparison operator nested under one, e.g. $gte/$lte/$in) into datetime
    objects, so pymongo sends a BSON Date instead of a string. Also handles
    the $expr array form above: a Date field compared against a raw String
    via $lte/$gte silently matches nothing (BSON type ordering — Date
    always sorts after String), so that string operand must be converted
    too, even though it's a list element rather than a dict value under a
    date-field key.
    """
    if isinstance(node, dict):
        for op in _EXPR_COMPARISON_OPS:
            operands = node.get(op)
            if (
                isinstance(operands, list)
                and len(operands) == 2
                and any(_is_date_field_ref(o) for o in operands)
            ):
                return {
                    k: (
                        [o if _is_date_field_ref(o) else _maybe_parse_iso(o) for o in v]
                        if k == op
                        else _convert_dates(v, active=active)
                    )
                    for k, v in node.items()
                }
        return {
            k: _convert_dates(
                v,
                active=k in _DATE_FIELDS
                or k.rsplit(".", 1)[-1] in _DATE_FIELDS
                or (active and k.startswith("$")),
            )
            for k, v in node.items()
        }
    if isinstance(node, list):
        return [_convert_dates(item, active=active) for item in node]
    if active and isinstance(node, str):
        return _maybe_parse_iso(node)
    return node


def _convert_oids(node: Any) -> Any:
    """Claude sometimes refers back to an _id seen in prior (serialized-to-
    string) results using MongoDB Extended JSON, {"$oid": "<hex>"} — valid
    in the shell/Compass, but pymongo passes it through literally and the
    server rejects $oid as an unknown query operator. Convert it to a real
    ObjectId before executing.
    """
    if isinstance(node, dict):
        if set(node) == {"$oid"} and isinstance(node["$oid"], str):
            try:
                return ObjectId(node["$oid"])
            except InvalidId:
                return node
        return {k: _convert_oids(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_convert_oids(item) for item in node]
    return node


def _normalize_raw(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Accept both the current {"queries": [...]} shape and the legacy
    single {"collection":.., "pipeline":..} shape some older prompts/tests
    may still produce."""
    queries = raw.get("queries")
    if queries is None:
        queries = [raw]
    if not isinstance(queries, list) or not queries:
        raise QueryError("'queries' must be a non-empty list")
    if len(queries) > _MAX_SUBQUERIES:
        raise QueryError(f"Too many sub-queries ({len(queries)}); max {_MAX_SUBQUERIES}")
    return queries


def validate_queries(raw: dict[str, Any]) -> list[tuple[str, list[dict[str, Any]]]]:
    validated: list[tuple[str, list[dict[str, Any]]]] = []
    for q in _normalize_raw(raw):
        collection = q.get("collection")
        pipeline = q.get("pipeline")
        if collection not in COLLECTIONS:
            raise QueryError(f"Unknown collection: {collection!r}")
        if not isinstance(pipeline, list) or not all(isinstance(s, dict) for s in pipeline):
            raise QueryError("pipeline must be a list of stage objects")
        _scan_forbidden(pipeline)
        pipeline = [_convert_oids(_convert_dates(stage)) for stage in pipeline]
        # Always cap the result set as a final stage.
        pipeline = pipeline + [{"$limit": get_settings().max_result_docs}]
        validated.append((collection, pipeline))
    return validated


def _serialize(obj: Any) -> Any:
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def _has_lookup(pipeline: list[dict[str, Any]]) -> bool:
    return any("$lookup" in stage for stage in pipeline)


def execute_query(collection: str, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    s = get_settings()
    col = get_client()[s.mongo_db][collection]
    timeout_ms = s.join_query_timeout_ms if _has_lookup(pipeline) else s.query_timeout_ms
    try:
        rows = list(col.aggregate(pipeline, maxTimeMS=timeout_ms))
    except ExecutionTimeout:
        raise QueryError(
            f"Query timed out after {timeout_ms}ms — likely an unindexed or "
            "unfiltered $lookup join. Try asking a narrower question."
        )
    except PyMongoError as e:
        raise QueryError(f"Database error while executing query: {e}")
    return [_serialize(r) for r in rows]


def execute_queries(
    validated: list[tuple[str, list[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    return [
        {"collection": collection, "pipeline": pipeline, "rows": execute_query(collection, pipeline)}
        for collection, pipeline in validated
    ]


def run(question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Full query path: generate -> validate -> execute, for one or more
    independently-filtered sub-queries (see _DOMAIN_RULES for when Claude
    emits more than one).

    A malformed or unexecutable query gets the concrete error fed back to
    Claude for one correction attempt (see _MAX_ATTEMPTS) before we give up
    and surface it — more precise, and far less prompt bloat, than trying to
    prose-prevent every possible mistake up front.
    """
    system = f"{_build_system()}\n\n{current_date_context()}"
    messages: list[tuple[str, str]] = [("system", system), *as_messages(history), ("human", question)]

    for attempt in range(_MAX_ATTEMPTS):
        raw, content = _invoke(messages)  # raises ClarificationNeeded — not retried, it's a valid reply
        try:
            validated = validate_queries(raw)
            return {"queries": execute_queries(validated)}
        except QueryError as e:
            if attempt == _MAX_ATTEMPTS - 1:
                raise
            messages = messages + [
                ("ai", content),
                ("human", f"That query failed: {e}. Return corrected JSON only, no prose."),
            ]
