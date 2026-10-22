"""Second stage: stored questions, versions, sharing, banks, usage and cross-survey statistics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pymongo.errors import DuplicateKeyError

from conftest import register_login, unique_username


@pytest.fixture(autouse=True)
def signed_in(client):
    """Every test in this module needs an authenticated owner client."""
    return register_login(client)


def question_payload(**overrides) -> dict:
    payload = {"type": "single", "title": "你的年龄段", "required": True,
               "options": [{"id": "a", "label": "18-25"}, {"id": "b", "label": "26-35"}],
               "validation": {}, "note": ""}
    payload.update(overrides)
    return payload


def create_question(client, **overrides) -> dict:
    response = client.post("/api/questions", json=question_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def new_version(client, question_id: str, **overrides) -> dict:
    response = client.post(f"/api/questions/{question_id}/versions", json=question_payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def create_survey(client, title: str = "合成问卷") -> dict:
    response = client.post("/api/surveys", json={"title": title, "description": "第二阶段测试",
                                                 "allow_anonymous": True, "allow_repeat": True,
                                                 "closes_at": None})
    assert response.status_code == 201, response.text
    return response.json()


def import_question(client, survey: dict, question_id: str, version: int | None = None) -> dict:
    body = {"question_id": question_id}
    if version is not None:
        body["version"] = version
    response = client.post(f"/api/surveys/{survey['id']}/questions/import", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def publish(client, survey: dict) -> dict:
    latest = client.get(f"/api/surveys/{survey['id']}").json()
    response = client.post(f"/api/surveys/{survey['id']}/publish", json={"revision": latest["revision"]})
    assert response.status_code == 200, response.text
    return response.json()


def submit_answer(client, survey: dict, answers: dict, request_id: str = "req-1") -> dict:
    fill = client.get(f"/api/fill/{survey['share_code']}")
    assert fill.status_code == 200, fill.text
    response = client.post(f"/api/fill/{survey['share_code']}/submit",
                           json={"version": fill.json()["version"], "request_id": request_id,
                                 "answers": answers})
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------- R15 stored questions
def test_question_creation_listing_and_validation(client, db):
    created = create_question(client)
    assert created["current_version"] == 1
    assert created["owned"] is True
    assert created["current"]["title"] == "你的年龄段"
    assert created["current"]["version"] == 1

    listed = client.get("/api/questions").json()
    assert [row["id"] for row in listed] == [created["id"]]
    assert client.get("/api/questions", params={"type": "text"}).json() == []
    assert client.get("/api/questions", params={"q": "年龄"}).json()[0]["id"] == created["id"]
    assert client.get("/api/questions", params={"q": "不存在的题"}).json() == []

    # The same definition rules as a survey question: one option is not allowed.
    bad = client.post("/api/questions", json=question_payload(options=[{"id": "a", "label": "唯一"}]))
    assert bad.status_code == 422
    assert db.questions.count_documents({}) == 1

    unknown_field = client.post("/api/questions", json={**question_payload(), "owner_id": "spoof"})
    assert unknown_field.status_code == 422


def test_versions_are_append_only_and_restorable(client, db):
    question = create_question(client)
    question_id = question["id"]
    updated = new_version(client, question_id, title="你的年龄段（细分为三段）",
                          options=[{"id": "a", "label": "18-25"}, {"id": "b", "label": "26-35"},
                                   {"id": "c", "label": "36 以上"}])
    assert updated["current_version"] == 2
    versions = {row["version"]: row for row in updated["versions"]}
    assert sorted(versions) == [1, 2]
    assert versions[2]["derived_from"] == {"question_id": question_id, "version": 1}
    # v1 stays byte-identical in the database: no in-place edit ever happens.
    original = db.question_versions.find_one({"question_id": question_id, "version": 1})
    assert original["title"] == "你的年龄段"
    assert len(original["options"]) == 2

    restored = client.post(f"/api/questions/{question_id}/versions/1/restore")
    assert restored.status_code == 201
    assert restored.json()["current_version"] == 3
    restored_version = db.question_versions.find_one({"question_id": question_id, "version": 3})
    assert restored_version["restored_from"] == 1
    assert restored_version["title"] == "你的年龄段"
    assert restored_version["options"] == original["options"]

    with pytest.raises(DuplicateKeyError):
        db.question_versions.insert_one({**original, "_id": str(uuid4())})


def test_question_of_another_owner_is_not_visible(client, client_factory):
    owner = create_question(client)
    with client_factory() as other:
        register_login(other)
        assert other.get(f"/api/questions/{owner['id']}").status_code == 404
        assert other.post(f"/api/questions/{owner['id']}/versions",
                          json=question_payload(title="越权修改")).status_code == 404
        assert other.get(f"/api/questions/{owner['id']}/statistics").status_code == 404


# ---------------------------------------------------------------- R16 sharing
def test_sharing_allows_reuse_but_not_modification(client, client_factory, db):
    owner = create_question(client)
    question_id = owner["id"]
    with client_factory() as colleague:
        colleague_user = register_login(colleague)
        shared = client.post(f"/api/questions/{question_id}/shares",
                             json={"username": colleague_user["username"]})
        assert shared.status_code == 201, shared.text

        overview = colleague.get("/api/questions/shared").json()
        assert [row["id"] for row in overview] == [question_id]
        assert overview[0]["shared_with_me"] is True and overview[0]["owned"] is False
        assert colleague.get(f"/api/questions/{question_id}").status_code == 200

        survey = create_survey(colleague, "同事的问卷")
        imported = import_question(colleague, survey, question_id)
        assert imported["questions"][0]["question_version"] == 1

        # A grantee may use and even fork the question, but never append a version.
        assert colleague.post(f"/api/questions/{question_id}/versions",
                              json=question_payload(title="同事改题")).status_code == 404
        forked = colleague.post(f"/api/questions/{question_id}/fork",
                                json=question_payload(title="同事的副本"))
        assert forked.status_code == 201
        assert forked.json()["owner_id"] == colleague_user["id"]
        assert db.question_versions.find_one({"question_id": forked.json()["id"],
                                              "version": 1})["derived_from"] == {
            "question_id": question_id, "version": 1}

        removed = client.delete(f"/api/questions/{question_id}/shares/{colleague_user['id']}")
        assert removed.status_code == 200
        assert colleague.get("/api/questions/shared").json() == []
        assert colleague.get(f"/api/questions/{question_id}").status_code == 404

    duplicate = client.post(f"/api/questions/{question_id}/shares",
                            json={"username": unique_username()})
    assert duplicate.status_code == 404  # unknown recipient


# ---------------------------------------------------------------- R17 published questions freeze
def test_published_question_snapshot_survives_new_versions(client, db):
    question = create_question(client)
    survey = create_survey(client, "已发布问卷")
    import_question(client, survey, question["id"])
    published = publish(client, survey)
    assert published["questions"][0]["question_version"] == 1

    new_version(client, question["id"], title="改过的题目", options=[{"id": "a", "label": "甲"},
                                                                    {"id": "b", "label": "乙"}])
    stored = client.get(f"/api/surveys/{survey['id']}").json()
    assert stored["questions"][0]["title"] == "你的年龄段"
    assert stored["questions"][0]["question_version"] == 1
    assert db.survey_versions.find_one({"survey_id": survey["id"], "version": 1})["questions"][0][
        "title"] == "你的年龄段"

    frozen = client.put(f"/api/surveys/{survey['id']}", json={
        "title": survey["title"], "description": "第二阶段测试", "allow_anonymous": True,
        "allow_repeat": True, "closes_at": None, "revision": stored["revision"],
        "questions": stored["questions"], "rules": []})
    assert frozen.status_code == 409

    second = create_survey(client, "新问卷")
    imported = import_question(client, second, question["id"])
    assert imported["questions"][0]["title"] == "改过的题目"
    assert imported["questions"][0]["question_version"] == 2


def test_client_cannot_claim_a_version_it_does_not_match(client):
    question = create_question(client)
    survey = create_survey(client)
    imported = import_question(client, survey, question["id"])
    forged = imported["questions"][0]
    forged["title"] = "伪造的标题"
    forged["question_version"] = 1
    saved = client.put(f"/api/surveys/{survey['id']}", json={
        "title": survey["title"], "description": "第二阶段测试", "allow_anonymous": True,
        "allow_repeat": True, "closes_at": None, "revision": imported["revision"],
        "questions": [forged], "rules": []})
    assert saved.status_code == 200
    assert "question_version" not in saved.json()["questions"][0]


# ---------------------------------------------------------------- R19/R20 versions and usage
def test_two_surveys_can_pin_different_versions_and_usage_lists_both(client, db):
    question = create_question(client)
    first = create_survey(client, "旧版本问卷")
    import_question(client, first, question["id"], version=1)
    publish(client, first)

    new_version(client, question["id"], title="新版本题目")
    second = create_survey(client, "新版本问卷")
    import_question(client, second, question["id"], version=2)

    usage = client.get(f"/api/questions/{question['id']}/usage").json()
    assert usage["usage_count"] == 2
    rows = {(row["survey_id"], row["status"]): row for row in usage["usages"]}
    assert rows[(first["id"], "published")]["question_version"] == 1
    assert rows[(first["id"], "published")]["editable"] is False
    assert rows[(second["id"], "draft")]["question_version"] == 2
    assert rows[(second["id"], "draft")]["editable"] is True


def test_revision_modes_change_only_what_they_should(client, db):
    question = create_question(client)
    survey = create_survey(client)
    imported = import_question(client, survey, question["id"])
    question_id = question["id"]

    local = client.post(f"/api/surveys/{survey['id']}/questions/{question_id}/revision",
                        json={"mode": "draft_only", "question": question_payload(title="只改本卷")})
    assert local.status_code == 200, local.text
    assert local.json()["questions"][0]["title"] == "只改本卷"
    assert "question_version" not in local.json()["questions"][0]
    assert db.questions.find_one({"_id": question_id})["current_version"] == 1

    added = client.post(f"/api/surveys/{survey['id']}/questions/{question_id}/revision",
                        json={"mode": "new_version", "question": question_payload(title="新版本")})
    assert added.status_code == 200, added.text
    assert added.json()["questions"][0]["question_version"] == 2
    assert db.questions.find_one({"_id": question_id})["current_version"] == 2

    forked = client.post(f"/api/surveys/{survey['id']}/questions/{question_id}/revision",
                         json={"mode": "fork", "question": question_payload(title="分叉题")})
    assert forked.status_code == 200, forked.text
    forked_question = forked.json()["questions"][0]
    assert forked_question["id"] != question_id
    assert forked_question["title"] == "分叉题"
    assert db.questions.find_one({"_id": question_id})["current_version"] == 2


def test_fork_with_rules_rewrites_the_reference(client):
    question = create_question(client)
    survey = create_survey(client)
    imported = import_question(client, survey, question["id"])
    questions = imported["questions"] + [
        {"id": "tail", "type": "text", "title": "补充说明", "required": False,
         "options": [], "validation": {"min_length": 0, "max_length": 100}}]
    rules = [{"source": question["id"], "op": "eq", "value": "a", "target": "tail", "priority": 1}]
    saved = client.put(f"/api/surveys/{survey['id']}", json={
        "title": survey["title"], "description": "第二阶段测试", "allow_anonymous": True,
        "allow_repeat": True, "closes_at": None, "revision": imported["revision"],
        "questions": questions, "rules": rules})
    assert saved.status_code == 200, saved.text

    forked = client.post(f"/api/surveys/{survey['id']}/questions/{question['id']}/revision",
                         json={"mode": "fork", "question": question_payload(title="分叉并改跳转")})
    assert forked.status_code == 200, forked.text
    new_id = forked.json()["questions"][0]["id"]
    assert forked.json()["rules"][0]["source"] == new_id


# ---------------------------------------------------------------- R21 banks
def test_bank_items_pin_versions_and_can_be_updated(client, db):
    bank = client.post("/api/banks", json={"name": "常用题", "description": "年龄与性别"})
    assert bank.status_code == 201
    bank_id = bank.json()["id"]
    assert client.post("/api/banks", json={"name": "常用题"}).status_code == 409

    question = create_question(client)
    added = client.post(f"/api/banks/{bank_id}/items", json={"question_id": question["id"]})
    assert added.status_code == 201, added.text
    item = added.json()["items"][0]
    assert item["question_version"] == 1 and item["outdated"] is False
    assert client.post(f"/api/banks/{bank_id}/items",
                       json={"question_id": question["id"]}).status_code == 409

    new_version(client, question["id"], title="题库里的题更新了")
    bank_view = client.get(f"/api/banks/{bank_id}").json()
    assert bank_view["items"][0]["outdated"] is True
    assert bank_view["items"][0]["question_version"] == 1

    repinned = client.patch(f"/api/banks/{bank_id}/items/{question['id']}")
    assert repinned.status_code == 200, repinned.text
    assert repinned.json()["items"][0]["question_version"] == 2
    assert repinned.json()["items"][0]["outdated"] is False

    removed = client.delete(f"/api/banks/{bank_id}/items/{question['id']}")
    assert removed.json()["items"] == []
    assert client.get("/api/banks").json()[0]["items"] == 0


# ---------------------------------------------------------------- R22 cross-survey statistics
def test_cross_survey_statistics_aggregate_one_question(client, client_factory):
    question = create_question(client)
    first = create_survey(client, "问卷一")
    import_question(client, first, question["id"], version=1)
    publish(client, first)
    submit_answer(client, first, {question["id"]: "a"})

    second = create_survey(client, "问卷二")
    import_question(client, second, question["id"], version=1)
    publish(client, second)
    submit_answer(client, second, {question["id"]: "b"})

    new_version(client, question["id"], title="第三段年龄",
                options=[{"id": "a", "label": "18-25"}, {"id": "b", "label": "26-35"},
                         {"id": "c", "label": "36 以上"}])
    third = create_survey(client, "问卷三")
    import_question(client, third, question["id"], version=2)
    publish(client, third)
    submit_answer(client, third, {question["id"]: "c"})

    stats = client.get(f"/api/questions/{question['id']}/statistics").json()
    assert stats["survey_count"] == 3
    assert stats["total_answered"] == 3
    assert stats["scope"] == "all surveys"
    options = {row["id"]: row["count"] for row in stats["aggregate"]["by_type"]["single"]["options"]}
    assert options == {"a": 1, "b": 1, "c": 1}
    assert set(stats["by_question_version"]) == {"1", "2"}
    assert stats["by_question_version"]["1"]["answered"] == 2
    assert stats["by_question_version"]["2"]["answered"] == 1

    # A grantee only aggregates over their own surveys, never over the owner's data.
    with client_factory() as colleague:
        colleague_user = register_login(colleague)
        client.post(f"/api/questions/{question['id']}/shares", json={"username": colleague_user["username"]})
        mine = create_survey(colleague, "同事问卷")
        import_question(colleague, mine, question["id"], version=2)
        publish(colleague, mine)
        submit_answer(colleague, mine, {question["id"]: "a"})
        colleague_stats = colleague.get(f"/api/questions/{question['id']}/statistics").json()
        assert colleague_stats["scope"] == "own surveys only"
        assert colleague_stats["survey_count"] == 1
        assert colleague_stats["total_answered"] == 1


def test_cross_survey_statistics_of_number_and_text(client):
    number = create_question(client, type="number", title="你的年龄",
                             options=[], validation={"min_value": 0, "max_value": 120,
                                                     "integer_only": True})
    text = create_question(client, type="text", title="你的城市", options=[],
                           validation={"min_length": 0, "max_length": 50})
    survey = create_survey(client, "混合题")
    import_question(client, survey, number["id"])
    imported = import_question(client, survey, text["id"])
    publish(client, survey)
    submit_answer(client, survey, {number["id"]: 20, text["id"]: "上海"})
    submit_answer(client, survey, {number["id"]: 30, text["id"]: "上海"}, request_id="req-2")

    number_stats = client.get(f"/api/questions/{number['id']}/statistics").json()
    payload = number_stats["aggregate"]["by_type"]["number"]
    assert payload["count"] == 2 and payload["mean"] == 25
    text_stats = client.get(f"/api/questions/{text['id']}/statistics").json()
    assert text_stats["aggregate"]["by_type"]["text"]["values"].count("上海") == 2


def test_import_rejects_duplicates_and_published_surveys(client):
    question = create_question(client)
    survey = create_survey(client)
    import_question(client, survey, question["id"])
    duplicate = client.post(f"/api/surveys/{survey['id']}/questions/import",
                            json={"question_id": question["id"]})
    assert duplicate.status_code == 409
    publish(client, survey)
    late = client.post(f"/api/surveys/{survey['id']}/questions/import",
                       json={"question_id": question["id"]})
    assert late.status_code == 409


def test_share_pairs_and_bank_items_are_unique(client, db):
    question = create_question(client)
    now = datetime.now(timezone.utc)
    grantee = str(uuid4())
    share = {"_id": str(uuid4()), "question_id": question["id"], "owner_id": question["owner_id"],
             "grantee_id": grantee, "created_at": now, "schema_version": 1}
    db.question_shares.insert_one(dict(share))
    with pytest.raises(DuplicateKeyError):
        db.question_shares.insert_one({**share, "_id": str(uuid4())})

    bank_id = client.post("/api/banks", json={"name": "唯一性题库"}).json()["id"]
    client.post(f"/api/banks/{bank_id}/items", json={"question_id": question["id"]})
    with pytest.raises(DuplicateKeyError):
        db.question_bank_items.insert_one({
            "_id": str(uuid4()), "bank_id": bank_id, "question_id": question["id"],
            "question_version": 1, "added_by": question["owner_id"], "added_at": now,
            "schema_version": 1})


def test_usage_scope_hides_other_owners_surveys(client, client_factory):
    """A share grants reuse, not visibility into someone else's survey titles."""
    question = create_question(client)
    mine = create_survey(client, "我的问卷")
    import_question(client, mine, question["id"])
    publish(client, mine)
    with client_factory() as colleague:
        colleague_user = register_login(colleague)
        client.post(f"/api/questions/{question['id']}/shares",
                    json={"username": colleague_user["username"]})
        theirs = create_survey(colleague, "同事的问卷")
        import_question(colleague, theirs, question["id"])
        publish(client=colleague, survey=theirs)

        owner_view = client.get(f"/api/questions/{question['id']}/usage").json()
        assert owner_view["scope"] == "all surveys" and owner_view["usage_count"] == 2

        grantee_view = colleague.get(f"/api/questions/{question['id']}/usage").json()
        assert grantee_view["scope"] == "own surveys only"
        assert grantee_view["usage_count"] == 1
        assert grantee_view["other_surveys"] == 1
        assert [row["title"] for row in grantee_view["usages"]] == ["同事的问卷"]


