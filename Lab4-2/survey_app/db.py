"""MongoDB connections, field validators and access-pattern indexes."""

from __future__ import annotations

import re
from copy import deepcopy

from pymongo import ASCENDING, DESCENDING, MongoClient, ReadPreference
from pymongo.database import Database

from .config import Settings


UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
UUID = {"bsonType": "string", "pattern": UUID_PATTERN}
TEXT = {"bsonType": "string"}
NONEMPTY_TEXT = {"bsonType": "string", "minLength": 1}
DATE = {"bsonType": "date"}
BOOLEAN = {"bsonType": "bool"}
INTEGER = {"bsonType": ["int", "long"]}
SCHEMA_VERSION = {"bsonType": ["int", "long"], "enum": [1]}
HASH = {"bsonType": "string", "pattern": r"^[0-9a-f]{64}$"}
OBJECT_ARRAY = {"bsonType": "array", "items": {"bsonType": "object"}}


def _schema(properties: dict, optional: tuple[str, ...] = ()) -> dict:
    return {
        "bsonType": "object",
        "required": [name for name in properties if name not in optional],
        "additionalProperties": False,
        "properties": deepcopy(properties),
    }


SCHEMAS = {
    "users": _schema({
        "_id": UUID, "username": NONEMPTY_TEXT, "username_key": NONEMPTY_TEXT,
        "password_hash": NONEMPTY_TEXT, "created_at": DATE, "schema_version": SCHEMA_VERSION,
    }),
    "sessions": _schema({
        "_id": HASH, "user_id": UUID, "created_at": DATE, "expires_at": DATE,
        "schema_version": SCHEMA_VERSION,
    }),
    "surveys": _schema({
        "_id": UUID, "owner_id": UUID, "share_code": NONEMPTY_TEXT,
        "title": NONEMPTY_TEXT, "description": TEXT,
        "allow_anonymous": BOOLEAN, "allow_repeat": BOOLEAN,
        "status": {"bsonType": "string", "enum": ["draft", "published", "closed"]},
        "closes_at": {"bsonType": ["date", "null"]},
        "created_at": DATE, "updated_at": DATE,
        "published_version": {"bsonType": ["int", "long", "null"], "minimum": 1},
        "revision": {**INTEGER, "minimum": 0}, "gate_seq": {**INTEGER, "minimum": 0},
        "last_accepted_at": DATE,
        "draft": _schema({"questions": OBJECT_ARRAY, "rules": OBJECT_ARRAY}),
        "schema_version": SCHEMA_VERSION,
    }, optional=("last_accepted_at", "draft")),
    "survey_versions": _schema({
        "_id": UUID, "survey_id": UUID, "version": {**INTEGER, "minimum": 1},
        "questions": OBJECT_ARRAY, "rules": OBJECT_ARRAY, "created_at": DATE,
        "schema_version": SCHEMA_VERSION,
    }),
    "responses": _schema({
        "_id": UUID, "survey_id": UUID, "version": {**INTEGER, "minimum": 1},
        "respondent_id": UUID, "request_id": NONEMPTY_TEXT, "payload_hash": HASH,
        "answers": {"bsonType": "object"},
        "path": {"bsonType": "array", "items": {"bsonType": "string"}},
        "single_submission": BOOLEAN, "anonymous": BOOLEAN,
        "submitted_at": DATE, "schema_version": SCHEMA_VERSION,
    }),
    # ---- second stage: reusable, versioned, shareable questions ----
    "questions": _schema({
        "_id": UUID, "owner_id": UUID,
        "type": {"bsonType": "string", "enum": ["single", "multi", "text", "number"]},
        "title": NONEMPTY_TEXT,
        "current_version": {**INTEGER, "minimum": 1},
        "status": {"bsonType": "string", "enum": ["active", "archived"]},
        "origin": {"bsonType": "string", "enum": ["created", "forked", "migrated"]},
        "created_at": DATE, "updated_at": DATE, "schema_version": SCHEMA_VERSION,
    }),
    "question_versions": _schema({
        "_id": UUID, "question_id": UUID, "version": {**INTEGER, "minimum": 1},
        "type": {"bsonType": "string", "enum": ["single", "multi", "text", "number"]},
        "title": NONEMPTY_TEXT, "required": BOOLEAN,
        "options": OBJECT_ARRAY, "validation": {"bsonType": "object"},
        "derived_from": {"bsonType": ["object", "null"]},
        "supersedes": {"bsonType": ["int", "long", "null"]},
        "restored_from": {"bsonType": ["int", "long", "null"]},
        "note": TEXT, "created_by": UUID, "created_at": DATE, "schema_version": SCHEMA_VERSION,
    }),
    "question_shares": _schema({
        "_id": UUID, "question_id": UUID, "owner_id": UUID, "grantee_id": UUID,
        "created_at": DATE, "schema_version": SCHEMA_VERSION,
    }),
    "question_banks": _schema({
        "_id": UUID, "owner_id": UUID, "name": NONEMPTY_TEXT, "description": TEXT,
        "created_at": DATE, "updated_at": DATE, "schema_version": SCHEMA_VERSION,
    }),
    "question_bank_items": _schema({
        "_id": UUID, "bank_id": UUID, "question_id": UUID,
        "question_version": {**INTEGER, "minimum": 1},
        "added_by": UUID, "added_at": DATE, "schema_version": SCHEMA_VERSION,
    }),
    "question_share_links": _schema({
        "_id": UUID, "token_hash": HASH, "question_id": UUID, "owner_id": UUID,
        "created_at": DATE, "revoked_at": {"bsonType": ["date", "null"]},
        "expires_at": {"bsonType": ["date", "null"]},
        "max_uses": {"bsonType": ["int", "long", "null"], "minimum": 1},
        "uses": {**INTEGER, "minimum": 0},
        "schema_version": SCHEMA_VERSION,
    }),
}

