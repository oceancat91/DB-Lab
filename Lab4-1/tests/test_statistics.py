"""S5 statistics acceptance using successful API submissions in real MongoDB."""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from copy import deepcopy
from uuid import uuid4

import pytest

from conftest import register_login


pytestmark = pytest.mark.integration


def _published(client, questions, rules=None, *, anonymous=True, repeat=True):
    created = client.post("/api/surveys", json={
        "title": "统计验收合成问卷", "description": "仅用于隔离测试数据库",
        "allow_anonymous": anonymous, "allow_repeat": repeat, "closes_at": None,
    })
    assert created.status_code == 201
    draft = created.json()
    saved = client.put(f"/api/surveys/{draft['id']}", json={
        "title": draft["title"], "description": draft["description"],
        "allow_anonymous": anonymous, "allow_repeat": repeat, "closes_at": None,
        "revision": draft["revision"], "questions": questions, "rules": rules or [],
    })
    assert saved.status_code == 200
    published = client.post(f"/api/surveys/{draft['id']}/publish", json={
        "revision": saved.json()["revision"],
    })
    assert published.status_code == 200
    return published.json()


def _submit(client, survey, answers):
    request_id = uuid4().hex
    submitted = client.post(f"/api/fill/{survey['share_code']}/submit", json={
        "version": survey["version"], "request_id": request_id, "answers": answers,
    })
    assert submitted.status_code == 200
    receipt = submitted.json()
    assert receipt["replayed"] is False
    return receipt


def _fixture_questions():
    return [
        {"id": "single", "type": "single", "title": "单选", "required": True,
         "options": [{"id": "A", "label": "甲选项"}, {"id": "B", "label": "乙选项"}]},
        {"id": "multi", "type": "multi", "title": "多选", "required": True,
         "options": [{"id": "X", "label": "X选项"}, {"id": "Y", "label": "Y选项"}],
         "validation": {"min_choices": 1, "max_choices": 2}},
        {"id": "text", "type": "text", "title": "文字", "required": True,
         "validation": {"min_length": 1, "max_length": 100}},
        # This extra gate preserves all three original answers while only r3
        # skips the numeric question. Every fixture is a valid reachable path.
        {"id": "gate", "type": "single", "title": "是否填写数字", "required": True,
         "options": [{"id": "answer", "label": "填写"}, {"id": "skip", "label": "跳过"}]},
        {"id": "number", "type": "number", "title": "数字", "required": True,
         "validation": {"min_value": 0, "max_value": 100, "integer_only": True}},
        {"id": "end", "type": "text", "title": "可选结语", "required": False},
    ]


def _three_responses(owner_client, client_factory, *, anonymous=True):
    owner = register_login(owner_client)
    survey = _published(owner_client, _fixture_questions(), [
        {"source": "gate", "op": "eq", "value": "skip", "target": "end", "priority": 10},
    ], anonymous=anonymous, repeat=True)
    with client_factory() as first, client_factory() as second:
        first_user = register_login(first)
        second_user = register_login(second)
        first_answers = {"single": "A", "multi": ["X", "Y"], "text": "甲",
                         "gate": "answer", "number": 10, "end": None}
        second_answers = {"single": "B", "multi": ["Y"], "text": "乙",
                          "gate": "answer", "number": 20, "end": None}
        third_answers = {"single": "A", "multi": ["X"], "text": "丙",
                         "gate": "skip", "end": None}
        receipts = [_submit(first, survey, first_answers), _submit(second, survey, second_answers),
                    _submit(first, survey, third_answers)]
    return {"owner": owner, "survey": survey, "users": [first_user, second_user], "receipts": receipts}


def _statistics(client, survey):
    response = client.get(f"/api/surveys/{survey['id']}/statistics")
    assert response.status_code == 200
    return response.json()


def _by_question(result):
    return {question["id"]: question for question in result["questions"]}


def _error(response, status):
    assert response.status_code == status
    payload = response.json()
    assert isinstance(payload.get("error"), dict)
    assert isinstance(payload["error"].get("message"), str)
    return payload["error"]