def test_concurrent_new_versions_keep_a_contiguous_history(client, client_factory):
    """Simultaneous edits may conflict (409) or queue up, but must never gap or duplicate a version.

    TestClient requests can be serialised, so the assertion is the invariant rather than a fixed
    number of conflicts: versions stay 1..n, current_version equals the largest, and every
    outcome is either a creation or a clean conflict.
    """
    from concurrent.futures import ThreadPoolExecutor

    question = create_question(client)
    payload = question_payload(title="并发改题")
    with client_factory() as other:
        for cookie in client.cookies.jar:
            other.cookies.set(cookie.name, cookie.value)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(lambda inst=instance: inst.post(
                f"/api/questions/{question['id']}/versions", json=payload))
                for instance in (client, other)]
            codes = sorted(future.result().status_code for future in futures)
    assert set(codes) <= {201, 409}, f"unexpected outcomes: {codes}"
    assert 201 in codes, "at least one edit must succeed"
    detail = client.get(f"/api/questions/{question['id']}").json()
    versions = [row["version"] for row in detail["versions"]]
    assert versions == list(range(1, len(versions) + 1)), f"version history has a gap: {versions}"
    assert detail["current_version"] == max(versions)


def test_import_from_bank_uses_the_pinned_version(client):
    """Picking a question out of a bank honours that bank entry's pin, not the newest version."""
    question = create_question(client)
    bank_id = client.post("/api/banks", json={"name": "钉版题库"}).json()["id"]
    client.post(f"/api/banks/{bank_id}/items", json={"question_id": question["id"], "version": 1})
    new_version(client, question["id"], title="题库之后又更新了")

    pinned = create_survey(client, "用题库钉住版本")
    imported = client.post(f"/api/surveys/{pinned['id']}/questions/import",
                           json={"question_id": question["id"], "bank_id": bank_id})
    assert imported.status_code == 201, imported.text
    assert imported.json()["questions"][0]["question_version"] == 1

    explicit = create_survey(client, "显式指定版本")
    imported2 = client.post(f"/api/surveys/{explicit['id']}/questions/import",
                            json={"question_id": question["id"], "bank_id": bank_id, "version": 2})
    assert imported2.json()["questions"][0]["question_version"] == 2

    missing = create_survey(client, "题库里没有这题")
    rejected = client.post(f"/api/surveys/{missing['id']}/questions/import",
                           json={"question_id": question["id"], "bank_id": str(uuid4())})
    assert rejected.status_code == 404