# Names are stable so a repeated initializer verifies the same definitions.
INDEXES = {
    "users": [([("username_key", ASCENDING)], {"name": "uq_users_username_key", "unique": True})],
    "sessions": [
        ([("expires_at", ASCENDING)], {"name": "ttl_sessions_expires_at", "expireAfterSeconds": 0}),
        ([("user_id", ASCENDING)], {"name": "ix_sessions_user"}),
    ],
    "surveys": [
        ([("share_code", ASCENDING)], {"name": "uq_surveys_share_code", "unique": True}),
        ([("owner_id", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_surveys_owner_created"}),
        ([("draft.questions.id", ASCENDING)], {"name": "ix_surveys_draft_question"}),
    ],
    "survey_versions": [
        ([("survey_id", ASCENDING), ("version", ASCENDING)], {"name": "uq_survey_versions_survey_version", "unique": True}),
        ([("questions.id", ASCENDING)], {"name": "ix_survey_versions_question"}),
    ],
    "responses": [
        ([("survey_id", ASCENDING), ("respondent_id", ASCENDING), ("request_id", ASCENDING)],
         {"name": "uq_responses_request", "unique": True}),
        ([("survey_id", ASCENDING), ("respondent_id", ASCENDING)],
         {"name": "uq_responses_single_submission", "unique": True,
          "partialFilterExpression": {"single_submission": True}}),
        ([("survey_id", ASCENDING), ("version", ASCENDING)], {"name": "ix_responses_survey_version"}),
    ],
    "questions": [
        ([("owner_id", ASCENDING), ("updated_at", DESCENDING)], {"name": "ix_questions_owner_updated"}),
        ([("owner_id", ASCENDING), ("title", ASCENDING)], {"name": "ix_questions_owner_title"}),
    ],
    "question_versions": [
        ([("question_id", ASCENDING), ("version", ASCENDING)], {"name": "uq_question_versions_version", "unique": True}),
    ],
    "question_shares": [
        ([("question_id", ASCENDING), ("grantee_id", ASCENDING)], {"name": "uq_question_shares_pair", "unique": True}),
        ([("grantee_id", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_question_shares_grantee"}),
    ],
    "question_banks": [
        ([("owner_id", ASCENDING), ("name", ASCENDING)], {"name": "uq_question_banks_owner_name", "unique": True}),
    ],
    "question_bank_items": [
        ([("bank_id", ASCENDING), ("question_id", ASCENDING)], {"name": "uq_bank_items_pair", "unique": True}),
        ([("question_id", ASCENDING)], {"name": "ix_bank_items_question"}),
    ],
    "question_share_links": [
        ([("token_hash", ASCENDING)], {"name": "uq_share_links_token", "unique": True}),
        ([("question_id", ASCENDING), ("created_at", DESCENDING)], {"name": "ix_share_links_question"}),
    ],
}


def create_client(settings: Settings) -> MongoClient:
    return MongoClient(
        settings.mongodb_uri,
        tz_aware=True,
        read_preference=ReadPreference.PRIMARY,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        appname="lab4-survey",
    )


def initialize_schema(db: Database) -> None:
    """Create or update validators/indexes without deleting any data."""
    existing = set(db.list_collection_names())
    for name, schema in SCHEMAS.items():
        validator = {"$jsonSchema": deepcopy(schema)}
        options = {"validator": validator, "validationLevel": "strict", "validationAction": "error"}
        if name in existing:
            db.command({"collMod": name, **options})
        else:
            db.create_collection(name, **options)
    for name, definitions in INDEXES.items():
        for keys, options in definitions:
            db[name].create_index(keys, **deepcopy(options))


def safe_test_database(name: str) -> bool:
    """Accept only explicit, bounded test names; this function never deletes data."""
    return isinstance(name, str) and len(name) <= 63 and re.fullmatch(r"lab4_test_[A-Za-z0-9_]+", name) is not None
