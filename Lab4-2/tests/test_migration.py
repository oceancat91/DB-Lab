"""First-stage data keeps working: embedded questions are back-filled into stored entities."""

from __future__ import annotations

import sys
from hashlib import sha256
from pathlib import Path

import pytest

from conftest import register_login

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import migrate_question_library  # noqa: E402


@pytest.fixture(autouse=True)
def signed_in(client):
    return register_login(client)


def _fingerprint(db) -> str:
    """Hash the survey documents so we can prove the migration never rewrote them."""
    digest = sha256()
    for collection in ("surveys", "survey_versions"):
        for document in db[collection].find({}).sort("_id", 1):
            digest.update(repr(sorted(document.items())).encode())
    return digest.hexdigest()


def _seed_published_survey(client) -> tuple[dict, str]:
    survey = client.post("/api/surveys", json={"title": "第一阶段遗留问卷", "description": "",
                                               "allow_anonymous": True, "allow_repeat": True,
                                               "closes_at": None}).json()
    question_id = "11111111-1111-4111-8111-111111111111"
    saved = client.put(f"/api/surveys/{survey['id']}", json={
        "title": survey["title"], "description": "", "allow_anonymous": True, "allow_repeat": True,
        "closes_at": None, "revision": survey["revision"],
        "questions": [{"id": question_id, "type": "single", "title": "你的年龄段", "required": True,
                       "options": [{"id": "a", "label": "18-25"}, {"id": "b", "label": "26-35"}],
                       "validation": {}}],
        "rules": []})
    assert saved.status_code == 200, saved.text
    published = client.post(f"/api/surveys/{survey['id']}/publish",
                            json={"revision": saved.json()["revision"]})
    assert published.status_code == 200, published.text
    return published.json(), question_id


def test_migration_backfills_legacy_questions_without_rewriting_surveys(client, db):
    baseline = migrate_question_library.migrate(db, apply=False)
    entities_before = db.questions.count_documents({})
    survey, question_id = _seed_published_survey(client)
    assert db.questions.find_one({"_id": question_id}) is None
    before = _fingerprint(db)

    report = migrate_question_library.migrate(db, apply=False)
    assert report["questions_found"] == baseline["questions_found"] + 1
    assert report["created"] == baseline["created"] + 1 and report["applied"] is False
    assert db.questions.count_documents({}) == entities_before, "dry run must not write"

    applied = migrate_question_library.migrate(db, apply=True)
    assert applied["created"] == baseline["created"] + 1
    assert db.questions.count_documents({}) == entities_before + 1
    entity = db.questions.find_one({"_id": question_id})
    assert entity["origin"] == "migrated" and entity["current_version"] == 1
    version = db.question_versions.find_one({"question_id": question_id, "version": 1})
    assert version["title"] == "你的年龄段" and len(version["options"]) == 2
    assert _fingerprint(db) == before, "surveys and published snapshots must stay byte-identical"

    again = migrate_question_library.migrate(db, apply=True)
    assert again["created"] == 0 and again["skipped_existing"] >= 1

    # The migrated question now participates in usage and cross-survey statistics.
    usage = client.get(f"/api/questions/{question_id}/usage").json()
    assert usage["usage_count"] == 1 and usage["usages"][0]["status"] == "published"
    stats = client.get(f"/api/questions/{question_id}/statistics").json()
    assert stats["survey_count"] == 1

    # Editing it after migration creates v2 while the published copy keeps v1 content.
    updated = client.post(f"/api/questions/{question_id}/versions",
                          json={"type": "single", "title": "迁移后修改", "required": True,
                                "options": [{"id": "a", "label": "18-25"},
                                            {"id": "b", "label": "26 以上"}], "validation": {}})
    assert updated.status_code == 201, updated.text
    stored = client.get(f"/api/surveys/{survey['id']}").json()
    assert stored["questions"][0]["title"] == "你的年龄段"