def test_archiving_hides_a_question_and_blocks_new_use(client):
    question = create_question(client)
    survey = create_survey(client, "归档前的问卷")
    import_question(client, survey, question["id"])
    link = client.post(f"/api/questions/{question['id']}/share-links").json()
    assert link["token"]

    archived = client.patch(f"/api/questions/{question['id']}", json={"status": "archived"})
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"
    assert client.get("/api/questions").json() == []
    draft = client.get(f"/api/surveys/{survey['id']}").json()
    assert draft["questions"][0]["id"] == question["id"], "已加入的草稿不受归档影响"

    other = create_survey(client, "归档后的问卷")
    rejected = client.post(f"/api/surveys/{other['id']}/questions/import",
                           json={"question_id": question["id"]})
    assert rejected.status_code == 409
    assert client.get(f"/api/share-links/{link['token']}").status_code == 404
    assert client.post(f"/api/questions/{question['id']}/share-links").status_code == 409

    restored = client.patch(f"/api/questions/{question['id']}", json={"status": "active"})
    assert restored.json()["status"] == "active"
    assert [row["id"] for row in client.get("/api/questions").json()] == [question["id"]]


def test_share_link_preview_claim_and_revoke(client, client_factory):
    question = create_question(client)
    link = client.post(f"/api/questions/{question['id']}/share-links").json()
    with client_factory() as mate:
        register_login(mate)
        preview = mate.get(f"/api/share-links/{link['token']}").json()
        assert preview["title"] == "你的年龄段" and preview["owner_name"]
        claimed = mate.post(f"/api/share-links/{link['token']}/claim")
        assert claimed.status_code == 201, claimed.text
        assert claimed.json()["owned"] is False
        again = mate.post(f"/api/share-links/{link['token']}/claim")
        assert again.status_code == 201, "重复领取必须幂等"
        assert [row["id"] for row in mate.get("/api/questions/shared").json()] == [question["id"]]
        assert mate.delete(f"/api/questions/{question['id']}/share-links/{link['id']}").status_code == 404

    revoked = client.delete(f"/api/questions/{question['id']}/share-links/{link['id']}")
    assert revoked.status_code == 200
    assert client.get(f"/api/share-links/{link['token']}").status_code == 404
    assert client.get(f"/api/questions/{question['id']}/share-links").json()[0]["revoked"] is True


