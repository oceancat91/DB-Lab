"""Verify real MongoDB validators/indexes using only a new UUID test database."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import pymongo
from bson import Int64
from pymongo.errors import OperationFailure

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from survey_app.config import SEED, Settings
from survey_app.db import INDEXES, SCHEMAS, create_client, initialize_schema, safe_test_database

LOCAL_TIMEZONE = timezone(timedelta(hours=8))


def fixture_id(label: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"lab4-schema-{SEED}-{label}"))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    started = datetime.now(LOCAL_TIMEZONE)
    name = f"lab4_test_schema_{uuid4().hex}"
    report = {
        "stage": "S2", "requirements": ["R01", "R13"], "timezone": "Asia/Shanghai",
        "started_at": started.isoformat(), "seed": SEED,
        "command": "python scripts/check_schema.py", "database": name,
        "scope": "field validators/indexes only; no account, rule or submission API acceptance",
        "environment": {"python": platform.python_version(), "pymongo": pymongo.version},
        "checks": [], "cleanup": {"status": "NOT_RUN"},
    }
    checks = report["checks"]
    client = None
    cleanup_allowed = False

    def record(check: str, expected: object, actual: object, passed: bool) -> None:
        checks.append({"id": check, "expected": expected, "actual": actual, "status": "PASS" if passed else "FAIL"})

    def rejects(check: str, collection, document: dict, expected_code: int) -> None:
        try:
            collection.insert_one(document)
        except OperationFailure as exc:
            record(check, {"write_error_code": expected_code}, {"write_error_code": exc.code}, exc.code == expected_code)
        except Exception as exc:
            record(check, {"write_error_code": expected_code}, {"error_type": type(exc).__name__}, False)
        else:
            record(check, {"write_error_code": expected_code}, "insert unexpectedly succeeded", False)

    try:
        if not safe_test_database(name) or not re.fullmatch(r"lab4_test_schema_[0-9a-f]{32}", name):
            raise RuntimeError("Generated test database did not satisfy safety checks")
        settings = Settings.from_env()
        if name == settings.database:
            raise RuntimeError("Test database must differ from configured application database")
        client = create_client(settings)
        hello = client.admin.command("hello")
        report["environment"].update({
            "mongodb": client.server_info()["version"],
            "replica_set": hello.get("setName"),
            "writable_primary": hello.get("isWritablePrimary", False),
            "read_preference": "primary", "tz_aware": True,
        })
        record("primary_replica_set", "writable replica-set primary",
               {"replica_set": hello.get("setName"), "primary": hello.get("isWritablePrimary", False)},
               bool(hello.get("setName")) and hello.get("isWritablePrimary") is True)
        db = client[name]
        if db.list_collection_names():
            raise RuntimeError("Generated database was not empty; refusing to modify or clean it")
        cleanup_allowed = True
        initialize_schema(db)
        collections = sorted(db.list_collection_names())
        record("collection_names", sorted(SCHEMAS), collections, collections == sorted(SCHEMAS))
        for collection_name, schema in SCHEMAS.items():
            options = db[collection_name].options()
            actual = {key: options.get(key) for key in ("validationLevel", "validationAction", "validator")}
            expected = {"validationLevel": "strict", "validationAction": "error", "validator": {"$jsonSchema": schema}}
            record(f"validator_{collection_name}", "exact strict/error field schema", "matching" if actual == expected else "mismatch", actual == expected)
        index_snapshots = {}
        for collection_name, definitions in INDEXES.items():
            indexes = db[collection_name].index_information()
            index_snapshots[collection_name] = indexes
            for keys, options in definitions:
                actual = indexes.get(options["name"], {})
                matched = list(actual.get("key", [])) == keys
                for key in ("unique", "partialFilterExpression", "expireAfterSeconds"):
                    if key in options:
                        matched = matched and actual.get(key) == options[key]
                    elif key in actual and key != "unique":
                        matched = False
                    elif key == "unique" and actual.get(key, False):
                        matched = False
                record(f"index_{options['name']}", {"key": keys, **options}, actual, matched)
        report["indexes"] = index_snapshots

        now = datetime.now(timezone.utc)
        user_id = fixture_id("user")
        survey_id = fixture_id("survey")
        synthetic_hash = "pbkdf2_sha256$310000$schema-probe$" + hashlib.pbkdf2_hmac(
            "sha256", b"synthetic-probe-password", b"schema-probe", 310000).hex()
        documents = {
            "users": {"_id": user_id, "username": "Schema Probe", "username_key": "schema-probe", "password_hash": synthetic_hash,
                      "created_at": now, "schema_version": 1},
            "sessions": {"_id": hashlib.sha256(b"synthetic-session-token").hexdigest(), "user_id": user_id,
                         "created_at": now, "expires_at": now + timedelta(days=1), "schema_version": 1},
            "surveys": {"_id": survey_id, "owner_id": user_id, "share_code": "schema-probe-share", "title": "Schema probe",
                        "description": "Synthetic schema fixture", "allow_anonymous": True, "allow_repeat": False,
                        "status": "draft", "closes_at": None, "created_at": now, "updated_at": now,
                        "published_version": None, "revision": 0, "gate_seq": 0,
                        "draft": {"questions": [], "rules": []}, "schema_version": 1},
            "survey_versions": {"_id": fixture_id("version"), "survey_id": survey_id, "version": 1, "questions": [],
                                "rules": [], "created_at": now, "schema_version": 1},
            "responses": {"_id": fixture_id("response"), "survey_id": survey_id, "version": 1,
                          "respondent_id": user_id, "request_id": "probe-request", "payload_hash": "a" * 64,
                          "answers": {}, "path": [], "single_submission": False, "anonymous": True,
                          "submitted_at": now, "schema_version": 1},
        }
        for collection_name, document in documents.items():
            db[collection_name].insert_one(deepcopy(document))
            stored = db[collection_name].find_one({"_id": document["_id"]})
            record(f"valid_document_{collection_name}", "one valid fixture inserted/read back", bool(stored), stored is not None)
            invalid = deepcopy(document)
            invalid["_id"] = hashlib.sha256(collection_name.encode()).hexdigest() if collection_name == "sessions" else fixture_id(f"invalid-{collection_name}")
            del invalid["schema_version"]
            rejects(f"missing_schema_version_{collection_name}", db[collection_name], invalid, 121)

        bad_user = {**documents["users"], "_id": fixture_id("bad-user-extra"), "unexpected": True}
        rejects("unknown_field_rejected", db.users, bad_user, 121)
        bad_user = {**documents["users"], "_id": fixture_id("bad-user-version"), "schema_version": 2}
        rejects("wrong_schema_version_rejected", db.users, bad_user, 121)
        bad_user = {**documents["users"], "_id": fixture_id("bad-user-bool"), "schema_version": True}
        rejects("boolean_is_not_integer", db.users, bad_user, 121)
        for label, changes in (
            ("status", {"status": "invalid"}), ("date", {"closes_at": "tomorrow"}),
            ("boolean", {"allow_repeat": 1}), ("integer", {"revision": 1.5}),
            ("nested_draft", {"draft": {"questions": "invalid", "rules": []}}),
        ):
            invalid = {**documents["surveys"], "_id": fixture_id(f"bad-survey-{label}"), **changes}
            rejects(f"invalid_survey_{label}", db.surveys, invalid, 121)
        bad_response = {**documents["responses"], "_id": fixture_id("bad-response-path"), "path": [10]}
        rejects("response_path_string_items", db.responses, bad_response, 121)

        rejects("unique_username_key", db.users, {**documents["users"], "_id": fixture_id("duplicate-user")}, 11000)
        rejects("unique_share_code", db.surveys, {**documents["surveys"], "_id": fixture_id("duplicate-share")}, 11000)
        rejects("unique_survey_version", db.survey_versions, {**documents["survey_versions"], "_id": fixture_id("duplicate-version")}, 11000)
        rejects("unique_request_idempotency", db.responses, {**documents["responses"], "_id": fixture_id("duplicate-request")}, 11000)

        single = {**documents["responses"], "_id": fixture_id("single-1"), "survey_id": fixture_id("single-survey"),
                  "request_id": "single-1", "single_submission": True}
        db.responses.insert_one(single)
        rejects("single_submission_partial_unique", db.responses,
                {**single, "_id": fixture_id("single-2"), "request_id": "single-2"}, 11000)
        repeat_survey = fixture_id("repeat-survey")
        for number in (1, 2):
            db.responses.insert_one({**documents["responses"], "_id": fixture_id(f"repeat-{number}"),
                                     "survey_id": repeat_survey, "request_id": f"repeat-{number}", "single_submission": False})
        repeat_count = db.responses.count_documents({"survey_id": repeat_survey, "respondent_id": user_id})
        record("repeat_mode_accepts_multiple", 2, repeat_count, repeat_count == 2)
        long_document = {**documents["survey_versions"], "_id": fixture_id("long-version"), "version": Int64(2), "schema_version": Int64(1)}
        db.survey_versions.insert_one(long_document)
        record("bson_long_integer_accepted", "BSON long version/schema_version accepted", db.survey_versions.count_documents({"_id": long_document["_id"]}),
               db.survey_versions.count_documents({"_id": long_document["_id"]}) == 1)
        before = {collection: db[collection].count_documents({}) for collection in SCHEMAS}
        initialize_schema(db)
        after = {collection: db[collection].count_documents({}) for collection in SCHEMAS}
        record("reinitialize_preserves_documents", before, after, before == after)
        report["ttl_scope"] = "expires_at TTL index definition verified; asynchronous expiration timing is not claimed"
    except Exception as exc:
        record("probe_execution", "all schema/index checks execute", {"error_type": type(exc).__name__}, False)
    finally:
        if client is not None:
            if cleanup_allowed:
                try:
                    if not safe_test_database(name) or not re.fullmatch(r"lab4_test_schema_[0-9a-f]{32}", name):
                        raise RuntimeError("Cleanup safety check failed")
                    client.drop_database(name)
                    remaining = client[name].list_collection_names()
                    report["cleanup"] = {"status": "PASS" if not remaining else "FAIL", "database": name, "remaining_collections": remaining}
                except Exception as exc:
                    report["cleanup"] = {"status": "FAIL", "database": name, "error_type": type(exc).__name__}
            client.close()

    passed = bool(checks) and all(item["status"] == "PASS" for item in checks) and report["cleanup"]["status"] == "PASS"
    report["status"] = "PASS" if passed else "FAIL"
    report["exit_code"] = 0 if passed else 1
    report["finished_at"] = datetime.now(LOCAL_TIMEZONE).isoformat()
    report["source_sha256"] = {
        path: hashlib.sha256((PROJECT_ROOT / path).read_bytes()).hexdigest()
        for path in ("survey_app/config.py", "survey_app/db.py", "scripts/init_db.py", "scripts/check_schema.py")
    }
    output_directory = PROJECT_ROOT / "results" / "S2"
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / "schema-check.json"
    if output.exists():
        archive = output_directory / f"schema-check-{started.strftime('%Y%m%dT%H%M%S%f')}.json"
        archive.write_bytes(output.read_bytes())
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(checks), "failed": sum(item["status"] == "FAIL" for item in checks),
                      "cleanup": report["cleanup"]["status"], "evidence": "results/S2/schema-check.json"}, ensure_ascii=False))
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