@pytest.mark.case("TC-S01")
def test_hand_calculated_fixture_and_every_single_question_match(client, client_factory, db):
    fixture = _three_responses(client, client_factory)
    survey = fixture["survey"]
    stored = list(db.responses.find({"survey_id": survey["id"]}))
    assert len(stored) == 3
    by_id = {row["_id"]: row for row in stored}
    third = by_id[fixture["receipts"][2]["id"]]
    assert third["path"] == ["single", "multi", "text", "gate", "end"]
    assert "number" not in third["answers"]  # Legitimate skip, not a hand-inserted bad answer.

    result = _statistics(client, survey)
    assert set(result) == {"survey_id", "version", "submissions", "respondents", "questions"}
    assert result["survey_id"] == survey["id"] and result["version"] == 1
    assert result["submissions"] == 3 and result["respondents"] == 2
    questions = _by_question(result)
    single = questions["single"]
    assert (single["answered_submissions"], single["answered_people"]) == (3, 2)
    assert {option["id"]: (option["count"], option["people"]) for option in single["options"]} == {
        "A": (2, 1), "B": (1, 1),
    }
    multi = questions["multi"]
    assert (multi["answered_submissions"], multi["answered_people"]) == (3, 2)
    assert {option["id"]: (option["count"], option["people"]) for option in multi["options"]} == {
        "X": (2, 1), "Y": (2, 2),
    }
    assert Counter(questions["text"]["values"]) == Counter(["甲", "乙", "丙"])
    assert (questions["number"]["answered_submissions"], questions["number"]["answered_people"]) == (2, 2)
    assert sorted(questions["number"]["values"]) == [10, 20]
    assert questions["number"]["mean"] == 15
    assert questions["end"]["values"] == []
    assert questions["end"]["answered_submissions"] == 0
    for question_id, expected in questions.items():
        one = client.get(f"/api/surveys/{survey['id']}/statistics/{question_id}")
        assert one.status_code == 200 and one.json() == expected

    # Closing collection must not erase or hide its already submitted results.
    assert client.post(f"/api/surveys/{survey['id']}/close").status_code == 200
    assert _statistics(client, survey) == result


@pytest.mark.case("TC-S02")
def test_zero_data_optional_null_zero_and_same_question_in_other_survey(client, client_factory, db):
    register_login(client)
    questions = [
        {"id": "number", "type": "number", "title": "同名数字", "required": False},
        {"id": "text", "type": "text", "title": "同名文字", "required": False},
    ]
    first = _published(client, questions)
    other = _published(client, deepcopy(questions))
    zero = _statistics(client, first)
    assert zero["submissions"] == zero["respondents"] == 0
    assert _by_question(zero)["number"]["mean"] is None
    assert all(question["answered_submissions"] == 0 for question in zero["questions"])
    with client_factory() as respondent:
        register_login(respondent)
        _submit(respondent, other, {"number": 99, "text": "另一份问卷"})
        assert _statistics(client, first) == zero
        empty = _submit(respondent, first, {"number": None, "text": " \t "})
        stored = db.responses.find_one({"_id": empty["id"]})
        assert stored["answers"] == {} and stored["path"] == ["number", "text"]
        null_result = _statistics(client, first)
        assert null_result["submissions"] == null_result["respondents"] == 1
        null_questions = _by_question(null_result)
        assert null_questions["number"]["mean"] is None
        assert null_questions["number"]["values"] == null_questions["text"]["values"] == []
        _submit(respondent, first, {"number": 0, "text": "0"})
    current = _statistics(client, first)
    assert current["submissions"] == 2 and current["respondents"] == 1
    numeric = _by_question(current)["number"]
    assert numeric["values"] == [0] and numeric["mean"] == 0
    assert numeric["answered_submissions"] == numeric["answered_people"] == 1
    assert _by_question(current)["text"]["values"] == ["0"]
    other_result = _statistics(client, other)
    assert other_result["submissions"] == 1
    assert _by_question(other_result)["number"]["values"] == [99]
    assert _by_question(other_result)["number"]["mean"] == 99
    # Stage one has exactly one published version per survey; no fake v2 records.
    for survey in (first, other):
        assert db.survey_versions.count_documents({"survey_id": survey["id"]}) == 1
        assert _statistics(client, survey)["version"] == 1


