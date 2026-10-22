#!/usr/bin/env python3
"""Back-fill first-stage embedded questions into stored question entities.

First-stage surveys keep their question copies inside ``surveys.draft`` and
``survey_versions.questions``. The second stage adds reusable question entities, so this
migration creates one entity plus version 1 for every question id that has none yet, using the
survey owner as the question owner. Survey documents are never rewritten: the published
snapshots stay byte-identical, and cross-survey statistics/usage match on the question id.

    python scripts/migrate_question_library.py --dry-run
    python scripts/migrate_question_library.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from survey_app.config import Settings  # noqa: E402
from survey_app.db import create_client, initialize_schema  # noqa: E402
from survey_app.questions import check_definition  # noqa: E402

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def collect(db) -> tuple[list[dict], list[str], list[str]]:
    """Every embedded question copy with the owner of the survey that contains it."""
    found: dict[str, dict] = {}
    conflicts: list[str] = []
    skipped_non_uuid: list[str] = []
    for survey in db.surveys.find({}, {"owner_id": 1, "draft": 1, "share_code": 1}):
        for question in survey.get("draft", {}).get("questions", []):
            _remember(found, conflicts, skipped_non_uuid, question, survey["owner_id"], "draft")
    for version in db.survey_versions.find({}, {"survey_id": 1, "version": 1, "questions": 1}):
        survey = db.surveys.find_one({"_id": version["survey_id"]}, {"owner_id": 1})
        owner = survey["owner_id"] if survey else None
        for question in version.get("questions", []):
            _remember(found, conflicts, skipped_non_uuid, question, owner, f"v{version['version']}")
    return list(found.values()), conflicts, skipped_non_uuid


def _remember(found: dict, conflicts: list, skipped: list, question: dict,
              owner: str | None, source: str) -> None:
    identifier = question.get("id")
    if not isinstance(identifier, str) or owner is None:
        return
    if UUID_PATTERN.fullmatch(identifier) is None:
        # Legacy survey-local ids cannot become entity ids under the strict UUID schema; those
        # questions stay inside their survey and are reported instead of being silently dropped.
        if identifier not in skipped:
            skipped.append(identifier)
        return
    content = {key: question[key] for key in ("type", "title", "required", "options", "validation")
               if key in question}
    entry = found.get(identifier)
    if entry is None:
        found[identifier] = {"id": identifier, "owner": owner, "content": content, "sources": [source]}
        return
    entry["sources"].append(source)
    if content != entry["content"] and identifier not in conflicts:
        # Not a defect: different surveys may pin different versions of one question, so the
        # embedded copies legitimately differ. Reported for transparency only.
        conflicts.append(identifier)


def migrate(db, *, apply: bool = False) -> dict:
    initialize_schema(db)
    questions, conflicts, skipped_non_uuid = collect(db)
    report = {"questions_found": len(questions), "created": 0, "skipped_existing": 0,
              "skipped_non_uuid": sorted(skipped_non_uuid),
              "content_variants": sorted(set(conflicts)),
              "content_variants_note": "同一题目在不同问卷中引用不同版本时内嵌内容本就不同，不是迁移冲突",
              "invalid": [], "applied": apply}
    for entry in questions:
        if db.questions.find_one({"_id": entry["id"]}):
            report["skipped_existing"] += 1
            continue
        try:
            normalized, _ = check_definition([{**entry["content"], "id": entry["id"]}], [])
        except Exception as exc:  # malformed legacy definition: report, never invent
            report["invalid"].append({"id": entry["id"], "error": type(exc).__name__})
            continue
        content = normalized[0]
        now = _now()
        entity = {"_id": entry["id"], "owner_id": entry["owner"], "type": content["type"],
                  "title": content["title"], "current_version": 1, "status": "active",
                  "origin": "migrated", "created_at": now, "updated_at": now, "schema_version": 1}
        version = {"_id": str(uuid4()), "question_id": entry["id"], "version": 1,
                   "type": content["type"], "title": content["title"],
                   "required": content["required"], "options": content["options"],
                   "validation": content["validation"], "derived_from": None, "supersedes": None,
                   "restored_from": None, "note": "由第一阶段内嵌题目迁移", "created_by": entry["owner"],
                   "created_at": now, "schema_version": 1}
        if apply:
            try:
                db.questions.insert_one(entity)
                db.question_versions.insert_one(version)
            except Exception as exc:  # keep the survey data untouched, report the failure
                report.setdefault("failed", []).append({"id": entry["id"], "error": type(exc).__name__})
                continue
        report["created"] += 1
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--apply", action="store_true")
    parser.add_argument("--output", default="results/stage2/migration.json")
    arguments = parser.parse_args()

    settings = Settings.from_env()
    client = create_client(settings)
    try:
        db = client[settings.database]
        report = migrate(db, apply=arguments.apply)
        report["database_scope"] = "configured MONGODB_DATABASE only; no other database is read or written"
        report["finished_at"] = _now().isoformat()
        target = ROOT / arguments.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
