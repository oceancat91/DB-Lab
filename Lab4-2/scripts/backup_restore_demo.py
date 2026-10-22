"""Demonstrate BSON backup/restore using only two newly generated synthetic UUID databases.

No source/destination database arguments or overwrite mode exist. Private BSON stays
under .runtime and is deliberately excluded from the public evidence and ZIP.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import secrets
import sys
from uuid import uuid4

from bson import BSON, decode_all
from bson.codec_options import CodecOptions


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from survey_app.config import Settings  # noqa: E402
from survey_app.db import SCHEMAS, create_client, initialize_schema  # noqa: E402
from survey_app.service import SurveyService  # noqa: E402


BASELINE = "e7255c3332b3492691eff27a0a5ce7e395127422"
LOCAL_TIMEZONE = timezone(timedelta(hours=8))
COLLECTIONS = tuple(SCHEMAS)
OUTPUT = ROOT / "results/S7/backup-restore.json"


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def now():
    return datetime.now(LOCAL_TIMEZONE).isoformat()


def counts(db):
    return {name: db[name].count_documents({}) for name in COLLECTIONS}


def definitions(db):
    """Public validators and indexes; no business documents or credentials."""
    result = {}
    for name in COLLECTIONS:
        options = db[name].options()
        result[name] = {
            "validator": options.get("validator"),
            "validationLevel": options.get("validationLevel"),
            "validationAction": options.get("validationAction"),
            "indexes": {index["name"]: {
                key: (dict(value) if key == "key" else value)
                for key, value in index.items() if key not in {"v", "ns"}
            } for index in db[name].list_indexes()},
        }
    return result


def check_statistics(service, survey, owner_id, expected):
    result = service.statistics(survey["id"], owner_id)
    questions = {question["id"]: question for question in result["questions"]}
    require(result["submissions"] == expected["submissions"], "submission_count")
    require(result["respondents"] == expected["respondents"], "respondent_count")
    require(result["version"] == expected["published_version"], "published_version")
    for kind in ("single", "multi"):
        actual = {option["id"]: {key: option[key] for key in ("count", "people")}
                  for option in questions[kind]["options"]}
        require(actual == expected[kind], kind + "_options")
        require(questions[kind]["answered_submissions"] == 3, kind + "_answered")
        require(questions[kind]["answered_people"] == 2, kind + "_people")
    require(sorted(questions["text"]["values"]) == sorted(expected["text_values"]), "text_values")
    number = questions["number"]
    require(sorted(number["values"]) == expected["number_values"], "number_values")
    require(number["mean"] == expected["number_mean"], "number_mean")
    require(number["answered_submissions"] == expected["number_answered_submissions"], "number_answered")
    require(number["answered_people"] == expected["number_answered_people"], "number_people")
    require(questions["end"]["answered_submissions"] == expected["end_answered_submissions"], "end_answered")
    require(questions["end"]["values"] == [], "end_values")
    for question_id, question in questions.items():
        require(service.statistics(survey["id"], owner_id, question_id) == question, "single_question_match")
    return result


def make_empty_database(client, name, created, configured_database):
    require(name != configured_database and re.fullmatch(r"lab4_test_(backup|restore)_[0-9a-f]{32}", name),
            "unsafe_database_name")
    require(name not in client.list_database_names(), "database_already_exists")
    db = client[name]
    require(not db.list_collection_names(), "database_not_empty")
    # Successful create establishes ownership before the initializer can partially fail.
    db.create_collection("users", validator={"$jsonSchema": deepcopy(SCHEMAS["users"])},
                         validationLevel="strict", validationAction="error")
    created[name] = True
    initialize_schema(db)
    require(set(db.list_collection_names()) == set(COLLECTIONS), "unexpected_collections")
    return db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()  # No selectable database, backup directory or overwrite options.
    run_id = uuid4().hex
    source_name = "lab4_test_backup_" + run_id
    target_name = "lab4_test_restore_" + run_id
    permitted_names = (source_name, target_name)
    created = {name: False for name in permitted_names}
    backup = ROOT / ".runtime/backup-demo" / run_id
    evidence = {
        "status": "FAIL", "started_at": now(), "timezone": "Asia/Shanghai",
        "stage": "S7", "requirements": ["R13", "DOC-02", "TC-E02"],
        "command": "python scripts/backup_restore_demo.py",
        "application_baseline_commit": BASELINE, "seed": 20261015,
        "schema_version": 1, "published_version": 1,
        "input": "docs/fixtures/statistics.json",
        "databases": {"source": source_name, "restored": target_name},
        "backup_directory": backup.relative_to(ROOT).as_posix(),
        "backup_format": "BSON document streams, one file per collection; transaction snapshot",
        "cleanup": {}, "checks": {},
        "scope": "Synthetic quiescent backup; empty sessions collection does not prove session recovery.",
        "source_sha256": {}, "step": "configuration",
    }
    paths = sorted((ROOT / "survey_app").rglob("*.py")) + [
        Path(__file__), ROOT / "docs/fixtures/statistics.json", ROOT / "environment.yml",
    ]
    evidence["source_sha256"] = {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths
    }
    client = None
    exit_code = 1
    try:
        settings = Settings.from_env()
        client = create_client(settings)
        hello = client.admin.command("hello")
        options = client.admin.command("getCmdLineOpts")["parsed"]
        require(Path(options["storage"]["dbPath"]).resolve() == (ROOT / ".runtime/mongo").resolve(),
                "mongo_data_directory_not_this_project")
        require(hello.get("isWritablePrimary") is True and hello.get("setName"), "replica_set_required")
        evidence["environment"] = {
            "python": platform.python_version(), "platform": platform.platform(),
            "pymongo": importlib.metadata.version("pymongo"),
            "mongodb": client.server_info()["version"], "replica_set": hello["setName"],
            "writable_primary": True, "data_directory": ".runtime/mongo",
            "port": options.get("net", {}).get("port"),
        }
        fixture = json.loads((ROOT / evidence["input"]).read_text(encoding="utf-8"))
        expected = fixture["expected"]
        evidence["expected"] = expected
        evidence["step"] = "create_source"
        source = make_empty_database(client, source_name, created, settings.database)
        service = SurveyService(source, client, replace(settings, database=source_name))
        password = secrets.token_urlsafe(32)
        users = {label: service.register("demo_" + label + "_" + run_id[:12], password)
                 for label in ("owner", "first", "second")}
        owner_id = users["owner"]["id"]
        survey = service.create_survey(owner_id, deepcopy(fixture["survey"]))
        saved = service.update_survey(survey["id"], owner_id, {
            **deepcopy(fixture["survey"]), "revision": survey["revision"],
            "questions": deepcopy(fixture["questions"]), "rules": deepcopy(fixture["rules"]),
        })
        survey = service.publish(survey["id"], owner_id, saved["revision"])
        original = []
        for row in fixture["submissions"]:
            request_id = uuid4().hex
            user_id = users[row["respondent"]]["id"]
            receipt = service.submit(survey["share_code"], user_id, survey["version"], request_id,
                                     deepcopy(row["answers"]))
            require(receipt["replayed"] is False, "initial_submit_replayed")
            original.append((user_id, request_id, deepcopy(row["answers"]), receipt))
        require(counts(source) == expected["collections"], "source_counts")
        third = source.responses.find_one({"_id": original[2][3]["id"]})
        require(third["path"] == expected["third_path"] and "number" not in third["answers"], "legitimate_skip")
        before_statistics = check_statistics(service, survey, owner_id, expected)
        source_definitions = definitions(source)
        for name in COLLECTIONS:
            require(source_definitions[name]["validator"] == {"$jsonSchema": SCHEMAS[name]}, "source_validator")
            require(source_definitions[name]["validationLevel"] == "strict", "source_validation_level")
            require(source_definitions[name]["validationAction"] == "error", "source_validation_action")
        evidence["checks"]["source_service_submissions_and_statistics"] = "PASS"
        evidence["step"] = "snapshot_export"
        # No writes occur while exporting. All five reads share one snapshot transaction.
        snapshot = service.transaction(lambda session: {
            name: list(source[name].find({}, session=session).sort("_id", 1)) for name in COLLECTIONS
        })
        backup.mkdir(parents=True, exist_ok=False)
        for name, documents in snapshot.items():
            with (backup / (name + ".bson")).open("xb") as stream:
                for document in documents:
                    stream.write(BSON.encode(document))
        (backup / "schema-indexes.json").write_text(
            json.dumps(source_definitions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        evidence["checks"]["five_collection_snapshot_export"] = "PASS"
        evidence["step"] = "restore_into_new_database"
        target = make_empty_database(client, target_name, created, settings.database)
        for name in COLLECTIONS:
            documents = decode_all((backup / (name + ".bson")).read_bytes(),
                                   codec_options=CodecOptions(tz_aware=True))
            require(documents == snapshot[name], "bson_roundtrip")
            if documents:
                target[name].insert_many(documents, ordered=True)
        require(counts(target) == expected["collections"], "restored_counts")
        require(definitions(target) == source_definitions, "restored_schema_indexes")
        document_matches = {
            name: list(target[name].find({}).sort("_id", 1)) == snapshot[name] for name in COLLECTIONS
        }
        require(all(document_matches.values()), "restored_documents")
        evidence["checks"]["all_bson_documents_equal"] = document_matches
        evidence["checks"]["strict_schema_and_indexes_equal"] = "PASS"
        evidence["checks"]["all_document_schema_versions_one"] = all(
            doc["schema_version"] == 1 for documents in snapshot.values() for doc in documents)
        require(evidence["checks"]["all_document_schema_versions_one"], "schema_version")
        evidence["step"] = "restored_service_verification"
        restored = SurveyService(target, client, replace(settings, database=target_name))
        after_statistics = check_statistics(restored, survey, owner_id, expected)
        require(after_statistics == before_statistics, "restored_statistics_changed")
        evidence["checks"]["whole_and_six_single_question_statistics"] = "PASS"
        stable_gate = target.surveys.find_one({"_id": survey["id"]})["gate_seq"]
        for user_id, request_id, answers, first_receipt in original:
            replay = restored.submit(survey["share_code"], user_id, survey["version"], request_id, answers)
            require(replay == {**first_receipt, "replayed": True}, "original_idempotency_receipt")
        require(counts(target) == expected["collections"], "replay_added_documents")
        require(target.surveys.find_one({"_id": survey["id"]})["gate_seq"] == stable_gate, "replay_changed_gate")
        for label in users:
            require(restored.login(users[label]["username"], password)["_id"] == users[label]["id"], "restored_login")
        evidence["checks"]["three_original_receipts_replayed_without_writes"] = "PASS"
        evidence["checks"]["three_restored_account_passwords_verified"] = "PASS"
        number_statistics = next(question for question in after_statistics["questions"] if question["id"] == "number")
        evidence["actual"] = {
            "collections": counts(target), "submissions": after_statistics["submissions"],
            "respondents": after_statistics["respondents"], "number_mean": number_statistics["mean"],
            "number_values": sorted(number_statistics["values"]), "legitimate_skipped_third_path": third["path"],
            "replayed_original_receipts": len(original), "sessions_recovery": "NOT_COVERED_EMPTY_COLLECTION",
        }
        evidence["step"] = "finished"
        exit_code = 0
    except Exception as exc:
        # Do not expose driver exceptions, connection URIs, credentials or private documents.
        evidence["error"] = {"type": type(exc).__name__, "step": evidence["step"],
                             "message": "Execution failed; raw exception omitted to avoid secrets."}
        if type(exc) is RuntimeError and re.fullmatch(r"[a-z_]+", str(exc)):
            evidence["error"]["failed_check"] = str(exc)
    finally:
        if client is not None:
            for name in permitted_names:
                if not created[name]:
                    evidence["cleanup"][name] = {"status": "NOT_CREATED_NO_DROP"}
                    continue
                try:
                    require(name in permitted_names and created[name]
                            and re.fullmatch(r"lab4_test_(backup|restore)_[0-9a-f]{32}", name), "cleanup_scope")
                    before_drop = counts(client[name])
                    client.drop_database(name)
                    require(not client[name].list_collection_names(), "cleanup_remaining_collections")
                    evidence["cleanup"][name] = {"status": "PASS", "counts_before_drop": before_drop}
                except Exception as exc:
                    evidence["cleanup"][name] = {"status": "FAIL", "error_type": type(exc).__name__}
                    exit_code = 1
            client.close()
        evidence["finished_at"] = now()
        evidence["exit_code"] = exit_code
        evidence["status"] = "PASS" if exit_code == 0 else "FAIL"
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        if OUTPUT.exists():
            archive = OUTPUT.with_name("backup-restore-" + run_id + ".json")
            archive.write_bytes(OUTPUT.read_bytes())
        OUTPUT.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "exit_code": exit_code,
                      "evidence": OUTPUT.relative_to(ROOT).as_posix()}))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