def test_share_link_expiry_and_claim_limit(client, client_factory, db):
    question = create_question(client)
    limited = client.post(f"/api/questions/{question['id']}/share-links",
                          json={"max_uses": 1}).json()
    with client_factory() as first, client_factory() as second:
        register_login(first)
        register_login(second)
        assert first.post(f"/api/share-links/{limited['token']}/claim").status_code == 201
        exhausted = second.post(f"/api/share-links/{limited['token']}/claim")
        assert exhausted.status_code == 410, exhausted.text
        assert first.get(f"/api/share-links/{limited['token']}").status_code == 410

    expiring = client.post(f"/api/questions/{question['id']}/share-links",
                           json={"expires_in_seconds": 3600}).json()
    assert expiring["expires_at"]
    db.question_share_links.update_one(
        {"_id": expiring["id"]},
        {"$set": {"expires_at": datetime.now(timezone.utc) - timedelta(minutes=1)}})
    assert client.get(f"/api/share-links/{expiring['token']}").status_code == 410
    rows = client.get(f"/api/questions/{question['id']}/share-links").json()
    assert next(row for row in rows if row["id"] == expiring["id"])["uses"] == 0


def test_bank_marks_archived_questions_and_refuses_new_ones(client):
    question = create_question(client)
    bank_id = client.post("/api/banks", json={"name": "归档题库"}).json()["id"]
    added = client.post(f"/api/banks/{bank_id}/items", json={"question_id": question["id"]})
    assert added.json()["items"][0]["archived"] is False

    other = create_question(client, title="之后归档的题")
    client.patch(f"/api/questions/{other['id']}", json={"status": "archived"})
    refused = client.post(f"/api/banks/{bank_id}/items", json={"question_id": other["id"]})
    assert refused.status_code == 409

    client.patch(f"/api/questions/{question['id']}", json={"status": "archived"})
    view = client.get(f"/api/banks/{bank_id}").json()
    assert view["items"][0]["archived"] is True


def test_statistics_limit_parameter(client):
    question = create_question(client)
    for index in range(3):
        survey = create_survey(client, f"限量问卷{index}")
        import_question(client, survey, question["id"])
        publish(client, survey)
        submit_answer(client, survey, {question["id"]: "a"}, request_id=f"req-limit-{index}")
    wide = client.get(f"/api/questions/{question['id']}/statistics").json()
    assert wide["survey_count"] == 3 and wide["truncated"] is False
    narrow = client.get(f"/api/questions/{question['id']}/statistics",
                        params={"limit": 2}).json()
    assert narrow["survey_count"] == 2
    assert narrow["truncated"] is True
    assert narrow["total_answered"] == 2