@pytest.mark.case("TC-S03", "TC-A03", "TC-A02")
def test_statistics_and_raw_response_routes_require_owner_and_login(client, client_factory, db):
    fixture = _three_responses(client, client_factory)
    survey = fixture["survey"]
    before = db.responses.count_documents({"survey_id": survey["id"]})
    routes = [f"/api/surveys/{survey['id']}/statistics",
              f"/api/surveys/{survey['id']}/statistics/single",
              f"/api/surveys/{survey['id']}/responses"]
    with client_factory() as stranger, client_factory() as anonymous:
        register_login(stranger)
        for route in routes:
            _error(stranger.get(route), 404)
            _error(anonymous.get(route), 401)
    assert db.responses.count_documents({"survey_id": survey["id"]}) == before == 3
    _error(client.get(f"/api/surveys/{survey['id']}/statistics/unknown"), 404)


@pytest.mark.case("TC-S02", "TC-S03")
def test_draft_has_no_statistics_and_owner_check_precedes_state_disclosure(client, client_factory):
    register_login(client)
    created = client.post("/api/surveys", json={"title": "尚未发布的统计测试"})
    assert created.status_code == 201
    survey_id = created.json()["id"]
    routes = [f"/api/surveys/{survey_id}/statistics",
              f"/api/surveys/{survey_id}/statistics/unknown",
              f"/api/surveys/{survey_id}/responses"]
    for route in routes:
        _error(client.get(route), 409)
    with client_factory() as stranger:
        register_login(stranger)
        for route in routes:
            _error(stranger.get(route), 404)


@pytest.mark.case("TC-S03", "TC-R04")
@pytest.mark.parametrize("anonymous", [True, False], ids=["anonymous", "identified"])
def test_response_whitelist_and_anonymity(client, client_factory, db, anonymous):
    fixture = _three_responses(client, client_factory, anonymous=anonymous)
    survey = fixture["survey"]
    detail = client.get(f"/api/surveys/{survey['id']}/responses")
    assert detail.status_code == 200
    public = detail.json()
    assert len(public) == 3
    allowed = {"id", "version", "answers", "path", "submitted_at", "anonymous"}
    if not anonymous:
        allowed.add("username")
    stored = {row["_id"]: row for row in db.responses.find({"survey_id": survey["id"]})}
    usernames = {user["id"]: user["username"] for user in fixture["users"]}
    for row in public:
        original = stored[row["id"]]
        assert set(row) == allowed
        assert row["version"] == 1 and row["anonymous"] is anonymous
        assert row["answers"] == original["answers"] and row["path"] == original["path"]
        assert row["submitted_at"]
        if anonymous:
            assert "username" not in row
        else:
            assert row["username"] == usernames[original["respondent_id"]]
    serialized = json.dumps({"statistics": _statistics(client, survey), "responses": public}, ensure_ascii=False)
    for field in ("respondent_id", "request_id", "payload_hash", "password_hash", "username_key", "single_submission"):
        assert field not in serialized
    for original in stored.values():
        for field in ("respondent_id", "request_id", "payload_hash"):
            assert original[field] not in serialized
    if anonymous:
        assert all(user["username"] not in serialized for user in fixture["users"])


@pytest.mark.case("TC-S01", "TC-S02")
@pytest.mark.parametrize("values,expected", [
    ([sys.float_info.max] * 3, sys.float_info.max),
    ([-sys.float_info.max] * 3, -sys.float_info.max),
    ([1e308, -1e308, 1e308], 1e308 / 3),
], ids=["largest-positive-double", "largest-negative-double", "large-cancellation"])
def test_large_finite_numeric_mean_via_actual_submissions(client, client_factory, values, expected):
    register_login(client)
    survey = _published(client, [{"id": "number", "type": "number", "title": "有限大数",
                                  "required": True, "validation": {}}], repeat=True)
    with client_factory() as respondent:
        register_login(respondent)
        for value in values:
            _submit(respondent, survey, {"number": value})
    result = _statistics(client, survey)
    numeric = _by_question(result)["number"]
    assert result["submissions"] == len(values) and result["respondents"] == 1
    assert numeric["answered_submissions"] == len(values)
    assert numeric["answered_people"] == 1
    assert Counter(numeric["values"]) == Counter(values)
    assert math.isfinite(numeric["mean"])
    assert numeric["mean"] == pytest.approx(expected)
    one = client.get(f"/api/surveys/{survey['id']}/statistics/number")
    assert one.status_code == 200 and one.json() == numeric
